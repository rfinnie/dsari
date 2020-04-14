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

import uuid

from . import utils

__version__ = '2.0'


class ConcurrencyGroup(object):
    def __init__(self, name):
        self.name = name
        self.max = 1

    def __lt__(self, other):
        if isinstance(other, self.__class__):
            return self.name < other.name
        return NotImplemented

    def __repr__(self):
        return '<ConcurrencyGroup {} ({})>'.format(self.name, self.max)


class Job(object):
    def __init__(self, name):
        self.name = name
        self.command = []
        self.schedule = None
        self.concurrency_groups = []
        self.max_execution = None
        self.max_execution_grace = utils.seconds_to_td(60.0)
        self.environment = {}
        self.render_reports = True
        self.command_append_run = False
        self.jenkins_environment = False
        self.job_group = None
        self.concurrent_runs = False

    def __lt__(self, other):
        if isinstance(other, self.__class__):
            return self.name < other.name
        return NotImplemented

    def __repr__(self):
        if self.schedule:
            return '<Job {} ({})>'.format(self.name, self.schedule)
        else:
            return '<Job {}>'.format(self.name)


class Run(object):
    def __init__(self, job, id=None):
        self.job = job
        self.id = id
        self.schedule_time = None
        self.trigger_type = None
        self.trigger_data = {}
        self.run_data = {}
        self.respawn = False
        self.concurrency_group = None
        self.start_time = None
        self.stop_time = None
        self.exit_code = None
        self.output = None

        if not self.id:
            self.id = str(uuid.uuid4())

    def __lt__(self, other):
        if isinstance(other, self.__class__):
            return self.id < other.id
        return NotImplemented

    def __repr__(self):
        return '<Run {} ({})>'.format(self.id, self.job.name)
