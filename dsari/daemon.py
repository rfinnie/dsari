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

import argparse
import copy
import datetime
import logging
import math
import os
import pwd
import random
import signal
import time

try:
    from shlex import quote as shquote
except ImportError:
    from pipes import quote as shquote

try:
    import dateutil.parser as dateutil_parser
except ImportError as e:
    dateutil_parser = e

import dsari
import dsari.config
import dsari.database
from dsari.utils import dt_to_epoch, epoch_to_dt
from dsari.utils import seconds_to_td, td_to_seconds
from dsari.utils import (
    get_next_schedule_time,
    load_structured_file,
    validate_environment_dict,
    yaml,
)

__version__ = dsari.__version__


def wait_deadline(pid, options, deadline, interval=0.05):
    while True:
        (child_pid, child_exit, child_resource) = os.wait4(pid, options)
        child_signal = child_exit % 256
        if child_signal > 0:
            child_exit = 128 + child_signal
        else:
            child_exit = child_exit >> 8
        if child_pid != 0:
            return (child_pid, child_exit, child_resource)
        if datetime.datetime.now() >= deadline:
            return (child_pid, child_exit, child_resource)
        time.sleep(interval)


def backoff(a, b, min=5.0, max=300.0):
    a = dt_to_epoch(a)
    b = dt_to_epoch(b)
    if a >= b:
        return seconds_to_td(min)
    r = 2 ** math.log(b - a)
    if r < min:
        return seconds_to_td(min)
    elif r > max:
        return seconds_to_td(max)
    else:
        return seconds_to_td(r)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Do Something and Record It - scheduler daemon ({})".format(
            __version__
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
        help="report the program version",
    )
    parser.add_argument(
        "--config-dir",
        "-c",
        type=str,
        default=dsari.config.DEFAULT_CONFIG_DIR,
        help="configuration directory for dsari.json",
    )
    parser.add_argument(
        "--fork", action="store_true", help="fork into the background after starting"
    )
    parser.add_argument(
        "--debug", action="store_true", help="output additional debugging information"
    )
    parser.add_argument(
        "--no-timestamp",
        action="store_true",
        help="do not show timestamps in logging output",
    )
    return parser.parse_args()


