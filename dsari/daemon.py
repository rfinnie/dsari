#!/usr/bin/env python

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
import tempfile
import shutil
import argparse
import copy
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


class Job():
    def __init__(self, name):
        self.name = name
        self.config = {}


class Run():
    def __init__(self, job, id):
        self.job = job
        self.id = id
        self.scheduled_time = None
        self.trigger_type = 'schedule'
        self.trigger_data = {}


class Scheduler():
    def __init__(self):
        self.shutdown = False
        self.args = self.parse_args()
        self.load_config()
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, self.signal_handler)

        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        lh_console = logging.StreamHandler()
        lh_console_formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
        lh_console.setFormatter(lh_console_formatter)
        if self.args.debug:
            lh_console.setLevel(logging.DEBUG)
        else:
            lh_console.setLevel(logging.INFO)
        self.logger.addHandler(lh_console)

        db_exists = os.path.exists(os.path.join(self.config['data_dir'], 'dsari.sqlite3'))
        self.db_conn = sqlite3.connect(os.path.join(self.config['data_dir'], 'dsari.sqlite3'))
        if not db_exists:
            self.db_conn.execute(
                """CREATE TABLE runs (
                    job_name text,
                    run_id text,
                    start_time real,
                    stop_time real,
                    exit_code integer,
                    trigger_type text,
                    trigger_data text,
                    run_data text
                )"""
            )
            self.db_conn.commit()

        self.reset_jobs()

        self.running_runs = []
        self.running_groups = {}

        self.wakeups = []
        self.next_wakeup = time.time() + 60.0

    def parse_args(self):
        parser = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        parser.add_argument('--config-dir', '-c', type=str, default=utils.DEFAULT_CONFIG_DIR)
        parser.add_argument('--debug', action='store_true')
        return parser.parse_args()

    def begin_shutdown(self):
        for run in copy.copy(self.runs):
            if run not in self.running_runs:
                self.runs.remove(run)

        if 'shutdown_kill_runs' in self.config and self.config['shutdown_kill_runs']:
            for run in self.running_runs:
                job = run.job
                self.logger.info('[%s %s] Shutdown requested, sending SIGTERM to %d' % (job.name, run.id, run.pid))
                os.kill(run.pid, signal.SIGTERM)
                run.term_sent = True
        elif len(self.running_runs) > 0:
            self.logger.info('Shutdown will proceed after runs have completed')

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

    def load_config(self):
        self.sighup_load_config = False
        self.config = utils.load_config(self.args.config_dir)

    def reset_jobs(self):
        self.runs = []
        now = time.time()
        for job_name in sorted(self.config['jobs']):
            job = Job(job_name)
            job.config = self.config['jobs'][job_name]
            run = Run(job, str(uuid.uuid4()))
            t = croniter_hash.croniter_hash(job.config['schedule'], start_time=now, hash_id=job_name).get_next() + (random.random() * 60.0)
            self.logger.debug('[%s %s] Next scheduled run: %s (%0.02fs)' % (job.name, run.id, time.strftime('%c', time.localtime(t)), (t - now)))
            run.scheduled_time = t
            self.runs.append(run)

    def process_run_execution_time(self, run):
        job = run.job
        if ('max_execution' not in job.config) or (not job.config['max_execution']):
            return
        sigterm_grace = 60.0
        sigkill_grace = 5.0
        now = time.time()
        delta = now - run.start_time
        if delta > (job.config['max_execution'] + sigterm_grace):
            if not run.kill_sent:
                self.logger.warning('[%s %s] SIGTERM grace (%0.02fs) exceeded, sending SIGKILL to %d' % (job.name, run.id, sigterm_grace, run.pid))
                os.kill(run.pid, signal.SIGKILL)
                run.kill_sent = True
            self.wakeups.append(now + sigkill_grace)
        elif delta > job.config['max_execution']:
            if not run.term_sent:
                self.logger.warn('[%s %s] Max execution (%0.02fs) exceeded, sending SIGTERM to %d' % (job.name, run.id, job.config['max_execution'], run.pid))
                os.kill(run.pid, signal.SIGTERM)
                run.term_sent = True
            self.wakeups.append(now + sigterm_grace)
        else:
            self.wakeups.append(run.start_time + job.config['max_execution'])

    def run_child_executor(self, run):
        # Reset all handled signals to default
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, signal.SIG_DFL)

        # Put the child in its own process group to prevent SIGINT from
        # propagating to the children
        os.setpgid(os.getpid(), 0)

        # Close the database in the child
        self.db_conn.close()

        # Set environment variables
        job = run.job
        os.environ['JOB_NAME'] = job.name
        os.environ['RUN_ID'] = run.id
        os.environ['BUILD_NUMBER'] = run.id
        os.environ['BUILD_ID'] = run.id
        os.environ['BUILD_TAG'] = 'dsari-%s-%s' % (job.name, run.id)
        if 'concurrency_group' in job.config and job.config['concurrency_group']:
            os.environ['CONCURRENCY_GROUP'] = job.config['concurrency_group']
        if run.previous_run:
            os.environ['PREVIOUS_RUN_ID'] = run.previous_run[0]
            os.environ['PREVIOUS_START_TIME'] = str(run.previous_run[1])
            os.environ['PREVIOUS_STOP_TIME'] = str(run.previous_run[2])
            os.environ['PREVIOUS_EXIT_CODE'] = str(run.previous_run[3])
        if 'environment' in job.config and job.config['environment']:
            for (key, val) in job.config['environment'].items():
                os.environ[key] = str(val)
        if 'environment' in run.trigger_data and run.trigger_data['environment']:
            for (key, val) in run.trigger_data['environment'].items():
                os.environ[key] = str(val)

        # Set STDIN to /dev/null, and STDOUT/STDERR to the tempfile
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        devnull_f = open(os.devnull, 'r')
        os.dup2(devnull_f.fileno(), 0)
        os.dup2(run.tempfile.fileno(), 1)
        os.dup2(run.tempfile.fileno(), 2)
        devnull_f.close()
        run.tempfile.close()

        # Finally!
        os.execvp(job.config['command'][0], job.config['command'])

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
        start_time = run.start_time
        stop_time = now
        self.logger.info('[%s %s] Finished with status %d in %0.02fs' % (job.name, run.id, child_exit, (stop_time - start_time)))
        #self.logger.debug('[%s %s] Resources: %s' % (job.name, run.id, repr(child_resource)))
        self.db_conn.execute('INSERT INTO runs (job_name, run_id, start_time, stop_time, exit_code, trigger_type, trigger_data, run_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (job.name, run.id, start_time, stop_time, child_exit, run.trigger_type, json.dumps(run.trigger_data), json.dumps({})))
        self.db_conn.commit()
        if not os.path.exists(os.path.join(self.config['data_dir'], 'runs', job.name)):
            os.makedirs(os.path.join(self.config['data_dir'], 'runs', job.name))
        shutil.copyfile(run.tempfile.name, os.path.join(self.config['data_dir'], 'runs', job.name, '%s.output' % run.id))
        os.remove(run.tempfile.name)
        self.running_runs.remove(run)
        self.runs.remove(run)
        if run.concurrency_group and run in self.running_groups[run.concurrency_group]:
            self.running_groups[run.concurrency_group].remove(run)
        if not self.shutdown:
            run = Run(job, str(uuid.uuid4()))
            t = croniter_hash.croniter_hash(job.config['schedule'], start_time=now, hash_id=job.name).get_next() + (random.random() * 60.0)
            run.scheduled_time = t
            self.runs.append(run)
            self.logger.debug('[%s %s] Next scheduled run: %s (%0.02fs)' % (job.name, run.id, time.strftime('%c', time.localtime(t)), (t - now)))
        return child_pid

    def process_run(self, run):
        now = time.time()
        job = run.job
        if run in self.running_runs:
            self.wakeups.append(now + backoff(run.scheduled_time, now))
            return
        if os.path.exists(os.path.join(self.config['data_dir'], 'trigger', job.name)):
            self.logger.info('[%s %s] Trigger detected, scheduling for now' % (job.name, run.id))
            run.trigger_type = 'file'
            with open(os.path.join(self.config['data_dir'], 'trigger', job.name)) as f:
                os.remove(os.path.join(self.config['data_dir'], 'trigger', job.name))
                try:
                    run.trigger_data = json.load(f)
                except ValueError:
                    run.trigger_data = {}
            run.scheduled_time = now
        if run.scheduled_time > now:
            self.wakeups.append(run.scheduled_time)
            return
        if 'concurrency_group' in job.config and job.config['concurrency_group']:
            concurrency_group = job.config['concurrency_group']
            if concurrency_group not in self.running_groups:
                self.running_groups[concurrency_group] = []
            concurrency_inuse = len(self.running_groups[concurrency_group])
            if (concurrency_group in self.config['concurrency_groups']) and ('max' in self.config['concurrency_groups'][concurrency_group]):
                concurrency_max = self.config['concurrency_groups'][concurrency_group]['max']
            else:
                concurrency_max = 1
            if concurrency_inuse >= concurrency_max:
                self.wakeups.append(now + backoff(run.scheduled_time, now))
                return
        else:
            concurrency_group = None

        res = self.db_conn.execute('SELECT run_id, start_time, stop_time, exit_code FROM runs WHERE job_name = ? ORDER BY stop_time DESC', (job.name,))
        run.previous_run = res.fetchone()
        res.close()

        self.logger.info('[%s %s] Running: %s' % (job.name, run.id, job.config['command']))
        run.start_time = now
        run.concurrency_group = concurrency_group
        run.term_sent = False
        run.kill_sent = False
        run.tempfile = tempfile.NamedTemporaryFile(delete=False)
        child_pid = os.fork()
        if child_pid == 0:
            self.run_child_executor(run)
            raise OSError('run_child_executor returned, when it should not have')
        else:
            run.pid = child_pid
            run.tempfile.close()
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
            for run in self.runs:
                self.process_run(run)

            for run in self.running_runs:
                self.process_run_execution_time(run)

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
    s = Scheduler()
    s.loop()
    return(2)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
