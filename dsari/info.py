#!/usr/bin/env python3

# dsari - Do Something and Record It
# Copyright (C) 2015-2021 Ryan Finnie
# SPDX-License-Identifier: MPL-2.0

import argparse
import binascii
import locale
import os
import shlex
import subprocess
import sys
import time

import dsari
import dsari.config
import dsari.database
from dsari.utils import dtnow, seconds_to_td
from dsari.utils import get_next_schedule_time, json_pretty_print, td_to_seconds, yaml

__version__ = dsari.__version__


class Color:
    def __init__(self, do_color=True):
        self.isatty = sys.stdout.isatty()
        self.hash_colors = []
        self.do_color = do_color
        if not self.do_color:
            return
        if not self.isatty:
            self.do_color = False
            return
        try:
            import termcolor

            self.termcolor = termcolor
        except ImportError:
            self.do_color = False
            return
        for c in self.termcolor.COLORS.keys():
            if c in ("red", "grey"):
                continue
            self.hash_colors.append((c, ["bold"]))
            self.hash_colors.append((c, []))

    def hash_colored(self, st):
        if not self.do_color:
            return st
        crc = binascii.crc32(st.encode("utf-8")) & 0xFFFFFFFF
        hashed_color = self.hash_colors[crc % len(self.hash_colors)]
        return self.termcolor.colored(st, hashed_color[0], attrs=hashed_color[1])

    def colored(self, st, *args, **kwargs):
        if not self.do_color:
            return st
        return self.termcolor.colored(st, *args, **kwargs)

    def format(self, st, *args, **kwargs):
        if not self.do_color:
            return st.format(
                *(i[0] for i in args), **{k: v[0] for k, v in kwargs.items()}
            )
        cargs = []
        for arg in args:
            if len(arg) > 1:
                cargs.append(
                    self.termcolor.colored(
                        arg[0], arg[1], attrs=(arg[2] if len(arg) > 2 else [])
                    )
                )
            else:
                cargs.append(arg[0])
        ckwargs = {}
        for k in kwargs:
            if len(kwargs[k]) > 1:
                ckwargs[k] = self.termcolor.colored(
                    kwargs[k][0],
                    kwargs[k][1],
                    attrs=(kwargs[k][2] if len(kwargs[k]) > 2 else []),
                )
            else:
                ckwargs[k] = kwargs[k][0]

        return st.format(*cargs, **ckwargs)


class AutoPager:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __init__(self):
        self.closed = False
        self.pager = None
        if sys.stdout.isatty():
            pager_cmd = ["pager"]
            if os.environ.get("PAGER"):
                pager_cmd = shlex.split(os.environ.get("PAGER"))
            env = os.environ.copy()
            if not os.environ.get("LESS"):
                env.update({"LESS": "-FRSXMQ"})
            try:
                self.pager = subprocess.Popen(
                    pager_cmd, stdin=subprocess.PIPE, stdout=sys.stdout, env=env
                )
            except FileNotFoundError:
                pass

    def write(self, line):
        if self.closed:
            return

        if self.pager:
            try:
                self.pager.stdin.write(line.encode("utf-8"))
            except KeyboardInterrupt:
                self.close()
            except BrokenPipeError:
                self.close()
        else:
            try:
                sys.stdout.write(line)
            except BrokenPipeError:
                self.close()

    def close(self):
        if self.closed:
            return

        if self.pager:
            try:
                self.pager.stdin.close()
            except BrokenPipeError:
                pass
            ret = None
            while ret is None:
                try:
                    ret = self.pager.wait()
                except KeyboardInterrupt:
                    continue

        self.closed = True


