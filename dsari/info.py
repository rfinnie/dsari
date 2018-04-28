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
import json
import argparse
import sys
import subprocess
import shlex

import dsari
import dsari.config
import dsari.database
from dsari.utils import td_to_seconds

__version__ = dsari.__version__


class AutoPager:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __init__(self):
        self.closed = False
        self.pager = None
        if sys.stdout.isatty():
            pager_cmd = ['pager']
            if os.environ.get('PAGER'):
                pager_cmd = shlex.split(os.environ.get('PAGER'))
            env = os.environ.copy()
            env.update({'LESS': 'FRX'})
            try:
                self.pager = subprocess.Popen(
                    pager_cmd, stdin=subprocess.PIPE, stdout=sys.stdout,
                    encoding='UTF-8', env=env
                )
            except FileNotFoundError:
                pass

    def write(self, l):
        if self.closed:
            return

        if self.pager:
            try:
                self.pager.stdin.write(l)
            except KeyboardInterrupt:
                self.close()
            except BrokenPipeError:
                self.close()
        else:
            try:
                sys.stdout.write(l)
            except BrokenPipeError:
                self.close()

    def close(self):
        if self.closed:
            return

        if self.pager:
            try:
                self.pager.stdin.close()
            except BrokenPipeError:
                pass
            ret = None
            while ret is None:
                try:
                    ret = self.pager.wait()
                except KeyboardInterrupt:
                    continue

        self.closed = True


def json_pretty_print(v):
    return json.dumps(v, sort_keys=True, indent=4, separators=(',', ': '))


def parse_args():
    parser = argparse.ArgumentParser(
        description='Do Something and Record It - job/run information ({})'.format(__version__),
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
    parser_tail_output = subparsers.add_parser(
        'tail-run-output',
        help='tail run output',
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
        p.add_argument(
            '--format', type=str, choices=['tabular', 'json'],
            default='tabular',
            help='output format',
        )

    parser_get_output.add_argument(
        'run', type=str, default=None,
        help='run UUID',
    )
    parser_tail_output.add_argument(
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

    subparsers.add_parser(
        'shell',
        help='interactive shell',
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

    def cmd_dump_config(self):
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
        with AutoPager() as pager:
            print(json_pretty_print(config), file=pager)

    def cmd_check_config(self):
        print('Config OK')

    def cmd_list_jobs(self):
        if self.args.job:
            jobs = self.dump_jobs(self.args.job)
        else:
            jobs = self.dump_jobs()
        if self.args.format == 'json':
            with AutoPager() as pager:
                print(json_pretty_print(jobs), file=pager)
        else:
            with AutoPager() as pager:
                for job_name in sorted(jobs):
                    job = jobs[job_name]
                    schedule = job['schedule'] or ''
                    print('{}\t{}\t{}'.format(
                        job_name,
                        schedule,
                        ' '.join([shlex.quote(x) for x in job['command']]),
                    ), file=pager)

    def cmd_list_runs(self):
        job_names = self.args.job
        run_ids = self.args.run
        runs_running = self.args.running
        runs = self.db.get_runs(job_names=job_names, run_ids=run_ids, runs_running=runs_running)
        if self.args.format == 'json':
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
            with AutoPager() as pager:
                print(json_pretty_print(out), file=pager)
        else:
            with AutoPager() as pager:
                if runs_running:
                    for run in sorted(runs, key=lambda run: run.start_time):
                        print('{}\t{}\t{}\t{}\t{}\t{}\t{}'.format(
                            run.id,
                            run.job.name,
                            '',
                            run.trigger_type,
                            run.schedule_time.isoformat(),
                            run.start_time.isoformat(),
                            '',
                        ), file=pager)
                else:
                    for run in sorted(runs, key=lambda run: run.stop_time):
                        print('{}\t{}\t{}\t{}\t{}\t{}\t{}'.format(
                            run.id,
                            run.job.name,
                            run.exit_code,
                            run.trigger_type,
                            run.schedule_time.isoformat(),
                            run.start_time.isoformat(),
                            run.stop_time.isoformat(),
                        ), file=pager)

    def cmd_get_run_output(self):
        run_id = self.args.run
        runs = self.db.get_runs(run_ids=[run_id])
        if len(runs) == 0:
            runs = self.db.get_runs(run_ids=[run_id], runs_running=True)
            if len(runs) == 0:
                self.args.parser.error('Cannot find run ID {}'.format(run_id))
        run = runs[0]
        fn = os.path.join(self.config.data_dir, 'runs', run.job.name, run.id, 'output.txt')
        with AutoPager() as pager:
            with open(fn) as f:
                for l in f:
                    pager.write(l)

    def cmd_tail_run_output(self):
        run_id = self.args.run
        runs = self.db.get_runs(run_ids=[run_id])
        if len(runs) == 0:
            runs = self.db.get_runs(run_ids=[run_id], runs_running=True)
            if len(runs) == 0:
                self.args.parser.error('Cannot find run ID {}'.format(run_id))
        run = runs[0]
        fn = os.path.join(self.config.data_dir, 'runs', run.job.name, run.id, 'output.txt')
        os.execvp('tail', ['tail', '-f', fn])

    def cmd_shell(self):
        # readline is used transparently by code.InteractiveConsole()
        import readline  # noqa: F401
        import datetime

        vars = {
            'concurrency_groups': self.config.concurrency_groups,
            'config': self.config,
            'datetime': datetime,
            'db': self.db,
            'dsari': dsari,
            'jobs': self.config.jobs,
        }
        banner = 'Additional variables available:\n'
        for (k, v) in vars.items():
            v = vars[k]
            if type(v) == dict:
                r = 'Dictionary ({} items)'.format(len(v))
            elif type(v) == list:
                r = 'List ({} items)'.format(len(v))
            else:
                r = repr(v)
            banner += '    {}: {}\n'.format(k, r)
        banner += '\n'

        sh = None
        try:
            from IPython.terminal.embed import InteractiveShellEmbed
            sh = InteractiveShellEmbed(user_ns=vars, banner2=banner)
            sh.excepthook = sys.__excepthook__
        except ImportError:
            print('ipython not available. Using normal python shell.')

        if sh:
            sh()
        else:
            import code

            class DsariConsole(code.InteractiveConsole):
                pass

            console_vars = vars.copy().update({
                '__name__': '__console__',
                '__doc__': None,
            })
            print(banner, end='')
            DsariConsole(locals=console_vars).interact()

    def main(self):
        cmd_map = {
            'dump-config': self.cmd_dump_config,
            'check-config': self.cmd_check_config,
            'list-jobs': self.cmd_list_jobs,
            'list-runs': self.cmd_list_runs,
            'get-run-output': self.cmd_get_run_output,
            'tail-run-output': self.cmd_tail_run_output,
            'shell': self.cmd_shell,
        }
        cmd_map[self.args.subcommand]()


def main():
    args = parse_args()
    r = Info(args)
    r.main()


if __name__ == '__main__':
    sys.exit(main())
