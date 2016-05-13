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
import sqlite3
import argparse
import datetime
import pipes

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

import dsari

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
        '--config-dir', '-c', type=str, default=dsari.DEFAULT_CONFIG_DIR,
        help='configuration directory for dsari.json',
    )

    subparsers = parser.add_subparsers(
        dest='subcommand',
    )
    parser_list_jobs = subparsers.add_parser(
        'list-jobs',
        help='list jobs',
    )
    parser_list_runs = subparsers.add_parser(
        'list-runs',
        help='list runs',
    )
    parser_dump_config = subparsers.add_parser(
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
        p.add_argument(
            '--format', type=str, choices=['tabular', 'json', 'yaml'],
            default='tabular',
            help='output format',
        )

    parser_list_runs.add_argument(
        '--run', type=str, action='append',
        help='run ID to filter (can be given multiple times)',
    )
    parser_list_runs.add_argument(
        '--epoch', action='store_true',
        help='output times in Unix epoch instead of ISO 8601',
    )

    args = parser.parse_args()
    args.parser = parser

    if hasattr(args, 'format') and (args.format == 'yaml') and (not HAS_YAML):
        parser.error('yaml package is not available')

    return args


class Info():
    def __init__(self, args):
        self.args = args
        self.config = dsari.Config()
        self.config.load_dir(self.args.config_dir)

        if not os.path.exists(os.path.join(self.config.data_dir, 'dsari.sqlite3')):
            return

        self.db_conn = sqlite3.connect(os.path.join(self.config.data_dir, 'dsari.sqlite3'))
        self.db_conn.row_factory = sqlite3.Row

    def dump_jobs(self, filter=None):
        jobs = {}
        for job in self.config.jobs.values():
            if filter is not None and job.name not in filter:
                continue
            jobs[job.name] = {
                'command': job.command,
                'command_append_run': job.command_append_run,
                'schedule': job.schedule,
                'environment': job.environment,
                'max_execution': job.max_execution,
                'max_execution_grace': job.max_execution_grace,
                'concurrency_groups': job.concurrency_groups.keys(),
                'render_reports': job.render_reports,
                'jenkins_environment': job.jenkins_environment,
                'job_group': job.job_group,
                'concurrent_runs': job.concurrent_runs,
            }
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
                for concurrency_group in self.config.concurrency_groups:
                    config['concurrency_groups'][concurrency_group] = {
                        'max': self.config.concurrency_groups[concurrency_group].max,
                    }
            print json_pretty_print(config)
        elif self.args.subcommand == 'check-config':
            print 'Config OK'
        elif self.args.subcommand == 'list-jobs':
            if self.args.job:
                jobs = self.dump_jobs(self.args.job)
            else:
                jobs = self.dump_jobs()
            if self.args.format == 'json':
                print json_pretty_print(jobs)
            elif self.args.format == 'yaml':
                print yaml.safe_dump(jobs, default_flow_style=False)
            else:
                for job_name in jobs:
                    job = jobs[job_name]
                    schedule = job['schedule'] or ''
                    print '%s\t%s\t%s' % (
                        job_name,
                        schedule,
                        ' '.join([pipes.quote(x) for x in job['command']]),
                    )
        elif self.args.subcommand == 'list-runs':
            job_names = self.args.job
            run_ids = self.args.run
            if (job_names is None) and (run_ids is None):
                job_names = [job.name for job in self.config.jobs.values()]
            runs = self.get_runs(jobs=job_names, runs=run_ids)
            if self.args.format == 'json':
                print json_pretty_print(runs)
            elif self.args.format == 'yaml':
                print yaml.safe_dump(runs, default_flow_style=False)
            else:
                for run_id in runs:
                    run = runs[run_id]
                    print '%s\t%s\t%s\t%s\t%s\t%s\t%s' % (
                        run_id,
                        run['job_name'],
                        run['exit_code'],
                        run['trigger_type'],
                        run['schedule_time'],
                        run['start_time'],
                        run['stop_time'],
                    )

    def time_format(self, epoch):
        if self.args.epoch:
            return epoch
        else:
            return datetime.datetime.fromtimestamp(epoch).isoformat()

    def get_runs(self, jobs=None, runs=None):
        if runs is not None:
            where = 'run_id'
            where_in = runs
        elif jobs is not None:
            where = 'job_name'
            where_in = jobs
        else:
            return {}

        sql_statement = """
            SELECT
                job_name,
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
                %s in (%s)
        """ % (
            where,
            ','.join('?' * len(where_in)),
        )
        res = self.db_conn.execute(sql_statement, where_in)

        runs = {}
        for db_result in res:
            runs[db_result['run_id']] = {
                'job_name': db_result['job_name'],
                'schedule_time': self.time_format(db_result['schedule_time']),
                'start_time': self.time_format(db_result['start_time']),
                'stop_time': self.time_format(db_result['stop_time']),
                'exit_code': db_result['exit_code'],
                'trigger_type': db_result['trigger_type'],
                'trigger_data': json.loads(db_result['trigger_data']),
                'run_data': json.loads(db_result['run_data']),
            }
        return runs


def main():
    args = parse_args()
    r = Info(args)
    r.main()


if __name__ == '__main__':
    import sys
    sys.exit(main())
