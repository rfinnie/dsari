#!/usr/bin/env python

# dsari - Do Something and Record It
# Copyright (C) 2015-2016 Ryan Finnie
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
import json
import time
import math
import random
import logging
import signal
import sqlite3
import argparse
import copy
import pwd
import datetime
import binascii

import dsari
from dsari.utils import seconds_to_td, td_to_seconds, epoch_to_dt, dt_to_epoch

try:
    from . import croniter_hash
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

try:
    import dateutil.rrule
    import dateutil.parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

__version__ = dsari.__version__


def get_next_schedule_time(schedule, job_name, start_time=None):
    if start_time is None:
        start_time = datetime.datetime.now()
    crc = binascii.crc32(job_name.encode('utf-8')) & 0xffffffff
    subsecond_offset = seconds_to_td(float(crc) / float(0xffffffff))
    if schedule.upper().startswith('RRULE:'):
        if not HAS_DATEUTIL:
            raise ImportError('dateutil not available, manual triggers only')
        hashed_epoch = start_time - seconds_to_td((dt_to_epoch(start_time) % (crc % 86400)))
        t = dateutil.rrule.rrulestr(schedule, dtstart=hashed_epoch).after(start_time) + subsecond_offset
        if t is None:
            raise ValueError('rrulestr returned None')
        return t
    if not HAS_CRONITER:
        raise ImportError('croniter not available, manual triggers only')
    if len(schedule.split(' ')) == 5:
        schedule = schedule + ' H'
    t = croniter_hash.croniter_hash(
        schedule,
        start_time=start_time,
        hash_id=job_name
    ).get_next(datetime.datetime) + subsecond_offset
    return t


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
        if datetime.datetime.now() >= deadline:
            return (child_pid, child_exit, child_resource)
        time.sleep(interval)


