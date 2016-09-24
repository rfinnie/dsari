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

from __future__ import print_function
import os
import json
import argparse

try:
    from shlex import quote as shquote
except ImportError:
    from pipes import quote as shquote

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

import dsari
import dsari.config
import dsari.database
from dsari.utils import td_to_seconds

__version__ = dsari.__version__


def json_pretty_print(v):
    return json.dumps(v, sort_keys=True, indent=4, separators=(',', ': '))


def parse_args():
    parser = argparse.ArgumentParser(
        description='Do Something and Record It - job/run information (%s)' % __version__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--version', action='version',
        version=__version__,
        help='report the program version',
    )
    parser.add_argument(
        '--config-dir', '-c', type=str, default=dsari.config.DEFAULT_CONFIG_DIR,
        help='configuration directory for dsari.json',
    )

    subparsers = parser.add_subparsers(
        dest='subcommand',
    )
    subparsers.required = True
    parser_list_jobs = subparsers.add_parser(
        'list-jobs',
        help='list jobs',
    )
    parser_list_runs = subparsers.add_parser(
        'list-runs',
        help='list runs',
    )
    parser_get_output = subparsers.add_parser(
        'get-run-output',
        help='get run output',
    )
    subparsers.add_parser(
        'check-config',
        help='validate configuration'
    )
    parser_dump_config = subparsers.add_parser(
        'dump-config',
        help='dump a compiled version of the loaded config'
    )
    parser_dump_config.add_argument(
        '--raw', action='store_true',
        help='output raw config instead of compiled/normalized config',
    )

    for p in (parser_list_jobs, parser_list_runs):
        p.add_argument(
            '--job', type=str, action='append',
            help='job name to filter (can be given multiple times)',
        )
        choices = ['tabular', 'json']
        if HAS_YAML:
            choices.append('yaml')
        p.add_argument(
            '--format', type=str, choices=choices,
            default='tabular',
            help='output format',
        )

    parser_get_output.add_argument(
        'run', type=str, default=None,
        help='run UUID',
    )

    parser_list_runs.add_argument(
        '--run', type=str, action='append',
        help='run ID to filter (can be given multiple times)',
    )

    parser_list_runs.add_argument(
        '--running', action='store_true',
        help='list currently running runs',
    )

    args = parser.parse_args()
    args.parser = parser

    return args


class Info():
    def __init__(self, args):
        self.args = args
        self.config = dsari.config.get_config(self.args.config_dir)
        self.db = dsari.database.get_database(self.config)

    def dump_jobs(self, filter=None):
        jobs = {}
        for job in self.config.jobs:
            if filter is not None and job.name not in filter:
                continue
            jobs[job.name] = {
                'command': job.command,
                'command_append_run': job.command_append_run,
                'schedule': job.schedule,
                'environment': job.environment,
                'max_execution': job.max_execution,
                'max_execution_grace': job.max_execution_grace,
                'concurrency_groups': sorted([concurrency_group.name for concurrency_group in job.concurrency_groups]),
                'render_reports': job.render_reports,
                'jenkins_environment': job.jenkins_environment,
                'job_group': job.job_group,
                'concurrent_runs': job.concurrent_runs,
            }
            for k in ('max_execution', 'max_execution_grace'):
                if jobs[job.name][k] is not None:
                    jobs[job.name][k] = td_to_seconds(jobs[job.name][k])
        return jobs

    def main(self):
        if self.args.subcommand == 'dump-config':
            if self.args.raw:
                config = self.config.raw_config
            else:
                config = {
                    'jobs': self.dump_jobs(),
                    'concurrency_groups': {},
                }
                for attr in (
                    'config_d',
                    'data_dir',
                    'template_dir',
                    'report_html_gz',
                    'shutdown_kill_runs',
                    'shutdown_kill_grace',
                    'environment',
                    'database',
                ):
                    config[attr] = getattr(self.config, attr)
                for attr in ('shutdown_kill_grace',):
                    if config[attr] is not None:
                        config[attr] = td_to_seconds(config[attr])
                for concurrency_group in self.config.concurrency_groups:
                    config['concurrency_groups'][concurrency_group.name] = {
                        'max': concurrency_group.max,
                    }
            print(json_pretty_print(config))
        elif self.args.subcommand == 'check-config':
            print('Config OK')
        elif self.args.subcommand == 'list-jobs':
            if self.args.job:
                jobs = self.dump_jobs(self.args.job)
            else:
                jobs = self.dump_jobs()
            if self.args.format == 'json':
                print(json_pretty_print(jobs))
            elif self.args.format == 'yaml':
                print(yaml.safe_dump(jobs, default_flow_style=False))
            else:
                for job_name in sorted(jobs):
                    job = jobs[job_name]
                    schedule = job['schedule'] or ''
                    print('%s\t%s\t%s' % (
                        job_name,
                        schedule,
                        ' '.join([shquote(x) for x in job['command']]),
                    ))
        elif self.args.subcommand == 'list-runs':
            job_names = self.args.job
            run_ids = self.args.run
            runs_running = self.args.running
            runs = self.db.get_runs(job_names=job_names, run_ids=run_ids, runs_running=runs_running)
            if self.args.format in ('json', 'yaml'):
                out = {}
                for run in runs:
                    out[run.id] = {
                        'job_name': run.job.name,
                        'schedule_time': run.schedule_time.isoformat(),
                        'start_time': run.start_time.isoformat(),
                        'stop_time': None,
                        'exit_code': None,
                        'trigger_type': run.trigger_type,
                        'trigger_data': run.trigger_data,
                        'run_data': run.run_data,
                    }
                    if not runs_running:
                        out[run.id]['stop_time'] = run.stop_time.isoformat()
                        out[run.id]['exit_code'] = run.exit_code
                if self.args.format == 'json':
                    print(json_pretty_print(out))
                elif self.args.format == 'yaml':
                    print(yaml.safe_dump(out, default_flow_style=False))
            else:
                if runs_running:
                    for run in sorted(runs, key=lambda run: run.start_time):
                        print('%s\t%s\t%s\t%s\t%s\t%s\t%s' % (
                            run.id,
                            run.job.name,
                            '',
                            run.trigger_type,
                            run.schedule_time.isoformat(),
                            run.start_time.isoformat(),
                            '',
                        ))
                else:
                    for run in sorted(runs, key=lambda run: run.stop_time):
                        print('%s\t%s\t%s\t%s\t%s\t%s\t%s' % (
                            run.id,
                            run.job.name,
                            run.exit_code,
                            run.trigger_type,
                            run.schedule_time.isoformat(),
                            run.start_time.isoformat(),
                            run.stop_time.isoformat(),
                        ))

        elif self.args.subcommand == 'get-run-output':
            run_id = self.args.run
            runs = self.db.get_runs(run_ids=[run_id])
            if len(runs) == 0:
                self.args.parser.error('Cannot find run ID %s' % run_id)
            run = runs[0]
            fn = os.path.join(self.config.data_dir, 'runs', run.job.name, run.id, 'output.txt')
            with open(fn) as f:
                for l in f:
                    print(l, end='')


def main():
    args = parse_args()
    r = Info(args)
    r.main()


if __name__ == '__main__':
    import sys
    sys.exit(main())
