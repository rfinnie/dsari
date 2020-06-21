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

import binascii
import copy
import datetime
import gzip
import json
import os

try:
    import dateutil.rrule as dateutil_rrule
except ImportError as e:
    dateutil_rrule = e

try:
    import lzma
except ImportError as e:
    lzma = e

try:
    import yaml
except ImportError as e:
    yaml = e

try:
    from . import croniter_hash
except ImportError as e:
    croniter_hash = e


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


def load_structured_file(file, file_type="json", delete_during=False):
    if file_type == "yaml" and isinstance(yaml, ImportError):
        raise ImportError("yaml not available")
    with open(file) as f:
        if delete_during:
            os.remove(file)
        try:
            if file_type == "yaml":
                return yaml.safe_load(f)
            else:
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
    return dt.timestamp()


def validate_environment_dict(env_in):
    env_out = {}
    for k in env_in:
        if type(k) not in (str,):
            raise KeyError(
                "Invalid environment key name: {} ({})".format(repr(k), repr(type(k)))
            )
        if type(env_in[k]) in (str,):
            env_out[k] = env_in[k]
        elif type(env_in[k]) in (int, float):
            env_out[k] = str(env_in[k])
        else:
            raise ValueError(
                "Invalid environment value name: {} ({})".format(
                    repr(env_in[k]), repr(type(env_in[k]))
                )
            )
    return env_out


def get_next_schedule_time(schedule, job_name, start_time=None):
    if start_time is None:
        start_time = datetime.datetime.now()
    crc = binascii.crc32(job_name.encode("utf-8")) & 0xFFFFFFFF
    subsecond_offset = seconds_to_td(float(crc) / float(0xFFFFFFFF))
    if schedule.upper().startswith("RRULE:"):
        if isinstance(dateutil_rrule, ImportError):
            raise ImportError("dateutil not available, manual triggers only")
        hashed_epoch = start_time - seconds_to_td(
            (dt_to_epoch(start_time) % (crc % 86400))
        )
        t = dateutil_rrule.rrulestr(schedule, dtstart=hashed_epoch).after(start_time)
        if t is not None:
            t = t + subsecond_offset
        return t
    if isinstance(croniter_hash, ImportError):
        raise ImportError("croniter not available, manual triggers only")
    if len(schedule.split(" ")) == 5:
        schedule = schedule + " H"
    t = (
        croniter_hash.croniter_hash(
            schedule, start_time=start_time, hash_id=job_name
        ).get_next(datetime.datetime)
        + subsecond_offset
    )
    return t


def json_pretty_print(v):
    return json.dumps(v, sort_keys=True, indent=4, separators=(",", ": "))


def read_output(filename):
    if os.path.isfile(filename):
        with open(filename, "rb") as f:
            return f.read().decode("utf-8")
    elif os.path.isfile("{}.gz".format(filename)):
        with gzip.open("{}.gz".format(filename), "rb") as f:
            return f.read().decode("utf-8")
    elif (not isinstance(lzma, ImportError)) and os.path.isfile(
        "{}.xz".format(filename)
    ):
        with open("{}.xz".format(filename), "rb") as f:
            return lzma.LZMADecompressor().decompress(f.read()).decode("utf-8")
    else:
        return None