def parse_args():
    parser = argparse.ArgumentParser(
        description="Do Something and Record It - job/run information ({})".format(
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
        help="configuration directory",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    parser_job = subparsers.add_parser("job", help="job commands")
    subparsers_job = parser_job.add_subparsers(dest="command_job")
    subparsers_job.required = True
    parser_job_list = subparsers_job.add_parser("list", help="list jobs")

    parser_run = subparsers.add_parser("run", help="run commands")
    subparsers_run = parser_run.add_subparsers(dest="command_run")
    subparsers_run.required = True
    parser_run_list = subparsers_run.add_parser("list", help="list runs")
    parser_run_get = subparsers_run.add_parser("output", help="get run output")
    parser_run_tail = subparsers_run.add_parser("tail", help="tail run output")

    parser_config = subparsers.add_parser("config", help="config commands")
    subparsers_config = parser_config.add_subparsers(dest="command_config")
    subparsers_config.required = True
    parser_config_dump = subparsers_config.add_parser(
        "dump", help="dump a compiled version of the loaded config"
    )
    subparsers_config.add_parser("check", help="validate configuration")

    optional_formats = []
    if not isinstance(yaml, ImportError):
        optional_formats.append("yaml")

    parser_config_dump.add_argument(
        "--raw",
        action="store_true",
        help="output raw config instead of compiled/normalized config",
    )
    parser_config_dump.add_argument(
        "--format",
        type=str,
        choices=["json", *optional_formats],
        default="json",
        help="output format",
    )

    for p in (parser_job_list, parser_run_list):
        p.add_argument(
            "--job",
            type=str,
            action="append",
            help="job name to filter (can be given multiple times)",
        )
        p.add_argument(
            "--format",
            type=str,
            choices=["pretty", "tabular", "json", *optional_formats],
            default="pretty",
            help="output format",
        )

    parser_run_get.add_argument("run", type=str, default=None, help="run UUID")
    parser_run_tail.add_argument("run", type=str, nargs="*", help="run UUID")

    parser_run_list.add_argument(
        "--run",
        type=str,
        action="append",
        help="run ID to filter (can be given multiple times)",
    )

    subparsers.add_parser("shell", help="interactive shell")

    args = parser.parse_args()
    args.parser = parser

    return args


class Info:
    def __init__(self, args):
        self.args = args
        self.config = dsari.config.get_config(self.args.config_dir)
        self.db = dsari.database.get_database(self.config)

    def pretty_print_table(self, output_data, column_headers, file=sys.stdout):
        largest_columns = {
            i: len(column_headers[i]) for i in range(len(column_headers))
        }
        for line in output_data:
            for i in range(len(line)):
                if line[i][1] > largest_columns[i]:
                    largest_columns[i] = line[i][1]

        printable_column_lengths = list(largest_columns.values())
        columns = 1000
        if sys.stdout.isatty():
            try:
                columns = int(
                    subprocess.check_output(["stty", "size"]).decode().split()[1]
                )
            except Exception:
                pass
        try:
            columns = int(os.environ.get("COLUMNS"))
        except Exception:
            pass
        while len(printable_column_lengths) >= 1:
            if (
                sum(printable_column_lengths)
                + (3 * (len(printable_column_lengths) - 1))
                <= columns
            ):
                break
            printable_column_lengths.pop()

        if locale.getlocale()[1] == "UTF-8":
            dashchar = "\u2500"
        else:
            dashchar = "-"
        line_data = [
            "{{:^{}}}".format(largest_columns[i]).format(column_headers[i])
            for i in range(len(printable_column_lengths))
        ]
        print("   ".join(line_data), file=file)
        line_data = [
            dashchar * largest_columns[i] for i in range(len(printable_column_lengths))
        ]
        print("   ".join(line_data), file=file)
        for line in output_data:
            line_data = []
            for i in range(len(printable_column_lengths)):
                if (i + 1) == len(line):
                    line_data.append(line[i][0])
                else:
                    line_data.append(
                        line[i][0] + (" " * (largest_columns[i] - line[i][1]))
                    )
            print("   ".join(line_data), file=file)

    def dump_jobs(self, filter=None):
        jobs = {}
        for job in self.config.jobs.values():
            if filter is not None and job.name not in filter:
                continue
            jobs[job.name] = {
                "command": job.command,
                "command_append_run": job.command_append_run,
                "schedule": job.schedule,
                "next_scheduled_run": (
                    get_next_schedule_time(
                        job.schedule, job.name, start_time=dtnow(job.schedule_timezone)
                    )
                    if job.schedule
                    else None
                ),
                "environment": job.environment,
                "max_execution": job.max_execution,
                "max_execution_grace": job.max_execution_grace,
                "concurrency_groups": sorted(
                    [
                        concurrency_group.name
                        for concurrency_group in job.concurrency_groups
                    ]
                ),
                "render_reports": job.render_reports,
                "jenkins_environment": job.jenkins_environment,
                "job_group": job.job_group,
                "concurrent_runs": job.concurrent_runs,
            }
            if jobs[job.name]["next_scheduled_run"] is not None:
                jobs[job.name]["next_scheduled_run"] = jobs[job.name][
                    "next_scheduled_run"
                ].isoformat()
            for k in ("max_execution", "max_execution_grace"):
                if jobs[job.name][k] is not None:
                    jobs[job.name][k] = td_to_seconds(jobs[job.name][k])
        return jobs

    def cmd_dump_config(self):
        if self.args.raw:
            config = self.config.raw_config
        else:
            config = {"jobs": self.dump_jobs(), "concurrency_groups": {}}
            for attr in (
                "config_d",
                "data_dir",
                "template_dir",
                "report_html_gz",
                "report_run_output_start",
                "report_run_output_end",
                "shutdown_kill_runs",
                "shutdown_kill_grace",
                "environment",
                "database",
            ):
                config[attr] = getattr(self.config, attr)
            for attr in ("shutdown_kill_grace",):
                if config[attr] is not None:
                    config[attr] = td_to_seconds(config[attr])
            for concurrency_group in self.config.concurrency_groups.values():
                config["concurrency_groups"][concurrency_group.name] = {
                    "max": concurrency_group.max
                }
        with AutoPager() as pager:
            if self.args.format == "yaml":
                print(yaml.safe_dump(config), file=pager, end="")
            else:
                print(json_pretty_print(config), file=pager)

    def cmd_check_config(self):
        print("Config OK")

    def cmd_list_jobs(self):
        if self.args.job:
            jobs = self.dump_jobs(self.args.job)
        else:
            jobs = self.dump_jobs()
        if self.args.format == "json":
            with AutoPager() as pager:
                print(json_pretty_print(jobs), file=pager)
        elif self.args.format == "yaml":
            with AutoPager() as pager:
                print(yaml.safe_dump(jobs), file=pager, end="")
        elif self.args.format == "tabular":
            with AutoPager() as pager:
                for job_name in sorted(jobs):
                    job = jobs[job_name]
                    schedule = job["schedule"] or ""
                    command = " ".join([shlex.quote(x) for x in job["command"]])
                    next_scheduled_run = job["next_scheduled_run"] or ""
                    print(
                        "\t".join([job_name, schedule, command, next_scheduled_run]),
                        file=pager,
                    )
        else:
            color = Color()
            column_headers = ("Job Name", "Schedule", "Next Scheduled Run", "Command")
            output_data = []

            for job_name in sorted(jobs):
                job = jobs[job_name]
                schedule = job["schedule"] or ""
                command = " ".join([shlex.quote(x) for x in job["command"]])
                next_scheduled_run = job["next_scheduled_run"] or ""
                output_data.append(
                    (
                        (color.hash_colored(job_name), len(job_name)),
                        (schedule, len(schedule)),
                        (next_scheduled_run, len(next_scheduled_run)),
                        (command, len(command)),
                    )
                )
            with AutoPager() as pager:
                self.pretty_print_table(output_data, column_headers, pager)

    def cmd_list_runs(self):
        job_names = self.args.job
        run_ids = self.args.run
        runs = self.db.get_runs(
            job_names=job_names, run_ids=run_ids, runs_running=False
        ) + self.db.get_runs(job_names=job_names, run_ids=run_ids, runs_running=True)
        if self.args.format in ("json", "yaml"):
            out = {}
            for run in runs:
                out[run.id] = {
                    "job_name": run.job.name,
                    "schedule_time": run.schedule_time.isoformat(),
                    "start_time": run.start_time.isoformat(),
                    "stop_time": (
                        None if not run.stop_time else run.stop_time.isoformat()
                    ),
                    "exit_code": (None if not run.stop_time else run.exit_code),
                    "trigger_type": run.trigger_type,
                    "trigger_data": run.trigger_data,
                    "run_data": run.run_data,
                }
            with AutoPager() as pager:
                if self.args.format == "json":
                    print(json_pretty_print(out), file=pager)
                elif self.args.format == "yaml":
                    print(yaml.safe_dump(out), file=pager, end="")
        elif self.args.format == "tabular":
            with AutoPager() as pager:
                for run in sorted(runs, key=lambda run: run.start_time):
                    print(
                        "\t".join(
                            [
                                run.id,
                                run.job.name,
                                ("" if not run.stop_time else str(run.exit_code)),
                                run.trigger_type,
                                run.schedule_time.isoformat(),
                                run.start_time.isoformat(),
                                (
                                    ""
                                    if not run.stop_time
                                    else run.stop_time.isoformat()
                                ),
                            ]
                        ),
                        file=pager,
                    )
        else:
            color = Color()

            def time_color(t):
                now = dtnow()
                if (now - t) <= seconds_to_td(60 * 60):
                    return "green"
                elif (now - t) <= seconds_to_td(60 * 60 * 24):
                    return "blue"
                else:
                    return None

            output_data = []
            if True:
                column_headers = (
                    "Run ID",
                    "Exit",
                    "Job",
                    "Duration",
                    "Start Time",
                    "Type",
                    "Schedule Delay",
                )
                now = dtnow()
                for run in sorted(runs, key=lambda run: run.start_time, reverse=True):
                    if run.stop_time is not None:
                        run_time = str(run.stop_time - run.start_time)
                        run_time_color = None
                        exit_code = str(run.exit_code)
                        exit_code_color = "red" if run.exit_code > 0 else None
                    else:
                        run_time = str(now - run.start_time)
                        run_time_color = "blue"
                        exit_code = "..."
                        exit_code_color = "blue"
                    output_data.append(
                        (
                            (run.id, len(run.id)),
                            (
                                color.colored(exit_code, exit_code_color),
                                len(str(exit_code)),
                            ),
                            (color.hash_colored(run.job.name), len(run.job.name)),
                            (color.colored(run_time, run_time_color), len(run_time)),
                            (
                                color.colored(
                                    run.start_time.isoformat(),
                                    time_color(run.start_time),
                                ),
                                len(run.start_time.isoformat()),
                            ),
                            (
                                color.colored(
                                    run.trigger_type,
                                    ("blue" if run.trigger_type == "file" else None),
                                ),
                                len(run.trigger_type),
                            ),
                            (
                                str(run.start_time - run.schedule_time),
                                len(str(run.start_time - run.schedule_time)),
                            ),
                        )
                    )

            with AutoPager() as pager:
                self.pretty_print_table(output_data, column_headers, file=pager)

    def cmd_get_run_output(self):
        run_id = self.args.run
        runs = self.db.get_runs(run_ids=[run_id])
        if len(runs) == 0:
            runs = self.db.get_runs(run_ids=[run_id], runs_running=True)
            if len(runs) == 0:
                self.args.parser.error("Cannot find run ID {}".format(run_id))
        run = runs[0]
        fn = os.path.join(
            self.config.data_dir, "runs", run.job.name, run.id, "output.txt"
        )
        with AutoPager() as pager:
            pager.write(dsari.utils.read_output(fn))

    def cmd_tail_run_output(self):
        while True:
            self.cmd_tail_run_output_loop()
            time.sleep(1)

    def cmd_tail_run_output_loop(self):
        runs = self.db.get_runs(
            run_ids=(self.args.run if self.args.run else None), runs_running=True
        )
        filenames = []
        for run in runs:
            filename = os.path.join(
                self.config.data_dir, "runs", run.job.name, run.id, "output.txt"
            )
            if os.path.exists(filename):
                filenames.append(filename)
        if filenames:
            os.execvp("tail", ["tail", "-f", *filenames])

    def cmd_shell(self):
        # readline is used transparently by code.InteractiveConsole()
        import readline  # noqa: F401

        vars = {
            "concurrency_groups": self.config.concurrency_groups,
            "config": self.config,
            "db": self.db,
            "dsari": dsari,
            "jobs": self.config.jobs,
        }
        banner = "Additional variables available:\n"
        for (k, v) in vars.items():
            v = vars[k]
            if type(v) == dict:
                r = "Dictionary ({} items)".format(len(v))
            elif type(v) == list:
                r = "List ({} items)".format(len(v))
            else:
                r = repr(v)
            banner += "    {}: {}\n".format(k, r)
        banner += "\n"

        sh = None
        try:
            from IPython.terminal.embed import InteractiveShellEmbed

            sh = InteractiveShellEmbed(user_ns=vars, banner2=banner)
            sh.excepthook = sys.__excepthook__
        except ImportError:
            print("ipython not available. Using normal python shell.")

        if sh:
            sh()
        else:
            import code

            class DsariConsole(code.InteractiveConsole):
                pass

            console_vars = vars.copy().update(
                {"__name__": "__console__", "__doc__": None}
            )
            print(banner, end="")
            DsariConsole(locals=console_vars).interact()

    def main(self):
        command = self.args.command
        while hasattr(self.args, "command_{}".format(command)):
            command = "{}_{}".format(
                command, getattr(self.args, "command_{}".format(command))
            )

        cmd_map = {
            "config_check": self.cmd_check_config,
            "config_dump": self.cmd_dump_config,
            "job_list": self.cmd_list_jobs,
            "run_list": self.cmd_list_runs,
            "run_output": self.cmd_get_run_output,
            "run_tail": self.cmd_tail_run_output,
            "shell": self.cmd_shell,
        }
        cmd_map[command]()


def main():
    args = parse_args()
    r = Info(args)
    r.main()


if __name__ == "__main__":
    sys.exit(main())
