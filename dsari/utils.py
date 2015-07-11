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

    if 'concurrency_groups' not in config:
        config['concurrency_groups'] = {}

    if 'data_dir' not in config:
        config['data_dir'] = DEFAULT_DATA_DIR

    return config
