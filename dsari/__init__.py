#!/usr/bin/env python3

# dsari - Do Something and Record It
# Copyright (C) 2015-2021 Ryan Finnie
# SPDX-License-Identifier: MPL-2.0

import uuid

from . import utils

__version__ = "2.0"


class ConcurrencyGroup(object):
    def __init__(self, name):
        self.name = name
        self.max = 1

    def __lt__(self, other):
        if isinstance(other, self.__class__):
            return self.name < other.name
        return NotImplemented

    def __repr__(self):
        return "<ConcurrencyGroup {} ({})>".format(self.name, self.max)


class Job(object):
    def __init__(self, name):
        self.name = name
        self.command = []
        self.schedule = None
        self.schedule_timezone = utils.dtnow().tzinfo
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
            return "<Job {} ({})>".format(self.name, self.schedule)
        else:
            return "<Job {}>".format(self.name)


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
        return "<Run {} ({})>".format(self.id, self.job.name)
