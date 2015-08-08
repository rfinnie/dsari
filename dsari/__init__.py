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
import copy
import re
import binascii

import utils

__version__ = '1.2.0'

if __file__.startswith('/usr/lib'):
    DEFAULT_CONFIG_DIR = '/etc/dsari'
    DEFAULT_DATA_DIR = '/var/lib/dsari'
elif __file__.startswith('/usr/local/lib'):
    DEFAULT_CONFIG_DIR = '/usr/local/etc/dsari'
    DEFAULT_DATA_DIR = '/usr/local/lib/dsari'
else:
    DEFAULT_CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.dsari', 'etc')
    DEFAULT_DATA_DIR = os.path.join(os.path.expanduser('~'), '.dsari', 'var')


class ConcurrencyGroup():
    def __init__(self, name):
        self.name = name
        self.max = 1

    def __repr__(self):
        return '<ConcurrencyGroup %s (%s)>' % (self.name, self.max)


class Job():
    def __init__(self, name):
        self.name = name
        self.command = []
        self.schedule = None
        self.subsecond_offset = 0.0
        self.concurrency_groups = []
        self.max_execution = None
        self.max_execution_grace = 60.0
        self.environment = {}
        self.render_reports = True
        self.command_append_run = False
        self.jenkins_environment = False
        self.job_group = None

    def __repr__(self):
        if self.schedule:
            return '<Job %s (%s)>' % (self.name, self.schedule)
        else:
            return '<Job %s>' % self.name


class Run():
    def __init__(self, job, id):
        self.job = job
        self.id = id
        self.schedule_time = None
        self.trigger_type = None
        self.trigger_data = {}
        self.respawn = False
        self.concurrency_group = None
        self.start_time = None
        self.stop_time = None
        self.exit_code = None
        self.output = None

    def __repr__(self):
        return '<Run %s (%s)>' % (self.id, self.job.name)


class Config():
    def __init__(self):
        self.raw_config = {}

        self.jobs = []
        self.concurrency_groups = []
        self.config_d = None
        self.data_dir = DEFAULT_DATA_DIR
        self.template_dir = None
        self.report_html_gz = False
        self.shutdown_kill_runs = False
        self.shutdown_kill_grace = None

    def load_dir(self, config_dir=DEFAULT_CONFIG_DIR):
        config = {}
        if os.path.exists(os.path.join(config_dir, 'dsari.json')):
            config = utils.json_load_file(os.path.join(config_dir, 'dsari.json'))
        self.config_d = os.path.join(config_dir, 'config.d')
        if 'config_d' in config:
            self.config_d = config['config_d']
        if self.config_d and os.path.isdir(self.config_d):
            config_d = self.config_d
            config_files = [
                os.path.join(config_d, fn)
                for fn in os.listdir(config_d)
                if fn.endswith('.json')
                and os.path.isfile(os.path.join(config_d, fn))
                and os.access(os.path.join(config_d, fn), os.R_OK)
            ]
            config_files.sort()
            for file in config_files:
                config = utils.dict_merge(config, utils.json_load_file(file))
        self.load(config)

    def load(self, config):
        self.raw_config = config
        for k in ('data_dir', 'template_dir', 'report_html_gz', 'shutdown_kill_runs', 'shutdown_kill_grace'):
            if k in config:
                setattr(self, k, config[k])

        concurrency_groups = {}
        if 'concurrency_groups' in config:
            concurrency_groups = config['concurrency_groups']

        for concurrency_group_name in concurrency_groups.keys():
            concurrency_group = ConcurrencyGroup(concurrency_group_name)
            for k in ('max',):
                if k in concurrency_groups[concurrency_group_name]:
                    setattr(concurrency_group, k, concurrency_groups[concurrency_group_name][k])
            self.concurrency_groups.append(concurrency_group)

        jobs = {}
        if 'jobs' in config:
            jobs = config['jobs']
        job_groups = {}
        if 'job_groups' in config:
            job_groups = config['job_groups']

        for job_group_name in job_groups:
            job_template = copy.deepcopy(job_groups[job_group_name])
            if 'job_names' not in job_template:
                continue
            for job_name in job_template['job_names']:
                jobs[job_name] = copy.deepcopy(job_template)
                jobs[job_name]['job_group'] = job_group_name
                del(jobs[job_name]['job_names'])

        for job_name in jobs.keys():
            if '/' in job_name:
                continue
            if job_name in ('.', '..'):
                continue
            if 'command' not in jobs[job_name]:
                continue
            if type(jobs[job_name]['command']) != list:
                continue
            if (len(job_name) > 64) or (not re.search('^([- A-Za-z0-9_+.:@]+)$', job_name)):
                continue
            job = Job(job_name)
            for k in (
                'command', 'schedule', 'max_execution', 'max_execution_grace',
                'environment', 'render_reports', 'command_append_run',
                'jenkins_environment', 'job_group'
            ):
                if k in jobs[job_name]:
                    setattr(job, k, jobs[job_name][k])
            job_concurrency_group_names = []
            if 'concurrency_groups' in jobs[job_name]:
                job_concurrency_group_names = jobs[job_name]['concurrency_groups']
            concurrency_group_map = {x.name: x for x in self.concurrency_groups}
            for concurrency_group_name in job_concurrency_group_names:
                if concurrency_group_name not in concurrency_group_map:
                    concurrency_group_map[concurrency_group_name] = ConcurrencyGroup(concurrency_group_name)
                    self.concurrency_groups.append(concurrency_group_map[concurrency_group_name])
                job.concurrency_groups.append(concurrency_group_map[concurrency_group_name])
            if job.schedule:
                job.subsecond_offset = float(binascii.crc32(job.name) & 0xffffffff) / float(2**32)
                if len(job.schedule.split(' ')) == 5:
                    job.schedule = job.schedule + ' H'
            self.jobs.append(job)
