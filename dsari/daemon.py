#!/usr/bin/env python

# TODO:
# running_groups

import os
import sys
import subprocess
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
import croniter_hash

VAR_DIR = 'var'


def wait_deadline(pid, options, deadline, interval=0.05):
    while True:
        (child_pid, child_exit, child_resource) = os.wait4(pid, options)
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
        self.run = None


class Run():
    def __init__(self, job, id):
        self.job = job
        self.id = id
        self.scheduled_time = None
        self.trigger_type = 'schedule'
        self.trigger_data = {}


class Scheduler():
    def __init__(self):
        self.load_config()
        signal.signal(signal.SIGHUP, self.sighup_handler)

        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        lh_console = logging.StreamHandler()
        lh_console_formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
        lh_console.setFormatter(lh_console_formatter)
        lh_console.setLevel(logging.DEBUG)
        self.logger.addHandler(lh_console)

        self.db_conn = sqlite3.connect('dsari.sqlite3')

        self.reset_jobs()

        self.running_jobs = []
        self.running_groups = {}

        self.wakeups = []
        self.next_wakeup = time.time() + 60.0

    def sighup_handler(self, signum, frame):
        self.logger.info('SIGHUP received, reloading config when next idle')
        self.sighup_load_config = True

    def load_config(self):
        self.sighup_load_config = False
        with open('dsari.json') as f:
            self.config = json.load(f)
        if 'concurrency_groups' not in self.config:
            self.config['concurrency_groups'] = {}

    def reset_jobs(self):
        self.jobs = []
        now = time.time()
        for job_name in sorted(self.config['jobs']):
            job = Job(job_name)
            job.config = self.config['jobs'][job_name]
            run = Run(job, str(uuid.uuid4()))
            t = croniter_hash.croniter_hash(job.config['schedule'], start_time=now, hash_id=job_name).get_next() + (random.random() * 60.0)
            self.logger.debug('[%s] Next scheduled run: %s (%0.02fs)' % (job.name, time.strftime('%c', time.localtime(t)), (t - now)))
            run.scheduled_time = t
            job.run = run
            self.jobs.append(job)

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
                self.logger.info('[%s] SIGTERM grace (%0.02fs) exceeded, sending SIGKILL to %d' % (job.name, sigterm_grace, run.pid))
                os.kill(run.pid, signal.SIGKILL)
                run.kill_sent = True
            self.wakeups.append(now + sigkill_grace)
        elif delta > job.config['max_execution']:
            if not run.term_sent:
                self.logger.info('[%s] Max execution (%0.02fs) exceeded, sending SIGTERM to %d' % (job.name, job.config['max_execution'], run.pid))
                os.kill(run.pid, signal.SIGTERM)
                run.term_sent = True
            self.wakeups.append(now + sigterm_grace)
        else:
            self.wakeups.append(run.start_time + job.config['max_execution'])

    def run_child_executor(self, run):
        job = run.job
        self.db_conn.close()
        for j in self.jobs:
            if j.name == job.name:
                continue
            if hasattr(j.run, 'tempfile') and j.run.tempfile:
                j.run.tempfile.close()
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
        if not os.path.exists('%s/runs/%s' % (VAR_DIR, job.name)):
            os.makedirs('%s/runs/%s' % (VAR_DIR, job.name))
        devnull_f = open(os.devnull, 'r')
        exit_code = subprocess.call(job.config['command'], stdout=run.tempfile, stderr=run.tempfile, stdin=devnull_f)
        sys.exit(exit_code)

    def process_next_child(self):
        self.logger.debug('Waiting up to %0.02fs for running jobs' % (self.next_wakeup - time.time()))
        (child_pid, child_exit, child_resource) = wait_deadline(-1, os.WNOHANG, self.next_wakeup)
        if child_pid == 0:
            return child_pid
        job = None
        for j in self.running_jobs:
            if j.run.pid == child_pid:
                job = j
                break
        if not job:
            return child_pid
        now = time.time()
        run = job.run
        start_time = run.start_time
        stop_time = now
        self.logger.info('[%s %s] Finished with status %d in %0.02fs' % (job.name, run.id, child_exit, (stop_time - start_time)))
        #self.logger.debug('[%s %s] Resources: %s' % (job.name, run.id, repr(child_resource)))
        self.db_conn.execute('INSERT INTO runs (job_name, run_id, start_time, stop_time, exit_code, trigger_type, trigger_data) VALUES (?, ?, ?, ?, ?, ?, ?)', (job.name, run.id, start_time, stop_time, child_exit, run.trigger_type, json.dumps(run.trigger_data)))
        self.db_conn.commit()
        run.tempfile.close()
        shutil.copyfile(run.tempfile.name, '%s/runs/%s/%s.output' % (VAR_DIR, job.name, run.id))
        os.remove(run.tempfile.name)
        self.running_jobs.remove(job)
        if run.concurrency_group and job in self.running_groups[run.concurrency_group]:
            self.running_groups[run.concurrency_group].remove(job)
        run = Run(job, str(uuid.uuid4()))
        t = croniter_hash.croniter_hash(job.config['schedule'], start_time=now, hash_id=job.name).get_next() + (random.random() * 60.0)
        run.scheduled_time = t
        job.run = run
        self.logger.debug('[%s] Next scheduled run: %s (%0.02fs)' % (job.name, time.strftime('%c', time.localtime(t)), (t - now)))
        return child_pid

    def process_job(self, job):
        now = time.time()
        run = job.run
        if os.path.exists('%s/trigger/%s' % (VAR_DIR, job.name)):
            self.logger.info('[%s] Trigger detected, scheduling for now' % job.name)
            run.trigger_type = 'file'
            with open('%s/trigger/%s' % (VAR_DIR, job.name)) as f:
                os.remove('%s/trigger/%s' % (VAR_DIR, job.name))
                try:
                    run.trigger_data = json.load(f)
                except ValueError:
                    run.trigger_data = {}
            run.scheduled_time = now
        if run.scheduled_time > now:
            self.wakeups.append(run.scheduled_time)
            return
        if job in self.running_jobs:
            self.wakeups.append(now + backoff(run.scheduled_time, now))
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
        else:
            run.pid = child_pid
            self.running_jobs.append(job)
            if run.concurrency_group:
                self.running_groups[run.concurrency_group].append(job)

    def process_wakeups(self):
        self.next_wakeup = time.time() + 60.0
        for wakeup in self.wakeups:
            if wakeup < self.next_wakeup:
                self.next_wakeup = wakeup

    def loop(self):
        while True:
            self.wakeups = []
            for job in self.jobs:
                self.process_job(job)

            for job in self.running_jobs:
                self.process_run_execution_time(job.run)

            self.process_wakeups()

            if len(self.running_jobs) > 0:
                while (len(self.running_jobs) > 0) and (self.next_wakeup > time.time()):
                    if self.process_next_child() == 0:
                        break
            else:
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