class Scheduler:
    def __init__(self, args):
        self.shutdown = False
        self.args = args
        self.load_config()

        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        lh_console = logging.StreamHandler()
        if self.args.no_timestamp:
            lh_console_formatter = logging.Formatter("%(levelname)s: %(message)s")
        else:
            lh_console_formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)s: %(message)s"
            )
        lh_console.setFormatter(lh_console_formatter)
        if self.args.debug:
            lh_console.setLevel(logging.DEBUG)
        else:
            lh_console.setLevel(logging.INFO)
        self.logger.addHandler(lh_console)

        self.jobs = []
        self.scheduled_runs = []
        self.running_runs = []
        self.running_groups = {}

        self.wakeups = []
        self.next_wakeup = datetime.datetime.now() + seconds_to_td(60.0)

        self.db = dsari.database.get_database(self.config)
        self.logger.debug("Database in use: {}".format(repr(self.db)))
        self.db.clear_runs_running()

        self.reset_jobs()

        for signum in (
            signal.SIGHUP,
            signal.SIGINT,
            signal.SIGTERM,
            signal.SIGQUIT,
            signal.SIGUSR1,
        ):
            signal.signal(signum, self.signal_handler)

        self.logger.info("Scheduler running")

    def begin_shutdown(self):
        self.shutdown = True
        self.shutdown_begin = datetime.datetime.now()
        self.scheduled_runs = []
        for run in self.running_runs:
            run.respawn = False

        if self.config.shutdown_kill_runs:
            for run in self.running_runs:
                if run.term_sent:
                    continue
                job = run.job
                self.logger.info(
                    "[{} {}] Shutdown requested, sending SIGTERM to PID {}".format(
                        job.name, run.id, run.pid
                    )
                )
                os.kill(run.pid, signal.SIGTERM)
                run.term_sent = True
        elif len(self.running_runs) > 0:
            self.logger.info("Shutdown will proceed after runs have completed")

    def monitor_shutdown(self):
        if not self.config.shutdown_kill_runs:
            return
        if not self.config.shutdown_kill_grace:
            return
        if datetime.datetime.now() < (
            self.shutdown_begin + self.config.shutdown_kill_grace
        ):
            self.wakeups.append(self.shutdown_begin + self.config.shutdown_kill_grace)
            return
        for run in self.running_runs:
            if run.kill_sent:
                continue
            job = run.job
            self.logger.info(
                "[{} {}] Shutdown grace time exceeded, sending SIGKILL to PID {}".format(
                    job.name, run.id, run.pid
                )
            )
            os.kill(run.pid, signal.SIGKILL)
            run.kill_sent = True

    def signal_handler(self, signum, frame):
        self.next_wakeup = datetime.datetime.now()
        if signum in (signal.SIGINT, signal.SIGTERM):
            if signum == signal.SIGINT:
                self.logger.info("SIGINT received, beginning shutdown")
            elif signum == signal.SIGTERM:
                self.logger.info("SIGTERM received, beginning shutdown")
            self.begin_shutdown()
        elif signum == signal.SIGHUP:
            self.logger.info("SIGHUP received, reloading")
            self.load_config()
            self.reset_jobs()
        elif signum == signal.SIGQUIT:
            self.sigquit_status()
        elif signum == signal.SIGUSR1:
            self.logger.debug("SIGUSR1 received")

    def sigquit_status(self):
        now = datetime.datetime.now()
        for run in sorted(self.running_runs, key=lambda x: x.job.name):
            job = run.job
            t = run.start_time
            self.logger.info(
                "[{} {}] PID {} running since {} ({})".format(
                    job.name, run.id, run.pid, t, (now - t)
                )
            )
            if run.concurrency_group:
                concurrency_group = run.concurrency_group
                self.logger.info(
                    "[{} {}] Concurrency group: {} ({} out of {})".format(
                        job.name,
                        run.id,
                        concurrency_group.name,
                        len(self.running_groups[concurrency_group]),
                        concurrency_group.max,
                    )
                )
        for run in sorted(self.scheduled_runs, key=lambda x: x.job.name):
            job = run.job
            t = run.schedule_time

            # timedelta gets weird when dealing with negatives
            if t < now:
                delta_str = "-" + str(now - t)
            else:
                delta_str = str(t - now)

            self.logger.info(
                "[{} {}] Next run ({}): {} ({})".format(
                    job.name, run.id, run.trigger_type, t, delta_str
                )
            )

    def load_config(self):
        self.config = dsari.config.get_config(self.args.config_dir)

    def reset_jobs(self):
        if self.shutdown:
            return
        self.jobs = []
        self.scheduled_runs = []
        for run in self.running_runs:
            run.respawn = False
        now = datetime.datetime.now()
        for job in sorted(self.config.jobs.values()):
            self.jobs.append(job)
            if not job.schedule:
                self.logger.debug(
                    "[{}] No schedule defined, manual triggers only".format(job.name)
                )
                continue
            t = get_next_schedule_time(job.schedule, job.name, start_time=now)
            if t is None:
                self.logger.debug(
                    "[{}] Schedule {} does not produce a future run, skipping".format(
                        job.name, job.schedule
                    )
                )
                continue
            run = dsari.Run(job)
            run.respawn = True
            run.trigger_type = "schedule"
            self.logger.debug(
                "[{} {}] Next scheduled run: {} ({})".format(
                    job.name, run.id, t, (t - now)
                )
            )
            run.schedule_time = t
            self.scheduled_runs.append(run)

        # Regenerate running runs' jobs and concurrency groups
        self.running_groups = {}
        for run in self.running_runs:
            if run.job.name in self.config.jobs:
                run.job = self.config.jobs[run.job.name]
            else:
                # Job disappeared from config during SIGHUP
                run.respawn = False
            if run.concurrency_group:
                if run.concurrency_group.name in self.config.concurrency_groups:
                    concurrency_group = self.config.concurrency_groups[
                        run.concurrency_group.name
                    ]
                    run.concurrency_group = concurrency_group
                    if concurrency_group not in self.running_groups:
                        self.running_groups[concurrency_group] = []
                    self.running_groups[concurrency_group].append(run)
                else:
                    # Concurrency group disappeared from config during SIGHUP
                    run.concurrency_group = None

    def process_run_execution_time(self, run):
        job = run.job
        if not job.max_execution:
            return
        sigterm_grace = job.max_execution_grace
        sigkill_grace = seconds_to_td(5.0)
        now = datetime.datetime.now()
        delta = now - run.start_time
        if delta > (job.max_execution + sigterm_grace):
            if not run.kill_sent:
                self.logger.warning(
                    "[{} {}] SIGTERM grace ({}) exceeded, sending SIGKILL to {}".format(
                        job.name, run.id, sigterm_grace, run.pid
                    )
                )
                os.kill(run.pid, signal.SIGKILL)
                run.kill_sent = True
            self.wakeups.append(now + sigkill_grace)
        elif delta > job.max_execution:
            if not run.term_sent:
                self.logger.warning(
                    "[{} {}] Max execution ({}) exceeded, sending SIGTERM to {}".format(
                        job.name, run.id, job.max_execution, run.pid
                    )
                )
                os.kill(run.pid, signal.SIGTERM)
                run.term_sent = True
            self.wakeups.append(now + sigterm_grace)
        else:
            self.wakeups.append(run.start_time + job.max_execution)

    def run_child_executor(self, run):
        # Reset all handled signals to default
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGQUIT):
            signal.signal(signum, signal.SIG_DFL)

        # Put the child in its own process group to prevent SIGINT from
        # propagating to the children
        os.setpgid(os.getpid(), 0)

        # Close the database in the child
        self.db.child_close_fd()

        # Set environment variables
        job = run.job
        environ = {}

        try:
            pwd_user = pwd.getpwuid(os.getuid())
            environ["LOGNAME"] = pwd_user.pw_name
            environ["HOME"] = pwd_user.pw_dir
        except KeyError:
            pass
        if "PATH" in os.environ:
            environ["PATH"] = os.environ["PATH"]
        else:
            environ["PATH"] = "/usr/bin:/bin"

        environ["CI"] = "true"
        environ["DSARI"] = "true"
        environ["DATA_DIR"] = self.config.data_dir
        environ["JOB_NAME"] = job.name
        environ["JOB_DIR"] = os.path.join(self.config.data_dir, "runs", job.name)
        environ["RUN_ID"] = run.id
        environ["RUN_DIR"] = os.path.join(
            self.config.data_dir, "runs", job.name, run.id
        )
        environ["SCHEDULE_TIME"] = str(dt_to_epoch(run.schedule_time))
        environ["START_TIME"] = str(dt_to_epoch(run.start_time))
        environ["TRIGGER_TYPE"] = run.trigger_type
        environ["TRIGGER_DIR"] = os.path.join(self.config.data_dir, "trigger")
        if run.concurrency_group:
            environ["CONCURRENCY_GROUP"] = run.concurrency_group.name
        if run.previous_run:
            environ["PREVIOUS_RUN_ID"] = run.previous_run.id
            environ["PREVIOUS_SCHEDULE_TIME"] = str(
                dt_to_epoch(run.previous_run.schedule_time)
            )
            environ["PREVIOUS_START_TIME"] = str(
                dt_to_epoch(run.previous_run.start_time)
            )
            environ["PREVIOUS_STOP_TIME"] = str(dt_to_epoch(run.previous_run.stop_time))
            environ["PREVIOUS_EXIT_CODE"] = str(run.previous_run.exit_code)
        if run.previous_good_run:
            environ["PREVIOUS_GOOD_RUN_ID"] = run.previous_good_run.id
            environ["PREVIOUS_GOOD_SCHEDULE_TIME"] = str(
                dt_to_epoch(run.previous_good_run.schedule_time)
            )
            environ["PREVIOUS_GOOD_START_TIME"] = str(
                dt_to_epoch(run.previous_good_run.start_time)
            )
            environ["PREVIOUS_GOOD_STOP_TIME"] = str(
                dt_to_epoch(run.previous_good_run.stop_time)
            )
            environ["PREVIOUS_GOOD_EXIT_CODE"] = str(run.previous_good_run.exit_code)
        if run.previous_bad_run:
            environ["PREVIOUS_BAD_RUN_ID"] = run.previous_bad_run.id
            environ["PREVIOUS_BAD_SCHEDULE_TIME"] = str(
                dt_to_epoch(run.previous_bad_run.schedule_time)
            )
            environ["PREVIOUS_BAD_START_TIME"] = str(
                dt_to_epoch(run.previous_bad_run.start_time)
            )
            environ["PREVIOUS_BAD_STOP_TIME"] = str(
                dt_to_epoch(run.previous_bad_run.stop_time)
            )
            environ["PREVIOUS_BAD_EXIT_CODE"] = str(run.previous_bad_run.exit_code)
        if job.job_group:
            environ["JOB_GROUP"] = str(job.job_group)
        if job.jenkins_environment:
            environ["BUILD_NUMBER"] = run.id
            environ["BUILD_ID"] = run.id
            environ["BUILD_URL"] = "file://{}".format(
                os.path.join(self.config.data_dir, "runs", job.name, run.id, "")
            )
            environ["NODE_NAME"] = "master"
            environ["BUILD_TAG"] = "dsari-{}-{}".format(job.name, run.id)
            environ["JENKINS_URL"] = "file://{}".format(
                os.path.join(self.config.data_dir, "")
            )
            environ["EXECUTOR_NUMBER"] = "0"
            environ["WORKSPACE"] = os.path.join(
                self.config.data_dir, "runs", job.name, run.id
            )
        for (key, val) in self.config.environment.items():
            environ[str(key)] = str(val)
        for (key, val) in job.environment.items():
            environ[str(key)] = str(val)
        if "environment" in run.trigger_data:
            for (key, val) in run.trigger_data["environment"].items():
                environ[key] = val

        # Set STDIN to /dev/null, and STDOUT/STDERR to the output file
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        out_f = open(
            os.path.join(self.config.data_dir, "runs", job.name, run.id, "output.txt"),
            "w",
        )
        devnull_f = open(os.devnull, "r")
        os.dup2(devnull_f.fileno(), 0)
        os.dup2(out_f.fileno(), 1)
        os.dup2(out_f.fileno(), 2)
        devnull_f.close()
        out_f.close()

        # Build command line
        command = job.command
        if job.command_append_run:
            command.append(job.name)
            command.append(run.id)

        # chdir to the run directory
        run_pwd = os.path.join(self.config.data_dir, "runs", job.name, run.id)
        if ("PWD" in environ) and os.path.isdir(environ["PWD"]):
            run_pwd = environ["PWD"]
        os.chdir(run_pwd)
        environ["PWD"] = run_pwd

        # Close any remaining open filehandles.  At this point it should
        # just be /dev/urandom (usually on fd 4), but it's not worth it to
        # actually verify.
        os.closerange(3, 1024)

        # Finally!
        os.execvpe(command[0], command, environ)

    def process_next_child(self):
        self.logger.debug(
            "Waiting up to {} for running jobs".format(
                self.next_wakeup - datetime.datetime.now()
            )
        )
        (child_pid, child_exit, child_resource) = wait_deadline(
            -1, os.WNOHANG, self.next_wakeup
        )
        if child_pid == 0:
            return child_pid
        run = None
        for r in self.running_runs:
            if r.pid == child_pid:
                run = r
                break
        if not run:
            return child_pid
        job = run.job
        now = datetime.datetime.now()
        run.stop_time = now
        run.exit_code = child_exit
        self.logger.info(
            "[{} {}] Finished with status {} in {}".format(
                job.name, run.id, child_exit, (run.stop_time - run.start_time)
            )
        )

        return_data_file = None
        return_data_file_type = None
        for fn, fn_type in [("return_data.json", "json"), ("return_data.yaml", "yaml")]:
            test_file = os.path.join(self.config.data_dir, "runs", job.name, run.id, fn)
            if not os.path.exists(test_file):
                continue
            if fn_type == "yaml" and isinstance(yaml, ImportError):
                # Maybe warn here
                continue
            return_data_file = test_file
            return_data_file_type = fn_type
            break
        if return_data_file is not None:
            try:
                run.run_data["return_data"] = load_structured_file(
                    return_data_file, file_type=return_data_file_type
                )
            except Exception:
                pass

        self.db.insert_run(run)
        self.running_runs.remove(run)
        if run.concurrency_group and run in self.running_groups[run.concurrency_group]:
            self.running_groups[run.concurrency_group].remove(run)
        return child_pid

    def process_triggers(self):
        if self.shutdown:
            return
        for job in self.jobs:
            self.process_trigger_job(job)

    def process_trigger_job(self, job):
        trigger_file = None
        trigger_file_type = None
        for fn, fn_type in [("trigger.json", "json"), ("trigger.yaml", "yaml")]:
            test_file = os.path.join(self.config.data_dir, "trigger", job.name, fn)
            if not os.path.exists(test_file):
                continue
            if fn_type == "yaml" and isinstance(yaml, ImportError):
                # Maybe warn here
                continue
            trigger_file = test_file
            trigger_file_type = fn_type
            break
        if trigger_file is None:
            return
        t = epoch_to_dt(os.path.getmtime(trigger_file))
        try:
            j = load_structured_file(
                trigger_file, file_type=trigger_file_type, delete_during=True
            )
        except IOError:
            # Likely during open()
            # Return silently, otherwise we spam the log during each loop
            return
        except OSError:
            # Likely during os.remove()
            # Return silently, otherwise we spam the log during each loop
            return
        except ValueError as e:
            self.logger.error(
                "[{}] Cannot load trigger: {}".format(job.name, e.message)
            )
            return
        if type(j) != dict:
            self.logger.error(
                "[{}] Cannot load trigger: Data must be a dict".format(job.name)
            )
            return
        if ("environment" in j) and (type(j["environment"]) != dict):
            self.logger.error(
                "[{}] Cannot load trigger: environment must be a dict".format(job.name)
            )
            return

        if "schedule_time" in j:
            if type(j["schedule_time"]) in (int, float):
                t = epoch_to_dt(float(j["schedule_time"]))
            elif not isinstance(dateutil_parser, ImportError):
                try:
                    t = dateutil_parser.parse(j["schedule_time"])
                except ValueError:
                    self.logger.error(
                        '[{}] Invalid schedule_time "{}" for trigger'.format(
                            job.name, j["schedule_time"]
                        )
                    )
                    return
            else:
                self.logger.error(
                    '[{}] Cannot parse schedule_time "{}" for trigger'.format(
                        job.name, j["schedule_time"]
                    )
                )
                return

        if "environment" in j:
            try:
                j["environment"] = validate_environment_dict(
                    copy.deepcopy(j["environment"])
                )
            except (KeyError, ValueError) as e:
                self.logger.error(
                    "[{}] Cannot load trigger: {}".format(job.name, str(e))
                )
                return

        run = dsari.Run(job)
        run.respawn = False
        run.trigger_type = "file"
        run.trigger_data = j
        run.schedule_time = t

        if job.concurrent_runs:
            self.logger.info(
                "[{} {}] Trigger detected, created run for {}".format(
                    job.name, run.id, t
                )
            )
            self.scheduled_runs.append(run)
        else:
            scheduled_job_runs = [x for x in self.scheduled_runs if x.job == job]
            if len(scheduled_job_runs) > 0:
                old_run = scheduled_job_runs[0]
                run.respawn = old_run.respawn
                self.scheduled_runs.remove(old_run)
                self.logger.info(
                    "[{} {}] Trigger detected, created run for {}, replacing {}".format(
                        job.name, run.id, t, old_run.id
                    )
                )
            else:
                self.logger.info(
                    "[{} {}] Trigger detected, created run for {}".format(
                        job.name, run.id, t
                    )
                )
            self.scheduled_runs.append(run)

    def process_scheduled_run(self, run):
        now = datetime.datetime.now()
        job = run.job
        if run.schedule_time > now:
            self.wakeups.append(run.schedule_time)
            return
        if (not job.concurrent_runs) and (job in [x.job for x in self.running_runs]):
            self.wakeups.append(now + backoff(run.schedule_time, now))
            return
        run.concurrency_group = None
        if len(job.concurrency_groups) > 0:
            job_concurrency_groups = copy.copy(job.concurrency_groups)
            random.shuffle(job_concurrency_groups)
            for concurrency_group in job_concurrency_groups:
                if concurrency_group not in self.running_groups:
                    self.running_groups[concurrency_group] = []
                if len(self.running_groups[concurrency_group]) < concurrency_group.max:
                    run.concurrency_group = concurrency_group
                    break
            if not run.concurrency_group:
                backoff_time = backoff(run.schedule_time, now)
                self.logger.debug(
                    "[{} {}] Cannot run due to concurrency limits ({}), will try again within {}".format(
                        job.name,
                        run.id,
                        ", ".join(
                            [
                                "{}={}".format(
                                    concurrency_group.name, concurrency_group.max
                                )
                                for concurrency_group in sorted(job_concurrency_groups)
                            ]
                        ),
                        backoff_time,
                    )
                )
                self.wakeups.append(now + backoff_time)
                return

        (
            run.previous_run,
            run.previous_good_run,
            run.previous_bad_run,
        ) = self.db.get_previous_runs(job)

        if not os.path.exists(
            os.path.join(self.config.data_dir, "runs", job.name, run.id)
        ):
            os.makedirs(os.path.join(self.config.data_dir, "runs", job.name, run.id))

        run.start_time = now
        run.term_sent = False
        run.kill_sent = False

        self.db.insert_running_run(run)

        child_pid = os.fork()
        if child_pid == 0:
            self.run_child_executor(run)
            raise OSError("run_child_executor returned, when it should not have")
        run.pid = child_pid
        self.logger.info(
            "[{} {}] Running PID {}: {}".format(
                job.name, run.id, run.pid, " ".join([shquote(x) for x in job.command])
            )
        )
        self.scheduled_runs.remove(run)
        self.running_runs.append(run)
        if run.concurrency_group:
            self.running_groups[run.concurrency_group].append(run)
        if run.respawn and job.schedule:
            t = get_next_schedule_time(job.schedule, job.name, start_time=now)
            if t is None:
                self.logger.debug(
                    "[{}] Schedule {} does not produce a future run, skipping".format(
                        job.name, job.schedule
                    )
                )
                return
            run = dsari.Run(job)
            run.respawn = True
            run.trigger_type = "schedule"
            run.schedule_time = t
            self.scheduled_runs.append(run)
            self.logger.debug(
                "[{} {}] Next scheduled run: {} ({})".format(
                    job.name, run.id, t, (t - now)
                )
            )

    def process_wakeups(self):
        self.next_wakeup = datetime.datetime.now() + seconds_to_td(60.0)
        for wakeup in self.wakeups:
            if wakeup < self.next_wakeup:
                self.next_wakeup = wakeup

    def loop(self):
        while True:
            self.wakeups = []
            self.process_triggers()

            scheduled_runs = copy.copy(self.scheduled_runs)
            random.shuffle(scheduled_runs)
            for run in scheduled_runs:
                self.process_scheduled_run(run)

            for run in self.running_runs:
                self.process_run_execution_time(run)

            if self.shutdown:
                self.monitor_shutdown()

            self.process_wakeups()

            if len(self.running_runs) > 0:
                while (len(self.running_runs) > 0) and (
                    self.next_wakeup > datetime.datetime.now()
                ):
                    if self.process_next_child() == 0:
                        break
            else:
                if self.shutdown:
                    self.logger.info("Shutdown complete")
                    return

                self.logger.debug(
                    "No running jobs, waiting until {}".format(self.next_wakeup)
                )
                while True:
                    now = datetime.datetime.now()
                    if self.next_wakeup <= now:
                        break
                    elif (self.next_wakeup - now) < seconds_to_td(1):
                        time.sleep(td_to_seconds(self.next_wakeup - now))
                    else:
                        time.sleep(1)


def main():
    args = parse_args()
    if args.fork:
        child_pid = os.fork()
        if child_pid > 0:
            return
    s = Scheduler(args)
    s.loop()


if __name__ == "__main__":
    import sys

    sys.exit(main())
