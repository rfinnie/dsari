#!/usr/bin/env python

# dsari - Do Something and Record It
# Copyright (C) 2015 Ryan Finnie
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

import os
import sys
import json
import time
import uuid
import math
import random
import logging
import signal
import sqlite3
import argparse
import copy
import re
import binascii
import pwd
import __init__ as dsari
import croniter_hash
import utils


def wait_deadline(pid, options, deadline, interval=0.05):
    while True:
        (child_pid, child_exit, child_resource) = os.wait4(pid, options)
        child_signal = child_exit % 256
        if child_signal > 0:
            child_exit = 128 + child_signal
        else:
            child_exit = child_exit >> 8
        if child_pid != 0:
            return (child_pid, child_exit, child_resource)
        if time.time() >= deadline:
            return (child_pid, child_exit, child_resource)
        time.sleep(interval)


def backoff(a, b, min=5.0, max=300.0):
    if a >= b:
        return min
    r = 2 ** math.log(b - a)
    if r < min:
        return min
    elif r > max:
        return max
    else:
        return r


def parse_args():
    parser = argparse.ArgumentParser(
        description='Do Something and Record It - scheduler daemon (%s)' % dsari.VERSION,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--config-dir', '-c', type=str, default=utils.DEFAULT_CONFIG_DIR,
        help='configuration directory for dsari.json',
    )
    parser.add_argument(
        '--fork', action='store_true',
        help='fork into the background after starting',
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='output additional debugging information',
    )
    parser.add_argument(
        '--no-timestamp', action='store_true',
        help='do not show timestamps in logging output',
    )
    return parser.parse_args()


class Job():
    def __init__(self, name):
        self.name = name
        self.config = {}


class Run():
    def __init__(self, job, id):
        self.job = job
        self.id = id
        self.schedule_time = None
        self.trigger_type = 'schedule'
        self.trigger_data = {}
        self.respawn = False


