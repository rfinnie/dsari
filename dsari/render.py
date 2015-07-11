#!/usr/bin/env python

import os
import jinja2
import datetime
import json
import sqlite3
import argparse
import logging
import utils


def guess_autoescape(template_name):
    if template_name is None or '.' not in template_name:
        return False
    (base, ext) = template_name.rsplit('.', 1)
    if ext == 'jinja2':
        (base, ext) = base.rsplit('.', 1)
    return ext in ('html', 'htm', 'xml')


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--config-dir', '-c', type=str, default=utils.DEFAULT_CONFIG_DIR)
    parser.add_argument('--debug', action='store_true')
    return parser.parse_args()


def main(argv):
    args = parse_args()
    config = utils.load_config(args.config_dir)

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

    ignore_jobs = ['test', 'test2', 'test3', 'test4']

    if 'template_dir' in config and config['template_dir']:
        loader = jinja2.ChoiceLoader(
            jinja2.FileSystemLoader(config['template_dir']),
            jinja2.PackageLoader('dsari'),
        )
    else:
        loader = jinja2.PackageLoader('dsari')

    templates = jinja2.Environment(
        autoescape=guess_autoescape,
        loader=loader,
        extensions=['jinja2.ext.autoescape'],
    )
    run_template = templates.get_template('run.html')

    runs = []
    jobs = {}
    jobs_written = []
    db_conn = sqlite3.connect(os.path.join(config['data_dir'], 'dsari.sqlite3'))
    for (job_name, run_id, start_time, stop_time, exit_code, trigger_type, trigger_data) in db_conn.execute('SELECT job_name, run_id, start_time, stop_time, exit_code, trigger_type, trigger_data FROM runs'):
        if job_name in ignore_jobs:
            logger.debug('Ignoring %s %s' % (job_name, run_id))
            continue
        context = {
            'job_name': job_name,
            'run_id': run_id,
            'start_time': datetime.datetime.fromtimestamp(start_time),
            'stop_time': datetime.datetime.fromtimestamp(stop_time),
            'exit_code': exit_code,
            'trigger_type': trigger_type,
            'trigger_data': json.loads(trigger_data),
        }
        runs.append(context)
        if job_name not in jobs:
            jobs[job_name] = []
        jobs[job_name].append(context)
        if os.path.isfile(os.path.join(config['data_dir'], 'html', job_name, run_id, 'index.html')):
            continue
        if not os.path.exists(os.path.join(config['data_dir'], 'html', job_name, run_id)):
            os.makedirs(os.path.join(config['data_dir'], 'html', job_name, run_id))
        if os.path.isfile(os.path.join(config['data_dir'], 'runs', job_name, '%s.output' % run_id)):
            with open(os.path.join(config['data_dir'], 'runs', job_name, '%s.output' % run_id)) as f:
                context['run_output'] = f.read().decode('utf-8')
        logger.info('Writing %s' % os.path.join(config['data_dir'], 'html', job_name, run_id, 'index.html'))
        with open(os.path.join(config['data_dir'], 'html', job_name, run_id, 'index.html'), 'w') as f:
            f.write(run_template.render(context).encode('utf-8'))
        if job_name not in jobs_written:
            jobs_written.append(job_name)

    for job_name in jobs:
        if job_name not in jobs_written:
            continue
        context = {
            'job_name': job_name,
            'runs': jobs[job_name],
        }
        if not os.path.exists(os.path.join(config['data_dir'], 'html', job_name)):
            os.makedirs(os.path.join(config['data_dir'], 'html', job_name))
        index_template = templates.get_template('job.html')
        logger.info('Writing %s' % os.path.join(config['data_dir'], 'html', job_name, 'index.html'))
        with open(os.path.join(config['data_dir'], 'html', job_name, 'index.html'), 'w') as f:
            f.write(index_template.render(context))

    if len(jobs_written) > 0:
        context = {
            'runs': runs,
            'jobs': jobs.keys(),
        }
        index_template = templates.get_template('index.html')
        logger.info('Writing %s' % os.path.join(config['data_dir'], 'html', 'index.html'))
        with open(os.path.join(config['data_dir'], 'html', 'index.html'), 'w') as f:
            f.write(index_template.render(context))
