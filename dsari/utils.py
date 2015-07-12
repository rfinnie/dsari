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
    config = json_load_file(os.path.join(config_dir, 'dsari.json'))
    if 'config_d' in config and config['config_d']:
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
    if 'concurrency_groups' not in config:
        config['concurrency_groups'] = {}

    if 'data_dir' not in config:
        config['data_dir'] = DEFAULT_DATA_DIR
    if 'template_dir' not in config:
        config['template_dir'] = None

    if 'shutdown_kill_runs' not in config:
        config['shutdown_kill_runs'] = False
    if 'shutdown_kill_grace' not in config:
        config['shutdown_kill_grace'] = None

    for job_name in config['jobs'].keys():
        if '/' in job_name:
            del(config['jobs'][job_name])
            continue
        if job_name in ('.', '..'):
            del(config['jobs'][job_name])
            continue
        if 'concurrency_group' not in config['jobs'][job_name]:
            config['jobs'][job_name]['concurrency_group'] = None
        if 'max_execution' not in config['jobs'][job_name]:
            config['jobs'][job_name]['max_execution'] = None
        if 'environment' not in config['jobs'][job_name]:
            config['jobs'][job_name]['environment'] = {}
        if 'render_reports' not in config['jobs'][job_name]:
            config['jobs'][job_name]['render_reports'] = True
        if 'command_append_run' not in config['jobs'][job_name]:
            config['jobs'][job_name]['command_append_run'] = False

    return config