class Scheduler():
    def __init__(self, args):
        self.shutdown = False
        self.args = args
        self.load_config()
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGQUIT):
            signal.signal(signum, self.signal_handler)

        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        lh_console = logging.StreamHandler()
        if self.args.no_timestamp:
            lh_console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        else:
            lh_console_formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
        lh_console.setFormatter(lh_console_formatter)
        if self.args.debug:
            lh_console.setLevel(logging.DEBUG)
        else:
            lh_console.setLevel(logging.INFO)
        self.logger.addHandler(lh_console)

        if not os.path.exists(self.config['data_dir']):
            os.makedirs(self.config['data_dir'])
        db_exists = os.path.exists(os.path.join(self.config['data_dir'], 'dsari.sqlite3'))
        self.db_conn = sqlite3.connect(os.path.join(self.config['data_dir'], 'dsari.sqlite3'))
        if not db_exists:
            sql_statement = """
                CREATE TABLE runs (
                    job_name text,
                    run_id text,
                    schedule_time real,
                    start_time real,
                    stop_time real,
                    exit_code integer,
                    trigger_type text,
                    trigger_data text,
                    run_data text
                )
            """
            self.db_conn.execute(sql_statement)
            self.db_conn.commit()

        self.reset_jobs()

        self.running_runs = []
        self.running_groups = {}

        self.wakeups = []
        self.next_wakeup = time.time() + 60.0

        self.logger.info('Scheduler running')

    def begin_shutdown(self):
        for run in copy.copy(self.runs):
            if run not in self.running_runs:
                self.runs.remove(run)

        if self.config['shutdown_kill_runs']:
            for run in self.running_runs:
                if run.term_sent:
                    continue
                job = run.job
                self.logger.info('[%s %s] Shutdown requested, sending SIGTERM to %d' % (job.name, run.id, run.pid))
                os.kill(run.pid, signal.SIGTERM)
                run.term_sent = True
        elif len(self.running_runs) > 0:
            self.logger.info('Shutdown will proceed after runs have completed')

    def monitor_shutdown(self):
        if not self.config['shutdown_kill_runs']:
            return
        if not self.config['shutdown_kill_grace']:
            return
        if time.time() < (self.shutdown_begin + self.config['shutdown_kill_grace']):
            self.wakeups.append(self.shutdown_begin + self.config['shutdown_kill_grace'])
            return
        for run in self.running_runs:
            if run.kill_sent:
                continue
            job = run.job
            self.logger.info('[%s %s] Shutdown grace time exceeded, sending SIGKILL to %d' % (job.name, run.id, run.pid))
            os.kill(run.pid, signal.SIGKILL)
            run.kill_sent = True

    def signal_handler(self, signum, frame):
        if signum in (signal.SIGINT, signal.SIGTERM):
            if signum == signal.SIGINT:
                self.logger.info('SIGINT received, beginning shutdown')
            elif signum == signal.SIGTERM:
                self.logger.info('SIGTERM received, beginning shutdown')
            self.shutdown = True
            self.shutdown_begin = time.time()
            self.begin_shutdown()
        elif signum == signal.SIGHUP:
            self.logger.info('SIGHUP received, reloading config when next idle')
            self.sighup_load_config = True
        elif signum == signal.SIGQUIT:
            self.sigquit_status()

    def sigquit_status(self):
        now = time.time()
        for run in sorted(self.runs, key=lambda x: x.job.name):
            job = run.job
            if run in self.running_runs:
                t = run.start_time
                self.logger.info(
                    '[%s %s] PID %d running since %s (%0.02fs)' % (
                        job.name,
                        run.id,
                        run.pid,
                        time.strftime('%c', time.localtime(t)),
                        (now - t)
                    )
                )
            else:
                t = run.schedule_time
                self.logger.info(
                    '[%s %s] Next scheduled run: %s (%0.02fs)' % (
                        job.name,
                        run.id,
                        time.strftime('%c', time.localtime(t)),
                        (t - now)
                    )
                )

    def load_config(self):
        self.sighup_load_config = False
        self.config = utils.load_config(self.args.config_dir)

    def reset_jobs(self):
        if self.shutdown:
            return
        self.jobs = []
        self.runs = []
        now = time.time()
        for job_name in sorted(self.config['jobs']):
            if (len(job_name) > 64) or (not re.search('^([- A-Za-z0-9_+.:@]+)$', job_name)):
                self.logger.warning('Invalid job name: %s' % job_name)
                continue
            job = Job(job_name)
            job.config = self.config['jobs'][job_name]
            job.subsecond_offset = float(binascii.crc32(job.name) & 0xffffffff) / float(2**32)
            self.jobs.append(job)
            if not job.config['schedule']:
                self.logger.debug('[%s] No schedule defined, manual triggers only' % job.name)
                continue
            if len(job.config['schedule'].split(' ')) == 5:
                job.config['schedule'] = job.config['schedule'] + ' H'
            try:
                t = croniter_hash.croniter_hash(
                    job.config['schedule'],
                    start_time=now,
                    hash_id=job_name
                ).get_next() + job.subsecond_offset
            except Exception, e:
                self.logger.warning('[%s] Invalid schedule: %s: %s' % (job.name, type(e), str(e)))
                continue
            run = Run(job, str(uuid.uuid4()))
            run.respawn = True
            self.logger.debug(
                '[%s %s] Next scheduled run: %s (%0.02fs)' % (
                    job.name,
                    run.id,
                    time.strftime('%c', time.localtime(t)),
                    (t - now)
                )
            )
            run.schedule_time = t
            self.runs.append(run)

    def process_run_execution_time(self, run):
        job = run.job
        if not job.config['max_execution']:
            return
        sigterm_grace = job.config['max_execution_grace']
        sigkill_grace = 5.0
        now = time.time()
        delta = now - run.start_time
        if delta > (job.config['max_execution'] + sigterm_grace):
            if not run.kill_sent:
                self.logger.warning(
                    '[%s %s] SIGTERM grace (%0.02fs) exceeded, sending SIGKILL to %d' % (
                        job.name,
                        run.id,
                        sigterm_grace,
                        run.pid
                    )
                )
                os.kill(run.pid, signal.SIGKILL)
                run.kill_sent = True
            self.wakeups.append(now + sigkill_grace)
        elif delta > job.config['max_execution']:
            if not run.term_sent:
                self.logger.warn(
                    '[%s %s] Max execution (%0.02fs) exceeded, sending SIGTERM to %d' % (
                        job.name,
                        run.id,
                        job.config['max_execution'],
                        run.pid
                    )
                )
                os.kill(run.pid, signal.SIGTERM)
                run.term_sent = True
            self.wakeups.append(now + sigterm_grace)
        else:
            self.wakeups.append(run.start_time + job.config['max_execution'])

    def run_child_executor(self, run):
        # Reset all handled signals to default
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGQUIT):
            signal.signal(signum, signal.SIG_DFL)

        # Put the child in its own process group to prevent SIGINT from
        # propagating to the children
        os.setpgid(os.getpid(), 0)

        # Close the database in the child
        self.db_conn.close()

        # Set environment variables
        job = run.job
        environ = {}

        try:
            pwd_user = pwd.getpwuid(os.getuid())
            environ['LOGNAME'] = pwd_user.pw_name
            environ['HOME'] = pwd_user.pw_dir
        except KeyError:
            pass
        if 'PATH' in os.environ:
            environ['PATH'] = os.environ['PATH']
        else:
            environ['PATH'] = '/usr/bin:/bin'

        environ['JOB_NAME'] = job.name
        environ['RUN_ID'] = run.id
        if run.concurrency_group:
            environ['CONCURRENCY_GROUP'] = run.concurrency_group
        if run.previous_run:
            environ['PREVIOUS_RUN_ID'] = run.previous_run[0]
            environ['PREVIOUS_SCHEDULE_TIME'] = str(run.previous_run[1])
            environ['PREVIOUS_START_TIME'] = str(run.previous_run[2])
            environ['PREVIOUS_STOP_TIME'] = str(run.previous_run[3])
            environ['PREVIOUS_EXIT_CODE'] = str(run.previous_run[4])
        if run.previous_good_run:
            environ['PREVIOUS_GOOD_RUN_ID'] = run.previous_good_run[0]
            environ['PREVIOUS_GOOD_SCHEDULE_TIME'] = str(run.previous_good_run[1])
            environ['PREVIOUS_GOOD_START_TIME'] = str(run.previous_good_run[2])
            environ['PREVIOUS_GOOD_STOP_TIME'] = str(run.previous_good_run[3])
            environ['PREVIOUS_GOOD_EXIT_CODE'] = str(run.previous_good_run[4])
        if run.previous_bad_run:
            environ['PREVIOUS_BAD_RUN_ID'] = run.previous_bad_run[0]
            environ['PREVIOUS_BAD_SCHEDULE_TIME'] = str(run.previous_bad_run[1])
            environ['PREVIOUS_BAD_START_TIME'] = str(run.previous_bad_run[2])
            environ['PREVIOUS_BAD_STOP_TIME'] = str(run.previous_bad_run[3])
            environ['PREVIOUS_BAD_EXIT_CODE'] = str(run.previous_bad_run[4])
        if job.config['jenkins_environment']:
            environ['BUILD_NUMBER'] = run.id
            environ['BUILD_ID'] = run.id
            environ['BUILD_URL'] = 'file://%s' % os.path.join(self.config['data_dir'], 'runs', job.name, run.id, '')
            environ['NODE_NAME'] = 'master'
            environ['BUILD_TAG'] = 'dsari-%s-%s' % (job.name, run.id)
            environ['JENKINS_URL'] = 'file://%s' % os.path.join(self.config['data_dir'], '')
            environ['EXECUTOR_NUMBER'] = '0'
            environ['WORKSPACE'] = os.path.join(self.config['data_dir'], 'runs', job.name, run.id)
        for (key, val) in job.config['environment'].items():
            environ[str(key)] = str(val)
        if 'environment' in run.trigger_data:
            for (key, val) in run.trigger_data['environment'].items():
                environ[str(key)] = str(val)

        # Set STDIN to /dev/null, and STDOUT/STDERR to the output file
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        out_f = open(os.path.join(self.config['data_dir'], 'runs', job.name, run.id, 'output.txt'), 'w')
        devnull_f = open(os.devnull, 'r')
        os.dup2(devnull_f.fileno(), 0)
        os.dup2(out_f.fileno(), 1)
        os.dup2(out_f.fileno(), 2)
        devnull_f.close()
        out_f.close()

        # Build command line
        command = job.config['command']
        if job.config['command_append_run']:
            command.append(job.name)
            command.append(run.id)

        # chdir to the run directory
        os.chdir(os.path.join(self.config['data_dir'], 'runs', job.name, run.id))
        environ['PWD'] = os.path.join(self.config['data_dir'], 'runs', job.name, run.id)

        # Close any remaining open filehandles.  At this point it should
        # just be /dev/urandom (usually on fd 4), but it's not worth it to
        # actually verify.
        os.closerange(3, 1024)

        # Finally!
        os.execvpe(command[0], command, environ)

    def process_next_child(self):
        self.logger.debug('Waiting up to %0.02fs for running jobs' % (self.next_wakeup - time.time()))
        (child_pid, child_exit, child_resource) = wait_deadline(-1, os.WNOHANG, self.next_wakeup)
        if child_pid == 0:
            return child_pid
        run = None
        for r in self.running_runs:
            if r.pid == child_pid:
                run = r
                break
        if not run:
            return child_pid
        job = run.job
        now = time.time()
        schedule_time = run.schedule_time
        start_time = run.start_time
        stop_time = now
        self.logger.info('[%s %s] Finished with status %d in %0.02fs' % (job.name, run.id, child_exit, (stop_time - start_time)))
        sql_statement = """
            INSERT INTO runs (
                job_name,
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code,
                trigger_type,
                trigger_data,
                run_data
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """
        self.db_conn.execute(sql_statement, (
            job.name,
            run.id,
            schedule_time,
            start_time,
            stop_time,
            child_exit,
            run.trigger_type,
            json.dumps(run.trigger_data),
            json.dumps({})
        ))
        self.db_conn.commit()
        self.running_runs.remove(run)
        self.runs.remove(run)
        if run.concurrency_group and run in self.running_groups[run.concurrency_group]:
            self.running_groups[run.concurrency_group].remove(run)
        if (not self.shutdown) and run.respawn and job.config['schedule']:
            run = Run(job, str(uuid.uuid4()))
            run.respawn = True
            t = croniter_hash.croniter_hash(
                job.config['schedule'],
                start_time=now,
                hash_id=job.name
            ).get_next() + job.subsecond_offset
            run.schedule_time = t
            self.runs.append(run)
            self.logger.debug(
                '[%s %s] Next scheduled run: %s (%0.02fs)' % (
                    job.name,
                    run.id,
                    time.strftime('%c', time.localtime(t)), (t - now)
                )
            )
        return child_pid

    def process_triggers(self):
        if self.shutdown:
            return
        for job in self.jobs:
            self.process_trigger_job(job)

    def process_trigger_job(self, job):
        trigger_file = os.path.join(self.config['data_dir'], 'trigger', job.name, 'trigger.json')
        if not os.path.exists(trigger_file):
            return
        t = os.path.getmtime(trigger_file)
        try:
            f = open(trigger_file)
        except IOError, e:
            # Return silently, otherwise we spam the log during each loop
            return
        try:
            os.remove(trigger_file)
        except OSError, e:
            # Return silently, otherwise we spam the log during each loop
            f.close()
            return
        try:
            j = json.load(f)
        except ValueError, e:
            self.logger.error('[%s] Cannot load trigger: %s' % (job.name, e.message))
            f.close()
            return
        f.close()
        if type(j) != dict:
            self.logger.error('[%s] Cannot load trigger: Data must be a dict' % job.name)
            return
        if ('environment' in j) and (type(j['environment']) != dict):
            self.logger.error('[%s] Cannot load trigger: environment must be a dict' % job.name)
            return

        self.logger.info('[%s] Trigger detected, creating trigger run' % job.name)
        run = Run(job, str(uuid.uuid4()))
        run.respawn = False
        run.trigger_type = 'file'
        run.trigger_data = j
        run.schedule_time = t
        self.runs.append(run)

    def process_run(self, run):
        now = time.time()
        job = run.job
        if run in self.running_runs:
            self.wakeups.append(now + backoff(run.schedule_time, now))
            return
        if run.schedule_time > now:
            self.wakeups.append(run.schedule_time)
            return
        run.concurrency_group = None
        if len(job.config['concurrency_groups']) > 0:
            job_concurrency_groups = copy.copy(job.config['concurrency_groups'])
            random.shuffle(job_concurrency_groups)
            for concurrency_group in job_concurrency_groups:
                if concurrency_group not in self.running_groups:
                    self.running_groups[concurrency_group] = []
                concurrency_inuse = len(self.running_groups[concurrency_group])
                if (
                    (concurrency_group in self.config['concurrency_groups'])
                    and ('max' in self.config['concurrency_groups'][concurrency_group])
                ):
                    concurrency_max = self.config['concurrency_groups'][concurrency_group]['max']
                else:
                    concurrency_max = 1
                if concurrency_inuse < concurrency_max:
                    run.concurrency_group = concurrency_group
                    break
            if not run.concurrency_group:
                self.wakeups.append(now + backoff(run.schedule_time, now))
                return

        sql_statement = """
            SELECT
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code
            FROM
                runs
            WHERE
                job_name = ?
            ORDER BY
                stop_time DESC
        """
        res = self.db_conn.execute(sql_statement, (job.name,))
        run.previous_run = res.fetchone()
        res.close()

        sql_statement = """
            SELECT
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code
            FROM
                runs
            WHERE
                job_name = ?
            AND
                exit_code = 0
            ORDER BY
                stop_time DESC
        """
        res = self.db_conn.execute(sql_statement, (job.name,))
        run.previous_good_run = res.fetchone()
        res.close()

        sql_statement = """
            SELECT
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code
            FROM
                runs
            WHERE
                job_name = ?
            AND
                exit_code != 0
            ORDER BY
                stop_time DESC
        """
        res = self.db_conn.execute(sql_statement, (job.name,))
        run.previous_bad_run = res.fetchone()
        res.close()

        if not os.path.exists(os.path.join(self.config['data_dir'], 'runs', job.name, run.id)):
            os.makedirs(os.path.join(self.config['data_dir'], 'runs', job.name, run.id))

        self.logger.info('[%s %s] Running: %s' % (job.name, run.id, job.config['command']))
        run.start_time = now
        run.term_sent = False
        run.kill_sent = False
        child_pid = os.fork()
        if child_pid == 0:
            self.run_child_executor(run)
            raise OSError('run_child_executor returned, when it should not have')
        run.pid = child_pid
        self.running_runs.append(run)
        if run.concurrency_group:
            self.running_groups[run.concurrency_group].append(run)

    def process_wakeups(self):
        self.next_wakeup = time.time() + 60.0
        for wakeup in self.wakeups:
            if wakeup < self.next_wakeup:
                self.next_wakeup = wakeup

    def loop(self):
        while True:
            self.wakeups = []
            self.process_triggers()
            runs = copy.copy(self.runs)
            random.shuffle(runs)
            for run in runs:
                self.process_run(run)

            for run in self.running_runs:
                self.process_run_execution_time(run)

            if self.shutdown:
                self.monitor_shutdown()

            self.process_wakeups()

            if len(self.running_runs) > 0:
                while (len(self.running_runs) > 0) and (self.next_wakeup > time.time()):
                    if self.process_next_child() == 0:
                        break
            else:
                if self.shutdown:
                    self.logger.info('Shutdown complete')
                    return

                to_sleep = self.next_wakeup - time.time()
                if to_sleep > 0:
                    self.logger.debug('No running jobs, waiting %0.02fs' % to_sleep)
                    time.sleep(to_sleep)

                if self.sighup_load_config:
                    self.logger.info('Reloading config')
                    self.load_config()
                    self.reset_jobs()


def main(argv):
    args = parse_args()
    if args.fork:
        child_pid = os.fork()
        if child_pid > 0:
            return
    s = Scheduler(args)
    s.loop()


if __name__ == '__main__':
    sys.exit(main(sys.argv))
