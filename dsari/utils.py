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
import json
import copy


if __file__.startswith('/usr/lib'):
    DEFAULT_CONFIG_DIR = '/etc/dsari'
    DEFAULT_DATA_DIR = '/var/lib/dsari'
elif __file__.startswith('/usr/local/lib'):
    DEFAULT_CONFIG_DIR = '/usr/local/etc/dsari'
    DEFAULT_DATA_DIR = '/usr/local/lib/dsari'
else:
    DEFAULT_CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.dsari', 'etc')
    DEFAULT_DATA_DIR = os.path.join(os.path.expanduser('~'), '.dsari', 'var')


def dict_merge(s, m):
    """Recursively merge one dict into another."""
    if not isinstance(m, dict):
        return m
    out = copy.deepcopy(s)
    for k, v in m.items():
        if k in out and isinstance(out[k], dict):
            out[k] = dict_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def json_load_file(file):
    with open(file) as f:
        try:
            return json.load(f)
        except ValueError, e:
            e.args += (file,)
            raise


def load_config(config_dir):
    config = {}
    if os.path.exists(os.path.join(config_dir, 'dsari.json')):
        config = json_load_file(os.path.join(config_dir, 'dsari.json'))
    if 'config_d' not in config:
        config['config_d'] = os.path.join(config_dir, 'config.d')
    if config['config_d'] and os.path.isdir(config['config_d']):
        config_d = config['config_d']
        config_files = [
            os.path.join(config_d, fn)
            for fn in os.listdir(config_d)
            if fn.endswith('.json')
            and os.path.isfile(os.path.join(config_d, fn))
            and os.access(os.path.join(config_d, fn), os.R_OK)
        ]
        config_files.sort()
        for file in config_files:
            config = dict_merge(config, json_load_file(file))

    if 'jobs' not in config:
        config['jobs'] = {}
    if 'job_groups' not in config:
        config['job_groups'] = {}
    if 'concurrency_groups' not in config:
        config['concurrency_groups'] = {}

    if 'data_dir' not in config:
        config['data_dir'] = DEFAULT_DATA_DIR
    if 'template_dir' not in config:
        config['template_dir'] = None
    if 'report_html_gz' not in config:
        config['report_html_gz'] = False

    if 'shutdown_kill_runs' not in config:
        config['shutdown_kill_runs'] = False
    if 'shutdown_kill_grace' not in config:
        config['shutdown_kill_grace'] = None

    for job_group_name in config['job_groups'].keys():
        job_template = copy.deepcopy(config['job_groups'][job_group_name])
        del(config['job_groups'][job_group_name])
        if 'job_names' not in job_template:
            continue
        for job_name in job_template['job_names']:
            config['jobs'][job_name] = copy.deepcopy(job_template)
            config['jobs'][job_name]['job_group'] = job_group_name
            del(config['jobs'][job_name]['job_names'])

    for job_name in config['jobs'].keys():
        if '/' in job_name:
            del(config['jobs'][job_name])
            continue
        if job_name in ('.', '..'):
            del(config['jobs'][job_name])
            continue
        if 'command' not in config['jobs'][job_name]:
            continue
        if type(config['jobs'][job_name]['command']) != list:
            continue
        if 'schedule' not in config['jobs'][job_name]:
            config['jobs'][job_name]['schedule'] = None
        if 'concurrency_groups' not in config['jobs'][job_name]:
            config['jobs'][job_name]['concurrency_groups'] = []
        if 'max_execution' not in config['jobs'][job_name]:
            config['jobs'][job_name]['max_execution'] = None
        if 'max_execution_grace' not in config['jobs'][job_name]:
            config['jobs'][job_name]['max_execution_grace'] = 60.0
        if 'environment' not in config['jobs'][job_name]:
            config['jobs'][job_name]['environment'] = {}
        if 'render_reports' not in config['jobs'][job_name]:
            config['jobs'][job_name]['render_reports'] = True
        if 'command_append_run' not in config['jobs'][job_name]:
            config['jobs'][job_name]['command_append_run'] = False
        if 'jenkins_environment' not in config['jobs'][job_name]:
            config['jobs'][job_name]['jenkins_environment'] = False
        if 'job_group' not in config['jobs'][job_name]:
            config['jobs'][job_name]['job_group'] = None

    return config
