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

import json
import copy
import datetime


try:
    # Python 2
    STR_UNICODE = (str, unicode)
except NameError:
    # Python 3
    STR_UNICODE = (str, )


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
        except ValueError as e:
            e.args += (file,)
            raise


def seconds_to_td(seconds):
    return datetime.timedelta(seconds=seconds)


def td_to_seconds(td):
    return td.total_seconds()


def epoch_to_dt(epoch):
    return datetime.datetime.fromtimestamp(epoch)


def dt_to_epoch(dt):
    return float(dt.strftime('%s')) + (float(dt.microsecond) / float(1000000))


def validate_environment_dict(env_in):
    env_out = {}
    for k in env_in:
        if type(k) not in STR_UNICODE:
            raise KeyError('Invalid environment key name: %s (%s)' % (repr(k), repr(type(k))))
        if type(env_in[k]) in STR_UNICODE:
            env_out[k] = env_in[k]
        elif type(env_in[k]) in (int, float):
            env_out[k] = str(env_in[k])
        else:
            raise ValueError('Invalid environment value name: %s (%s)' % (repr(env_in[k]), repr(type(env_in[k]))))
    return env_out
