#!/usr/bin/python

import os
import sys
import glob
import jinja2
import datetime
import json
import codecs
import sqlite3

VAR_DIR='var'
ignore_jobs = ['test', 'test2', 'test3', 'test4']

def guess_autoescape(template_name):
    if template_name is None or '.' not in template_name:
        return False
    (base, ext) = template_name.rsplit('.', 1)
    if ext == 'jinja2':
        (base, ext) = base.rsplit('.', 1)
    return ext in ('html', 'htm', 'xml')

templates = jinja2.Environment(
    autoescape=guess_autoescape,
    loader=jinja2.FileSystemLoader('templates'),
    extensions=['jinja2.ext.autoescape'],
)
run_template = templates.get_template('run.html')

runs = []
jobs = {}
conn = sqlite3.connect('dsari.sqlite3')
for (job_name, run_id, start_time, stop_time, exit_code, trigger_type, trigger_data) in conn.execute('SELECT job_name, run_id, start_time, stop_time, exit_code, trigger_type, trigger_data FROM runs'):
    if job_name in ignore_jobs:
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
    if os.path.isfile('html/%s/%s/index.html' % (job_name, run_id)):
        continue
    if not os.path.exists('html/%s/%s' % (job_name, run_id)):
        os.makedirs('html/%s/%s' % (job_name, run_id))
    if os.path.isfile('%s/runs/%s/%s.output' % (VAR_DIR, job_name, run_id)):
        with open('%s/runs/%s/%s.output' % (VAR_DIR, job_name, run_id)) as f:
            context['run_output'] = f.read().decode('utf-8')
    with open('html/%s/%s/index.html' % (job_name, run_id), 'w') as f:
        f.write(run_template.render(context).encode('utf-8'))

for job_name in jobs:
    context = {
        'job_name': job_name,
        'runs': jobs[job_name],
    }
    if not os.path.exists('html/%s' % job_name):
        os.makedirs('html/%s' % job_name)
    index_template = templates.get_template('job.html')
    with open('html/%s/index.html' % job_name, 'w') as f:
        f.write(index_template.render(context))

context = {
    'runs': runs,
    'jobs': jobs.keys(),
}
index_template = templates.get_template('index.html')
with open('html/index.html', 'w') as f:
    f.write(index_template.render(context))