def backoff(a, b, min=5.0, max=300.0):
    a = dt_to_epoch(a)
    b = dt_to_epoch(b)
    if a >= b:
        return seconds_to_td(min)
    r = 2 ** math.log(b - a)
    if r < min:
        return seconds_to_td(min)
    elif r > max:
        return seconds_to_td(max)
    else:
        return seconds_to_td(r)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Do Something and Record It - scheduler daemon (%s)' % __version__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--version', action='version',
        version=__version__,
        help='report the program version',
    )
    parser.add_argument(
        '--config-dir', '-c', type=str, default=dsari.DEFAULT_CONFIG_DIR,
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

        if not os.path.exists(self.config.data_dir):
            os.makedirs(self.config.data_dir)
        db_exists = os.path.exists(os.path.join(self.config.data_dir, 'dsari.sqlite3'))
        self.db_conn = sqlite3.connect(os.path.join(self.config.data_dir, 'dsari.sqlite3'))
        self.db_conn.row_factory = sqlite3.Row
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

        sql_statement = """
            SELECT
                name
            FROM
                sqlite_master
            WHERE
                type = 'table'
            AND
                name = 'runs_running'
        """
        res = self.db_conn.execute(sql_statement)
        runs_running_exists = res.fetchone()
        res.close()
        if not runs_running_exists:
            sql_statement = """
                CREATE TABLE runs_running (
                    job_name text,
                    run_id text,
                    schedule_time real,
                    start_time real,
                    trigger_type text,
                    trigger_data text,
                    run_data text
                )
            """
            self.db_conn.execute(sql_statement)
            self.db_conn.commit()

        self.db_conn.execute('DELETE FROM runs_running')
        self.db_conn.commit()

        self.running_runs = []
        self.running_groups = {}

        self.reset_jobs()

        self.wakeups = []
        self.next_wakeup = datetime.datetime.now() + seconds_to_td(60.0)

        self.logger.info('Scheduler running')

    def begin_shutdown(self):
        self.shutdown = True
        self.shutdown_begin = datetime.datetime.now()
        self.scheduled_runs = []
        for run in self.running_runs:
            run.respawn = False

        if self.config.shutdown_kill_runs:
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
        if not self.config.shutdown_kill_runs:
            return
        if not self.config.shutdown_kill_grace:
            return
        if datetime.datetime.now() < (self.shutdown_begin + self.config.shutdown_kill_grace):
            self.wakeups.append(self.shutdown_begin + self.config.shutdown_kill_grace)
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
            self.begin_shutdown()
        elif signum == signal.SIGHUP:
            self.logger.info('SIGHUP received, reloading')
            self.load_config()
            self.reset_jobs()
        elif signum == signal.SIGQUIT:
            self.sigquit_status()

    def sigquit_status(self):
        now = datetime.datetime.now()
        for run in sorted(self.running_runs, key=lambda x: x.job.name):
            job = run.job
            t = run.start_time
            self.logger.info(
                '[%s %s] PID %d running since %s (%s)' % (
                    job.name,
                    run.id,
                    run.pid,
                    t,
                    (now - t)
                )
            )
        for run in sorted(self.scheduled_runs, key=lambda x: x.job.name):
            job = run.job
            t = run.schedule_time
            self.logger.info(
                '[%s %s] Next scheduled run: %s (%s)' % (
                    job.name,
                    run.id,
                    t,
                    (t - now)
                )
            )

    def load_config(self):
        self.config = dsari.Config()
        self.config.load_dir(self.args.config_dir)

    def reset_jobs(self):
        if self.shutdown:
            return
        self.jobs = []
        self.scheduled_runs = []
        for run in self.running_runs:
            run.respawn = False
        now = datetime.datetime.now()
        for (job_name, job) in sorted(self.config.jobs.items()):
            self.jobs.append(job)
            if not job.schedule:
                self.logger.debug('[%s] No schedule defined, manual triggers only' % job.name)
                continue
            try:
                t = get_next_schedule_time(job.schedule, job.name, start_time=now)
            except Exception as e:
                self.logger.warning('[%s] Invalid schedule (%s): %s: %s' % (job.name, job.schedule, type(e), str(e)))
                job.schedule = None
                continue
            run = dsari.Run(job)
            run.respawn = True
            run.trigger_type = 'schedule'
            self.logger.debug(
                '[%s %s] Next scheduled run: %s (%s)' % (
                    job.name,
                    run.id,
                    t,
                    (t - now)
                )
            )
            run.schedule_time = t
            self.scheduled_runs.append(run)

    def process_run_execution_time(self, run):
        job = run.job
        if not job.max_execution:
            return
        sigterm_grace = job.max_execution_grace
        sigkill_grace = seconds_to_td(5.0)
        now = datetime.datetime.now()
        delta = now - run.start_time
        if delta > (job.max_execution + sigterm_grace):
            if not run.kill_sent:
                self.logger.warning(
                    '[%s %s] SIGTERM grace (%s) exceeded, sending SIGKILL to %d' % (
                        job.name,
                        run.id,
                        sigterm_grace,
                        run.pid
                    )
                )
                os.kill(run.pid, signal.SIGKILL)
                run.kill_sent = True
            self.wakeups.append(now + sigkill_grace)
        elif delta > job.max_execution:
            if not run.term_sent:
                self.logger.warn(
                    '[%s %s] Max execution (%s) exceeded, sending SIGTERM to %d' % (
                        job.name,
                        run.id,
                        job.max_execution,
                        run.pid
                    )
                )
                os.kill(run.pid, signal.SIGTERM)
                run.term_sent = True
            self.wakeups.append(now + sigterm_grace)
        else:
            self.wakeups.append(run.start_time + job.max_execution)

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

        environ['DATA_DIR'] = self.config.data_dir
        environ['JOB_NAME'] = job.name
        environ['RUN_ID'] = run.id
        environ['RUN_DIR'] = os.path.join(self.config.data_dir, 'runs', job.name, run.id)
        environ['SCHEDULE_TIME'] = str(dt_to_epoch(run.schedule_time))
        environ['START_TIME'] = str(dt_to_epoch(run.start_time))
        environ['TRIGGER_TYPE'] = run.trigger_type
        if run.concurrency_group:
            environ['CONCURRENCY_GROUP'] = run.concurrency_group.name
        if run.previous_run:
            environ['PREVIOUS_RUN_ID'] = run.previous_run.id
            environ['PREVIOUS_SCHEDULE_TIME'] = str(dt_to_epoch(run.previous_run.schedule_time))
            environ['PREVIOUS_START_TIME'] = str(dt_to_epoch(run.previous_run.start_time))
            environ['PREVIOUS_STOP_TIME'] = str(dt_to_epoch(run.previous_run.stop_time))
            environ['PREVIOUS_EXIT_CODE'] = str(run.previous_run.exit_code)
        if run.previous_good_run:
            environ['PREVIOUS_GOOD_RUN_ID'] = run.previous_good_run.id
            environ['PREVIOUS_GOOD_SCHEDULE_TIME'] = str(dt_to_epoch(run.previous_good_run.schedule_time))
            environ['PREVIOUS_GOOD_START_TIME'] = str(dt_to_epoch(run.previous_good_run.start_time))
            environ['PREVIOUS_GOOD_STOP_TIME'] = str(dt_to_epoch(run.previous_good_run.stop_time))
            environ['PREVIOUS_GOOD_EXIT_CODE'] = str(run.previous_good_run.exit_code)
        if run.previous_bad_run:
            environ['PREVIOUS_BAD_RUN_ID'] = run.previous_bad_run.id
            environ['PREVIOUS_BAD_SCHEDULE_TIME'] = str(dt_to_epoch(run.previous_bad_run.schedule_time))
            environ['PREVIOUS_BAD_START_TIME'] = str(dt_to_epoch(run.previous_bad_run.start_time))
            environ['PREVIOUS_BAD_STOP_TIME'] = str(dt_to_epoch(run.previous_bad_run.stop_time))
            environ['PREVIOUS_BAD_EXIT_CODE'] = str(run.previous_bad_run.exit_code)
        if job.job_group:
            environ['JOB_GROUP'] = str(job.job_group)
        if job.jenkins_environment:
            environ['BUILD_NUMBER'] = run.id
            environ['BUILD_ID'] = run.id
            environ['BUILD_URL'] = 'file://%s' % os.path.join(self.config.data_dir, 'runs', job.name, run.id, '')
            environ['NODE_NAME'] = 'master'
            environ['BUILD_TAG'] = 'dsari-%s-%s' % (job.name, run.id)
            environ['JENKINS_URL'] = 'file://%s' % os.path.join(self.config.data_dir, '')
            environ['EXECUTOR_NUMBER'] = '0'
            environ['WORKSPACE'] = os.path.join(self.config.data_dir, 'runs', job.name, run.id)
        for (key, val) in self.config.environment.items():
            environ[str(key)] = str(val)
        for (key, val) in job.environment.items():
            environ[str(key)] = str(val)
        if 'environment' in run.trigger_data:
            for (key, val) in run.trigger_data['environment'].items():
                environ[str(key)] = str(val)

        # Set STDIN to /dev/null, and STDOUT/STDERR to the output file
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        out_f = open(os.path.join(self.config.data_dir, 'runs', job.name, run.id, 'output.txt'), 'w')
        devnull_f = open(os.devnull, 'r')
        os.dup2(devnull_f.fileno(), 0)
        os.dup2(out_f.fileno(), 1)
        os.dup2(out_f.fileno(), 2)
        devnull_f.close()
        out_f.close()

        # Build command line
        command = job.command
        if job.command_append_run:
            command.append(job.name)
            command.append(run.id)

        # chdir to the run directory
        run_pwd = os.path.join(self.config.data_dir, 'runs', job.name, run.id)
        if ('PWD' in environ) and os.path.isdir(environ['PWD']):
            run_pwd = environ['PWD']
        os.chdir(run_pwd)
        environ['PWD'] = run_pwd

        # Close any remaining open filehandles.  At this point it should
        # just be /dev/urandom (usually on fd 4), but it's not worth it to
        # actually verify.
        os.closerange(3, 1024)

        # Finally!
        os.execvpe(command[0], command, environ)

    def process_next_child(self):
        self.logger.debug('Waiting up to %s for running jobs' % (self.next_wakeup - datetime.datetime.now()))
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
        now = datetime.datetime.now()
        schedule_time = run.schedule_time
        start_time = run.start_time
        stop_time = now
        self.logger.info('[%s %s] Finished with status %d in %s' % (job.name, run.id, child_exit, (stop_time - start_time)))
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
            dt_to_epoch(schedule_time),
            dt_to_epoch(start_time),
            dt_to_epoch(stop_time),
            child_exit,
            run.trigger_type,
            json.dumps(run.trigger_data),
            json.dumps({})
        ))
        self.db_conn.execute('DELETE FROM runs_running WHERE run_id = ?', (run.id,))
        self.db_conn.commit()
        self.running_runs.remove(run)
        if run.concurrency_group and run in self.running_groups[run.concurrency_group]:
            self.running_groups[run.concurrency_group].remove(run)
        return child_pid

    def process_triggers(self):
        if self.shutdown:
            return
        for job in self.jobs:
            self.process_trigger_job(job)

    def process_trigger_job(self, job):
        trigger_file = os.path.join(self.config.data_dir, 'trigger', job.name, 'trigger.json')
        if not os.path.exists(trigger_file):
            return
        t = epoch_to_dt(os.path.getmtime(trigger_file))
        try:
            f = open(trigger_file)
        except IOError as e:
            # Return silently, otherwise we spam the log during each loop
            return
        try:
            os.remove(trigger_file)
        except OSError as e:
            # Return silently, otherwise we spam the log during each loop
            f.close()
            return
        try:
            j = json.load(f)
        except ValueError as e:
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

        if 'schedule_time' in j:
            if type(j['schedule_time']) in (int, float):
                t = epoch_to_dt(float(j['schedule_time']))
            elif HAS_DATEUTIL:
                try:
                    t = dateutil.parser.parse(j['schedule_time'])
                except ValueError:
                    self.logger.error('[%s] Invalid schedule_time "%s" for trigger' % (job.name, j['schedule_time']))
                    return
            else:
                self.logger.error('[%s] Cannot parse schedule_time "%s" for trigger' % (job.name, j['schedule_time']))
                return

        run = dsari.Run(job)
        run.respawn = False
        run.trigger_type = 'file'
        run.trigger_data = j
        run.schedule_time = t
        self.scheduled_runs.append(run)
        self.logger.info('[%s %s] Trigger detected, created run for %s' % (job.name, run.id, t))

    def process_scheduled_run(self, run):
        now = datetime.datetime.now()
        job = run.job
        if run.schedule_time > now:
            self.wakeups.append(run.schedule_time)
            return
        if (not job.concurrent_runs) and (job in [x.job for x in self.running_runs]):
            self.wakeups.append(now + backoff(run.schedule_time, now))
            return
        if (not job.concurrent_runs) and (job.name in [x.job.name for x in self.running_runs]):
            # Special case for a running run left during a SIGHUP reload
            self.wakeups.append(now + backoff(run.schedule_time, now))
            return
        run.concurrency_group = None
        if len(job.concurrency_groups) > 0:
            job_concurrency_groups = list(job.concurrency_groups.keys())
            random.shuffle(job_concurrency_groups)
            for concurrency_group_name in job_concurrency_groups:
                concurrency_group = job.concurrency_groups[concurrency_group_name]
                if concurrency_group not in self.running_groups:
                    self.running_groups[concurrency_group] = []
                if len(self.running_groups[concurrency_group]) < concurrency_group.max:
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
                exit_code,
                trigger_type,
                trigger_data,
                run_data
            FROM
                runs
            WHERE
                job_name = ?
            ORDER BY
                stop_time DESC
        """
        res = self.db_conn.execute(sql_statement, (job.name,))
        f = res.fetchone()
        res.close()
        if f:
            run.previous_run = dsari.Run(run.job, id=f['run_id'])
            run.previous_run.schedule_time = epoch_to_dt(f['schedule_time'])
            run.previous_run.start_time = epoch_to_dt(f['start_time'])
            run.previous_run.stop_time = epoch_to_dt(f['stop_time'])
            run.previous_run.exit_code = f['exit_code']
            run.previous_run.trigger_type = f['trigger_type']
            run.previous_run.trigger_data = json.loads(f['trigger_data'])
            run.previous_run.run_data = json.loads(f['run_data'])
        else:
            run.previous_run = None

        sql_statement = """
            SELECT
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code,
                trigger_type,
                trigger_data,
                run_data
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
        f = res.fetchone()
        res.close()
        if f:
            run.previous_good_run = dsari.Run(run.job, id=f['run_id'])
            run.previous_good_run.schedule_time = epoch_to_dt(f['schedule_time'])
            run.previous_good_run.start_time = epoch_to_dt(f['start_time'])
            run.previous_good_run.stop_time = epoch_to_dt(f['stop_time'])
            run.previous_good_run.exit_code = f['exit_code']
            run.previous_good_run.trigger_type = f['trigger_type']
            run.previous_good_run.trigger_data = json.loads(f['trigger_data'])
            run.previous_good_run.run_data = json.loads(f['run_data'])
        else:
            run.previous_good_run = None

        sql_statement = """
            SELECT
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code,
                trigger_type,
                trigger_data,
                run_data
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
        f = res.fetchone()
        res.close()
        if f:
            run.previous_bad_run = dsari.Run(run.job, id=f['run_id'])
            run.previous_bad_run.schedule_time = epoch_to_dt(f['schedule_time'])
            run.previous_bad_run.start_time = epoch_to_dt(f['start_time'])
            run.previous_bad_run.stop_time = epoch_to_dt(f['stop_time'])
            run.previous_bad_run.exit_code = f['exit_code']
            run.previous_bad_run.trigger_type = f['trigger_type']
            run.previous_bad_run.trigger_data = json.loads(f['trigger_data'])
            run.previous_bad_run.run_data = json.loads(f['run_data'])
        else:
            run.previous_bad_run = None

        if not os.path.exists(os.path.join(self.config.data_dir, 'runs', job.name, run.id)):
            os.makedirs(os.path.join(self.config.data_dir, 'runs', job.name, run.id))

        self.logger.info('[%s %s] Running: %s' % (job.name, run.id, job.command))
        run.start_time = now
        run.term_sent = False
        run.kill_sent = False

        sql_statement = """
            INSERT INTO runs_running (
                job_name,
                run_id,
                schedule_time,
                start_time,
                trigger_type,
                trigger_data,
                run_data
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?
            )
        """
        self.db_conn.execute(sql_statement, (
            job.name,
            run.id,
            dt_to_epoch(run.schedule_time),
            dt_to_epoch(run.start_time),
            run.trigger_type,
            json.dumps(run.trigger_data),
            json.dumps({})
        ))
        self.db_conn.commit()

        child_pid = os.fork()
        if child_pid == 0:
            self.run_child_executor(run)
            raise OSError('run_child_executor returned, when it should not have')
        run.pid = child_pid
        self.scheduled_runs.remove(run)
        self.running_runs.append(run)
        if run.concurrency_group:
            self.running_groups[run.concurrency_group].append(run)
        if run.respawn and job.schedule:
            run = dsari.Run(job)
            run.respawn = True
            run.trigger_type = 'schedule'
            t = get_next_schedule_time(job.schedule, job.name, start_time=now)
            run.schedule_time = t
            self.scheduled_runs.append(run)
            self.logger.debug(
                '[%s %s] Next scheduled run: %s (%s)' % (
                    job.name,
                    run.id,
                    t,
                    (t - now)
                )
            )

    def process_wakeups(self):
        self.next_wakeup = datetime.datetime.now() + seconds_to_td(60.0)
        for wakeup in self.wakeups:
            if wakeup < self.next_wakeup:
                self.next_wakeup = wakeup

    def loop(self):
        while True:
            self.wakeups = []
            self.process_triggers()

            scheduled_runs = copy.copy(self.scheduled_runs)
            random.shuffle(scheduled_runs)
            for run in scheduled_runs:
                self.process_scheduled_run(run)

            for run in self.running_runs:
                self.process_run_execution_time(run)

            if self.shutdown:
                self.monitor_shutdown()

            self.process_wakeups()

            if len(self.running_runs) > 0:
                while (len(self.running_runs) > 0) and (self.next_wakeup > datetime.datetime.now()):
                    if self.process_next_child() == 0:
                        break
            else:
                if self.shutdown:
                    self.logger.info('Shutdown complete')
                    return

                to_sleep = self.next_wakeup - datetime.datetime.now()
                if to_sleep > seconds_to_td(0):
                    self.logger.debug('No running jobs, waiting %s' % to_sleep)
                    time.sleep(td_to_seconds(to_sleep))


def main():
    args = parse_args()
    if args.fork:
        child_pid = os.fork()
        if child_pid > 0:
            return
    s = Scheduler(args)
    s.loop()


if __name__ == '__main__':
    import sys
    sys.exit(main())
