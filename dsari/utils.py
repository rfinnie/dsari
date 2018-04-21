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

import json
import copy
import datetime
import binascii

try:
    from . import croniter_hash
    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False

try:
    import dateutil.rrule
    import dateutil.parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False


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
    return (dt - datetime.datetime.utcfromtimestamp(0)).total_seconds()


def validate_environment_dict(env_in):
    env_out = {}
    for k in env_in:
        if type(k) not in (str, ):
            raise KeyError('Invalid environment key name: {} ({})'.format(repr(k), repr(type(k))))
        if type(env_in[k]) in (str, ):
            env_out[k] = env_in[k]
        elif type(env_in[k]) in (int, float):
            env_out[k] = str(env_in[k])
        else:
            raise ValueError('Invalid environment value name: {} ({})'.format(repr(env_in[k]), repr(type(env_in[k]))))
    return env_out


def get_next_schedule_time(schedule, job_name, start_time=None):
    if start_time is None:
        start_time = datetime.datetime.now()
    crc = binascii.crc32(job_name.encode('utf-8')) & 0xffffffff
    subsecond_offset = seconds_to_td(float(crc) / float(0xffffffff))
    if schedule.upper().startswith('RRULE:'):
        if not HAS_DATEUTIL:
            raise ImportError('dateutil not available, manual triggers only')
        hashed_epoch = start_time - seconds_to_td((dt_to_epoch(start_time) % (crc % 86400)))
        t = dateutil.rrule.rrulestr(schedule, dtstart=hashed_epoch).after(start_time) + subsecond_offset
        if t is None:
            raise ValueError('rrulestr returned None')
        return t
    if not HAS_CRONITER:
        raise ImportError('croniter not available, manual triggers only')
    if len(schedule.split(' ')) == 5:
        schedule = schedule + ' H'
    t = croniter_hash.croniter_hash(
        schedule,
        start_time=start_time,
        hash_id=job_name
    ).get_next(datetime.datetime) + subsecond_offset
    return t
