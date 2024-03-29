#!/usr/bin/env python3

# dsari - Do Something and Record It
# Copyright (C) 2015-2021 Ryan Finnie
# SPDX-License-Identifier: MPL-2.0

import copy
import os
import re
import shlex

import dsari
from dsari import utils


def dir_has_config(dir):
    if os.path.exists(os.path.join(dir, "dsari.json")):
        return True
    elif os.path.exists(os.path.join(dir, "dsari.yaml")):
        return True
    elif os.path.exists(os.path.join(dir, "config.d")):
        return True
    else:
        return False


if "DSARI_HOME" in os.environ:
    DEFAULT_CONFIG_DIR = os.path.join(os.environ["DSARI_HOME"], "etc")
    DEFAULT_DATA_DIR = os.path.join(os.environ["DSARI_HOME"], "var")
elif dir_has_config(os.path.join(os.path.expanduser("~"), ".dsari", "etc")):
    DEFAULT_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".dsari", "etc")
    DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), ".dsari", "var")
elif dir_has_config("/usr/local/etc/dsari"):
    DEFAULT_CONFIG_DIR = "/usr/local/etc/dsari"
    DEFAULT_DATA_DIR = "/usr/local/lib/dsari"
elif dir_has_config("/etc/dsari"):
    DEFAULT_CONFIG_DIR = "/etc/dsari"
    DEFAULT_DATA_DIR = "/var/lib/dsari"
else:
    DEFAULT_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".dsari", "etc")
    DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), ".dsari", "var")


def get_config(config_dir=DEFAULT_CONFIG_DIR):
    loader = ConfigLoader(Config())
    loader.load_dir(config_dir)
    return loader.config


class ConfigError(RuntimeError):
    pass


class Config:
    def __init__(self):
        self.raw_config = {}

        self.jobs = {}
        self.concurrency_groups = {}
        self.config_d = None
        self.data_dir = DEFAULT_DATA_DIR
        self.template_dir = None
        self.report_html_gz = False
        self.report_run_output_start = 0
        self.report_run_output_end = 0
        self.shutdown_kill_runs = False
        self.shutdown_kill_grace = None
        self.environment = {}
        self.database = {"type": "sqlite3", "file": None}


