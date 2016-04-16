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
import jinja2
import datetime
import json
import sqlite3
import argparse
import logging

import dsari

import gzip
HAS_LZMA = True
try:
    import lzma
except ImportError:
    HAS_LZMA = False

__version__ = dsari.__version__


def guess_autoescape(template_name):
    if template_name is None or '.' not in template_name:
        return False
    (base, ext) = template_name.rsplit('.', 1)
    if ext == 'jinja2':
        (base, ext) = base.rsplit('.', 1)
    return ext in ('html', 'htm', 'xml')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Do Something and Record It - report renderer (%s)' % __version__,
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
        '--regenerate', '-r', action='store_true',
        help='regenerate all reports',
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='output additional debugging information',
    )
    return parser.parse_args()


def read_output(filename):
    if os.path.isfile(filename):
        with open(filename, 'rb') as f:
            return f.read().decode('utf-8')
    elif os.path.isfile('%s.gz' % filename):
        with gzip.open('%s.gz' % filename, 'rb') as f:
            return f.read().decode('utf-8')
    elif HAS_LZMA and os.path.isfile('%s.xz' % filename):
        with open('%s.xz' % filename, 'rb') as f:
            return lzma.LZMADecompressor().decompress(f.read()).decode('utf-8')
    else:
        return None


def write_html_file(filename, content):
    if filename.endswith('.gz'):
        with gzip.open(filename, 'wb') as f:
            f.write(content.encode('utf-8'))
    else:
        with open(filename, 'wb') as f:
            f.write(content.encode('utf-8'))


class Renderer():
    def __init__(self, args):
        self.args = args
        self.config = dsari.Config()
        self.config.load_dir(self.args.config_dir)

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

        if not os.path.exists(os.path.join(self.config.data_dir, 'dsari.sqlite3')):
            return

        if self.config.template_dir:
            loader = jinja2.ChoiceLoader(
                jinja2.FileSystemLoader(self.config.template_dir),
                jinja2.PackageLoader('dsari'),
            )
        else:
            loader = jinja2.PackageLoader('dsari')

        self.templates = jinja2.Environment(
            autoescape=guess_autoescape,
            loader=loader,
            extensions=['jinja2.ext.autoescape'],
        )
        self.templates.globals['now'] = datetime.datetime.now()

        self.db_conn = sqlite3.connect(os.path.join(self.config.data_dir, 'dsari.sqlite3'))
        self.db_conn.row_factory = sqlite3.Row

    def render(self):
        self.jobs = {job.name: job for job in self.config.jobs.values() if job.render_reports}
        self.job_runs = {}
        for job in self.jobs.values():
            self.job_runs[job.name] = []
        self.runs = []
        self.jobs_written = []

        self.render_runs()
        self.render_jobs()
        self.render_index()

    def render_runs(self):
        self.run_template = self.templates.get_template('run.html')
        sql_statement = """
            SELECT
                job_name,
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code,
                trigger_type,
                trigger_data
            FROM
                runs
            ORDER BY
                start_time
        """
        for db_result in self.db_conn.execute(sql_statement):
            if db_result['job_name'] not in self.jobs:
                self.logger.debug('Cannot find job %s' % db_result['job_name'])
                continue
            job = self.jobs[db_result['job_name']]
            run = self.build_run_object(job, db_result)
            self.render_run(run)

    def render_run(self, run):
        job = run.job
        self.job_runs[job.name].append(run)
        self.runs.append(run)
        job.last_run_datetime = run.start_datetime
        job.last_duration_datetime = run.stop_datetime - run.start_datetime
        if run.exit_code == 0:
            job.last_successful_run_datetime = run.start_datetime
        run_html_filename = os.path.join(self.config.data_dir, 'html', job.name, run.id, 'index.html')
        if self.config.report_html_gz:
            run_html_filename = '%s.gz' % run_html_filename
        if os.path.isfile(run_html_filename):
            if not self.args.regenerate:
                return
        if not os.path.exists(os.path.join(self.config.data_dir, 'html', job.name, run.id)):
            os.makedirs(os.path.join(self.config.data_dir, 'html', job.name, run.id))
        run.output = read_output(os.path.join(self.config.data_dir, 'runs', job.name, run.id, 'output.txt'))
        self.logger.info('Writing %s' % run_html_filename)
        context = {
            'job': job,
            'run': run,
        }
        write_html_file(run_html_filename, self.run_template.render(context))
        if job not in self.jobs_written:
            self.jobs_written.append(job)

    def build_run_object(self, job, db_result):
        run = dsari.Run(job, db_result['run_id'])
        run.schedule_time = db_result['schedule_time']
        run.schedule_datetime = datetime.datetime.fromtimestamp(run.schedule_time)
        run.start_time = db_result['start_time']
        run.start_datetime = datetime.datetime.fromtimestamp(run.start_time)
        run.stop_time = db_result['stop_time']
        run.stop_datetime = datetime.datetime.fromtimestamp(run.stop_time)
        run.exit_code = db_result['exit_code']
        run.trigger_type = db_result['trigger_type']
        run.trigger_data = json.loads(db_result['trigger_data'])
        return run

    def render_jobs(self):
        self.job_template = self.templates.get_template('job.html')
        for job in self.jobs.values():
            if job not in self.jobs_written:
                if not self.args.regenerate:
                    continue
            self.render_job(job)

    def render_job(self, job):
        context = {
            'job': job,
            'runs': sorted(self.job_runs[job.name], key=lambda run: run.stop_time, reverse=True),
        }
        if not os.path.exists(os.path.join(self.config.data_dir, 'html', job.name)):
            os.makedirs(os.path.join(self.config.data_dir, 'html', job.name))
        job_html_filename = os.path.join(self.config.data_dir, 'html', job.name, 'index.html')
        if self.config.report_html_gz:
            job_html_filename = '%s.gz' % job_html_filename
        self.logger.info('Writing %s' % job_html_filename)
        write_html_file(job_html_filename, self.job_template.render(context))

    def render_index(self):
        self.index_template = self.templates.get_template('index.html')
        if (len(self.jobs_written) > 0) or self.args.regenerate:
            context = {
                'jobs': self.jobs,
                'runs': sorted(self.runs, key=lambda run: run.stop_time, reverse=True)[:25],
            }
            index_html_filename = os.path.join(self.config.data_dir, 'html', 'index.html')
            if self.config.report_html_gz:
                index_html_filename = '%s.gz' % index_html_filename
            self.logger.info('Writing %s' % index_html_filename)
            write_html_file(index_html_filename, self.index_template.render(context))


def main():
    args = parse_args()
    r = Renderer(args)
    r.render()


if __name__ == '__main__':
    import sys
    sys.exit(main())
