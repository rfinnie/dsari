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
import jinja2
import datetime
import json
import sqlite3
import argparse
import logging

import __init__ as dsari

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
        '--version', action='store_true',
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


def main(argv):
    args = parse_args()
    if args.version:
        print __version__
        return
    config = dsari.Config()
    config.load_dir(args.config_dir)

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    lh_console = logging.StreamHandler()
    lh_console_formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    lh_console.setFormatter(lh_console_formatter)
    if args.debug:
        lh_console.setLevel(logging.DEBUG)
    else:
        lh_console.setLevel(logging.INFO)
    logger.addHandler(lh_console)

    if not os.path.exists(os.path.join(config.data_dir, 'dsari.sqlite3')):
        return

    if config.template_dir:
        loader = jinja2.ChoiceLoader(
            jinja2.FileSystemLoader(config.template_dir),
            jinja2.PackageLoader('dsari'),
        )
    else:
        loader = jinja2.PackageLoader('dsari')

    templates = jinja2.Environment(
        autoescape=guess_autoescape,
        loader=loader,
        extensions=['jinja2.ext.autoescape'],
    )
    templates.globals['now'] = datetime.datetime.now()

    run_template = templates.get_template('run.html')

    jobs = {job for job in config.jobs if job.render_reports}
    job_runs = {}
    for job in jobs:
        job_runs[job.name] = []
    job_map = {job.name: job for job in jobs}
    runs = []
    jobs_written = []
    db_conn = sqlite3.connect(os.path.join(config.data_dir, 'dsari.sqlite3'))
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
    for (
        job_name,
        run_id,
        schedule_time,
        start_time,
        stop_time,
        exit_code,
        trigger_type,
        trigger_data
    ) in db_conn.execute(sql_statement):
        if job_name not in job_map:
            logger.debug('Cannot find job %s' % job_name)
            continue
        job = job_map[job_name]
        if not job.render_reports:
            logger.debug('Ignoring %s %s' % (job_name, run_id))
            continue
        run = dsari.Run(job, run_id)
        run.schedule_time = schedule_time
        run.schedule_datetime = datetime.datetime.fromtimestamp(schedule_time)
        run.start_time = start_time
        run.start_datetime = datetime.datetime.fromtimestamp(start_time)
        run.stop_time = stop_time
        run.stop_datetime = datetime.datetime.fromtimestamp(stop_time)
        run.exit_code = exit_code
        run.trigger_type = trigger_type
        run.trigger_data = json.loads(trigger_data)
        job_runs[job.name].append(run)
        runs.append(run)
        job.last_run_datetime = run.start_datetime
        job.last_duration_datetime = run.stop_datetime - run.start_datetime
        if exit_code == 0:
            job.last_successful_datetime = datetime.datetime.fromtimestamp(start_time)
        run_html_filename = os.path.join(config.data_dir, 'html', job.name, run.id, 'index.html')
        if config.report_html_gz:
            run_html_filename = '%s.gz' % run_html_filename
        if os.path.isfile(run_html_filename):
            if not args.regenerate:
                continue
        if not os.path.exists(os.path.join(config.data_dir, 'html', job.name, run.id)):
            os.makedirs(os.path.join(config.data_dir, 'html', job.name, run.id))
        run.output = read_output(os.path.join(config.data_dir, 'runs', job.name, run.id, 'output.txt'))
        logger.info('Writing %s' % run_html_filename)
        context = {
            'job': job,
            'run': run,
        }
        write_html_file(run_html_filename, run_template.render(context))
        if job not in jobs_written:
            jobs_written.append(job)

    for job in jobs:
        if job not in jobs_written:
            if not args.regenerate:
                continue
        context = {
            'job': job,
            'runs': sorted(job_runs[job.name], key=lambda run: run.stop_time, reverse=True),
        }
        if not os.path.exists(os.path.join(config.data_dir, 'html', job.name)):
            os.makedirs(os.path.join(config.data_dir, 'html', job.name))
        job_template = templates.get_template('job.html')
        job_html_filename = os.path.join(config.data_dir, 'html', job.name, 'index.html')
        if config.report_html_gz:
            job_html_filename = '%s.gz' % job_html_filename
        logger.info('Writing %s' % job_html_filename)
        write_html_file(job_html_filename, job_template.render(context))

    if (len(jobs_written) > 0) or args.regenerate:
        context = {
            'jobs': sorted(jobs, key=lambda job: job.name),
            'runs': sorted(runs, key=lambda run: run.stop_time, reverse=True)[:25],
        }
        index_template = templates.get_template('index.html')
        index_html_filename = os.path.join(config.data_dir, 'html', 'index.html')
        if config.report_html_gz:
            index_html_filename = '%s.gz' % index_html_filename
        logger.info('Writing %s' % index_html_filename)
        write_html_file(index_html_filename, index_template.render(context))