class ConfigLoader:
    def __init__(self, config):
        self.config = config

    def is_valid_name(self, job_name):
        if "/" in job_name:
            return False
        if job_name in (".", ".."):
            return False
        if len(job_name) > 64:
            return False
        if not re.search("^([- A-Za-z0-9_+.:@]+)$", job_name):
            return False
        return True

    def load_dir(self, config_dir=DEFAULT_CONFIG_DIR):
        config = {}
        for fn, fn_type in [("dsari.yaml", "yaml"), ("dsari.json", "json")]:
            if os.path.exists(os.path.join(config_dir, fn)):
                try:
                    config = utils.dict_merge(
                        config,
                        utils.load_structured_file(
                            os.path.join(config_dir, fn), file_type=fn_type
                        ),
                    )
                except (ValueError, ImportError) as e:
                    raise ConfigError(e)
        self.config.config_d = os.path.join(config_dir, "config.d")
        if "config_d" in config:
            self.config.config_d = config["config_d"]
        if self.config.config_d and os.path.isdir(self.config.config_d):
            config_d = self.config.config_d

            for fn_type in ["yaml", "json"]:
                config_files = [
                    os.path.join(config_d, fn)
                    for fn in os.listdir(config_d)
                    if fn.endswith("." + fn_type)
                    and os.path.isfile(os.path.join(config_d, fn))
                    and os.access(os.path.join(config_d, fn), os.R_OK)
                ]
                config_files.sort()
                for file in config_files:
                    try:
                        config = utils.dict_merge(
                            config, utils.load_structured_file(file, file_type=fn_type)
                        )
                    except (ValueError, ImportError) as e:
                        raise ConfigError(e)

        self.load(config)

    def populate_object(self, obj, level, source, valid_values, value_transforms):
        for k, v in source.items():
            if k not in valid_values:
                continue
            if type(v) not in valid_values[k]:
                raise ConfigError(
                    "{}: {}: Invalid value {} (expected {})".format(
                        level, k, repr(type(v)), repr(valid_values[k])
                    )
                )
            if k in value_transforms:
                try:
                    v = value_transforms[k](v)
                except Exception as e:
                    raise ConfigError(
                        "{}: {}: Invalid value during transformation: {}".format(
                            level, k, str(e)
                        )
                    )
                    return
            setattr(obj, k, v)

    def build_base(self, config):
        valid_values = {
            "data_dir": (str,),
            "template_dir": (str,),
            "report_html_gz": (bool,),
            "report_run_output_start": (int,),
            "report_run_output_end": (int,),
            "shutdown_kill_runs": (bool,),
            "shutdown_kill_grace": (int, float),
            "environment": (dict,),
            "database": (dict,),
        }
        value_transforms = {
            "shutdown_kill_grace": utils.seconds_to_td,
            "environment": lambda x: utils.validate_environment_dict(copy.deepcopy(x)),
        }
        self.populate_object(
            self.config, "Config", config, valid_values, value_transforms
        )

    def build_concurrency_groups(self, config):
        if "concurrency_groups" not in config:
            return

        valid_values = {"max": (int,)}
        value_transforms = {}

        for concurrency_group_name, concurrency_group_dict in config[
            "concurrency_groups"
        ].items():
            if not self.is_valid_name(concurrency_group_name):
                raise ConfigError(
                    "Concurrency group {}: Invalid name".format(concurrency_group_name)
                )
            concurrency_group = dsari.ConcurrencyGroup(concurrency_group_name)
            self.populate_object(
                concurrency_group,
                "Concurrency group {}".format(concurrency_group_name),
                concurrency_group_dict,
                valid_values,
                value_transforms,
            )
            self.config.concurrency_groups[concurrency_group.name] = concurrency_group

    def build_jobs(self, config):
        jobs = {}
        if "jobs" in config:
            jobs = config["jobs"]
        job_groups = {}
        if "job_groups" in config:
            job_groups = config["job_groups"]

        for job_group_name, job_group_dict in job_groups.items():
            if not self.is_valid_name(job_group_name):
                raise ConfigError("Job group {}: Invalid name".format(job_group_name))
            job_template = copy.deepcopy(job_group_dict)
            if "job_names" not in job_template:
                raise ConfigError(
                    "Job group {}: job_names required".format(job_group_name)
                )
            for job_name in job_template["job_names"]:
                jobs[job_name] = copy.deepcopy(job_template)
                jobs[job_name]["job_group"] = job_group_name
                del jobs[job_name]["job_names"]

        for job_name in jobs.keys():
            self.build_job(job_name, jobs[job_name])

    def build_job(self, job_name, job_dict):
        valid_values = {
            "command": (list, str),
            "schedule": (type(None),) + (str,),
            "schedule_timezone": (str,),
            "max_execution": (int, float),
            "max_execution_grace": (int, float),
            "environment": (dict,),
            "render_reports": (bool,),
            "command_append_run": (bool,),
            "jenkins_environment": (bool,),
            "job_group": (str,),
            "concurrent_runs": (bool,),
        }
        value_transforms = {
            "schedule_timezone": utils.dateutil_tz.gettz,
            "max_execution": utils.seconds_to_td,
            "max_execution_grace": utils.seconds_to_td,
            "environment": lambda x: utils.validate_environment_dict(copy.deepcopy(x)),
        }

        if not self.is_valid_name(job_name):
            raise ConfigError("Job {}: Invalid name".format(job_name))
        if "command" not in job_dict:
            raise ConfigError("Job {}: command required".format(job_name))
        if type(job_dict["command"]) == str:
            job_dict["command"] = shlex.split(job_dict["command"])
        job = dsari.Job(job_name)
        self.populate_object(
            job, "Job {}".format(job_name), job_dict, valid_values, value_transforms
        )
        if job.schedule is not None:
            try:
                utils.get_next_schedule_time(job.schedule, job.name)
            except Exception as e:
                raise ConfigError(
                    "Job {}: Invalid schedule ({}): {}: {}".format(
                        job.name, job.schedule, type(e), str(e)
                    )
                )
        self.build_job_concurrency_groups(job, job_dict)
        self.config.jobs[job.name] = job

    def build_job_concurrency_groups(self, job, job_dict):
        if "concurrency_groups" not in job_dict:
            return
        for concurrency_group_name in job_dict["concurrency_groups"]:
            if concurrency_group_name in self.config.concurrency_groups:
                concurrency_group = self.config.concurrency_groups[
                    concurrency_group_name
                ]
            else:
                if not self.is_valid_name(concurrency_group_name):
                    raise ConfigError(
                        "Concurrency group {}: Invalid name".format(
                            concurrency_group_name
                        )
                    )
                concurrency_group = dsari.ConcurrencyGroup(concurrency_group_name)
                self.config.concurrency_groups[
                    concurrency_group.name
                ] = concurrency_group
            job.concurrency_groups.append(concurrency_group)

    def load(self, config):
        self.config.raw_config = copy.deepcopy(config)
        self.build_base(config)
        self.build_concurrency_groups(config)
        self.build_jobs(config)
