#!/usr/bin/env python3

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
import copy
import re
import shlex

import dsari
from dsari import utils


if 'DSARI_HOME' in os.environ:
    DEFAULT_CONFIG_DIR = os.path.join(os.environ['DSARI_HOME'], 'etc')
    DEFAULT_DATA_DIR = os.path.join(os.environ['DSARI_HOME'], 'var')
elif __file__.startswith('/usr/lib'):
    DEFAULT_CONFIG_DIR = '/etc/dsari'
    DEFAULT_DATA_DIR = '/var/lib/dsari'
elif __file__.startswith('/usr/local/lib'):
    DEFAULT_CONFIG_DIR = '/usr/local/etc/dsari'
    DEFAULT_DATA_DIR = '/usr/local/lib/dsari'
else:
    DEFAULT_CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.dsari', 'etc')
    DEFAULT_DATA_DIR = os.path.join(os.path.expanduser('~'), '.dsari', 'var')


def get_config(config_dir=DEFAULT_CONFIG_DIR):
    config = Config()
    config.load_dir(config_dir)
    return config


class ConfigError(RuntimeError):
    pass


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
        self.environment = {}
        self.database = {
            'type': 'sqlite3',
            'file': None,
        }

    def is_valid_name(self, job_name):
        if '/' in job_name:
            return False
        if job_name in ('.', '..'):
            return False
        if len(job_name) > 64:
            return False
        if not re.search('^([- A-Za-z0-9_+.:@]+)$', job_name):
            return False
        return True

    def load_dir(self, config_dir=DEFAULT_CONFIG_DIR):
        config = {}
        if os.path.exists(os.path.join(config_dir, 'dsari.json')):
            try:
                config = utils.json_load_file(os.path.join(config_dir, 'dsari.json'))
            except ValueError as e:
                raise ConfigError(e)
        self.config_d = os.path.join(config_dir, 'config.d')
        if 'config_d' in config:
            self.config_d = config['config_d']
        if self.config_d and os.path.isdir(self.config_d):
            config_d = self.config_d
            config_files = [
                os.path.join(config_d, fn)
                for fn in os.listdir(config_d)
                if fn.endswith('.json') and
                os.path.isfile(os.path.join(config_d, fn)) and
                os.access(os.path.join(config_d, fn), os.R_OK)
            ]
            config_files.sort()
            for file in config_files:
                try:
                    config = utils.dict_merge(config, utils.json_load_file(file))
                except ValueError as e:
                    raise ConfigError(e)
        self.load(config)

    def load(self, config):
        valid_values = {
            'data_dir': (str,),
            'template_dir': (str,),
            'report_html_gz': (str,),
            'shutdown_kill_runs': (bool,),
            'shutdown_kill_grace': (int, float),
            'environment': (dict,),
            'database': (dict,),
        }
        valid_values_job = {
            'command': (list, str),
            'schedule': (type(None),) + (str,),
            'max_execution': (int, float),
            'max_execution_grace': (int, float),
            'environment': (dict,),
            'render_reports': (bool,),
            'command_append_run': (bool,),
            'jenkins_environment': (bool,),
            'job_group': (str,),
            'concurrent_runs': (bool,),
        }
        valid_values_concurrency_group = {
            'max': (int,),
        }
        self.raw_config = copy.deepcopy(config)
        for k in valid_values.keys():
            if k in config:
                if type(config[k]) not in valid_values[k]:
                    raise ConfigError('{}: Invalid value {} (expected {})'.format(
                        k,
                        repr(type(config[k])),
                        repr(valid_values[k]))
                    )
                if k in ('shutdown_kill_grace',):
                    setattr(self, k, utils.seconds_to_td(config[k]))
                elif k == 'environment':
                    try:
                        config[k] = utils.validate_environment_dict(copy.deepcopy(config[k]))
                    except (KeyError, ValueError) as e:
                        raise ConfigError('Invalid environment: {}'.format(str(e)))
                        return
                else:
                    setattr(self, k, config[k])

        concurrency_groups = {}
        if 'concurrency_groups' in config:
            concurrency_groups = config['concurrency_groups']

        for concurrency_group_name in concurrency_groups.keys():
            if not self.is_valid_name(concurrency_group_name):
                raise ConfigError('Concurrency group {}: Invalid name'.format(concurrency_group_name))
            concurrency_group = dsari.ConcurrencyGroup(concurrency_group_name)
            for k in valid_values_concurrency_group.keys():
                if k in concurrency_groups[concurrency_group_name]:
                    if type(concurrency_groups[concurrency_group_name][k]) not in valid_values_concurrency_group[k]:
                        raise ConfigError('Concurrency group {}: {}: Invalid value {} (expected {})'.format(
                            concurrency_group_name,
                            k,
                            repr(type(concurrency_groups[concurrency_group_name][k])),
                            repr(valid_values_concurrency_group[k]))
                        )
                    setattr(concurrency_group, k, concurrency_groups[concurrency_group_name][k])
            self.concurrency_groups.append(concurrency_group)

        jobs = {}
        if 'jobs' in config:
            jobs = config['jobs']
        job_groups = {}
        if 'job_groups' in config:
            job_groups = config['job_groups']

        for job_group_name in job_groups:
            if not self.is_valid_name(job_group_name):
                raise ConfigError('Job group {}: Invalid name'.format(job_group_name))
            job_template = copy.deepcopy(job_groups[job_group_name])
            if 'job_names' not in job_template:
                raise ConfigError('Job group {}: job_names required'.format(job_group_name))
            for job_name in job_template['job_names']:
                jobs[job_name] = copy.deepcopy(job_template)
                jobs[job_name]['job_group'] = job_group_name
                del(jobs[job_name]['job_names'])

        concurrency_groups_hash = {
            concurrency_group.name: concurrency_group
            for concurrency_group in self.concurrency_groups
        }
        for job_name in jobs.keys():
            if not self.is_valid_name(job_name):
                raise ConfigError('Job {}: Invalid name'.format(job_name))
            if 'command' not in jobs[job_name]:
                raise ConfigError('Job {}: command required'.format(job_name))
            if type(jobs[job_name]['command']) == str:
                jobs[job_name]['command'] = shlex.split(jobs[job_name]['command'])
            job = dsari.Job(job_name)
            for k in valid_values_job.keys():
                if k in jobs[job_name]:
                    if type(jobs[job_name][k]) not in valid_values_job[k]:
                        raise ConfigError('Job {}: {}: Invalid value {} (expected {})'.format(
                            job_name,
                            k,
                            repr(type(jobs[job_name][k])),
                            repr(valid_values_job[k]))
                        )
                    if k in ('max_execution', 'max_execution_grace'):
                        setattr(job, k, utils.seconds_to_td(jobs[job_name][k]))
                    elif k == 'environment':
                        try:
                            jobs[job_name][k] = utils.validate_environment_dict(copy.deepcopy(jobs[job_name][k]))
                        except (KeyError, ValueError) as e:
                            raise ConfigError('Job {}: Invalid environment: {}'.format(job_name, str(e)))
                            return
                    else:
                        setattr(job, k, jobs[job_name][k])
            job_concurrency_group_names = []
            if 'concurrency_groups' in jobs[job_name]:
                job_concurrency_group_names = jobs[job_name]['concurrency_groups']
            for concurrency_group_name in job_concurrency_group_names:
                if not self.is_valid_name(concurrency_group_name):
                    raise ConfigError('Concurrency group {}: Invalid name'.format(job_group_name))
                if concurrency_group_name not in concurrency_groups_hash:
                    concurrency_group = dsari.ConcurrencyGroup(concurrency_group_name)
                    concurrency_groups_hash[concurrency_group_name] = concurrency_group
                    self.concurrency_groups.append(concurrency_group)
                else:
                    concurrency_group = concurrency_groups_hash[concurrency_group_name]
                job.concurrency_groups.append(concurrency_group)
            if job.schedule is not None:
                try:
                    utils.get_next_schedule_time(job.schedule, job.name)
                except Exception as e:
                    raise ConfigError('Job {}: Invalid schedule ({}): {}: {}'.format(job.name, job.schedule, type(e), str(e)))
            self.jobs.append(job)
