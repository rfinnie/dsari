#!/usr/bin/env python3

# dsari - Do Something and Record It
# Copyright (C) 2015-2021 Ryan Finnie
# SPDX-License-Identifier: MPL-2.0

import argparse
import gzip
import logging
import os

import jinja2

try:
    from jinja2.ext import autoescape  # noqa: F401

    HAS_AUTOESCAPE = True
except ImportError:
    HAS_AUTOESCAPE = False

import dsari
import dsari.config
import dsari.database
import dsari.utils
from dsari.utils import dtnow

__version__ = dsari.__version__


def guess_autoescape(template_name):
    if template_name is None or "." not in template_name:
        return False
    (base, ext) = template_name.rsplit(".", 1)
    if ext == "jinja2":
        (base, ext) = base.rsplit(".", 1)
    return ext in ("html", "htm", "xml")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Do Something and Record It - report renderer ({})".format(
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
    parser.add_argument(
        "--regenerate", "-r", action="store_true", help="regenerate all reports"
    )
    parser.add_argument(
        "--debug", action="store_true", help="output additional debugging information"
    )
    return parser.parse_args()


def write_html_file(filename, content):
    if filename.endswith(".gz"):
        with gzip.open(filename, "wb") as f:
            f.write(content.encode("utf-8"))
    else:
        with open(filename, "wb") as f:
            f.write(content.encode("utf-8"))


class Renderer:
    def __init__(self, args):
        self.args = args
        self.config = dsari.config.get_config(self.args.config_dir)

        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        lh_console = logging.StreamHandler()
        lh_console_formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s: %(message)s"
        )
        lh_console.setFormatter(lh_console_formatter)
        if self.args.debug:
            lh_console.setLevel(logging.DEBUG)
        else:
            lh_console.setLevel(logging.INFO)
        self.logger.addHandler(lh_console)

        if self.config.template_dir:
            loader = jinja2.ChoiceLoader(
                jinja2.FileSystemLoader(self.config.template_dir),
                jinja2.PackageLoader("dsari"),
            )
        else:
            loader = jinja2.PackageLoader("dsari")

        extensions = []
        if HAS_AUTOESCAPE:
            extensions.append("jinja2.ext.autoescape")
        self.templates = jinja2.Environment(
            autoescape=guess_autoescape,
            loader=loader,
            extensions=extensions,
        )
        self.templates.globals.update(
            {
                "now": dtnow(),
                "strip_ms": lambda x: str(x).split(".", 2)[0],
            }
        )

        self.db = dsari.database.get_database(self.config)

    def render(self):
        self.jobs = sorted(
            [job for job in self.config.jobs.values() if job.render_reports]
        )
        self.job_runs = {}
        for job in self.jobs:
            job.last_run = None
            job.last_successful_run = None
            self.job_runs[job.name] = []
        self.runs = []
        self.jobs_written = []

        self.render_runs()
        self.render_jobs()
        self.render_index()

    def render_runs(self):
        self.run_template = self.templates.get_template("run.html")
        runs = self.db.get_runs(job_names=[job.name for job in self.jobs])
        for run in runs:
            self.render_run(run)

    def render_run(self, run):
        job = run.job
        self.job_runs[job.name].append(run)
        self.runs.append(run)
        job.last_run = run
        if run.exit_code == 0:
            job.last_successful_run = run
        run_html_filename = os.path.join(
            self.config.data_dir, "html", job.name, run.id, "index.html"
        )
        if self.config.report_html_gz:
            run_html_filename = "{}.gz".format(run_html_filename)
        if os.path.isfile(run_html_filename):
            if not self.args.regenerate:
                return
        if not os.path.exists(
            os.path.join(self.config.data_dir, "html", job.name, run.id)
        ):
            os.makedirs(os.path.join(self.config.data_dir, "html", job.name, run.id))
        raw_output = dsari.utils.read_output(
            os.path.join(self.config.data_dir, "runs", job.name, run.id, "output.txt")
        )
        raw_len = 0 if raw_output is None else len(raw_output)
        limit_start = self.config.report_run_output_start
        limit_end = self.config.report_run_output_end
        limit_combined = limit_start + limit_end
        if (
            (raw_output is not None)
            and (limit_start > 0 or limit_end > 0)
            and (
                raw_len > limit_combined
                or (raw_len > limit_start and limit_start > 0)
                or (raw_len > limit_end and limit_end > 0)
            )
        ):
            run.output = ""
            if limit_start > 0:
                run.output += raw_output[0:limit_start]
            run.output += "\n\n\n[...]\n\n\n"
            if limit_end > 0:
                run.output += raw_output[(0 - limit_end) :]
        else:
            run.output = raw_output
        self.logger.info("Writing {}".format(run_html_filename))
        context = {"run": run}
        write_html_file(run_html_filename, self.run_template.render(context))
        if job not in self.jobs_written:
            self.jobs_written.append(job)

    def render_jobs(self):
        self.job_template = self.templates.get_template("job.html")
        for job in self.jobs:
            if job not in self.jobs_written:
                if not self.args.regenerate:
                    continue
            self.render_job(job)

    def render_job(self, job):
        context = {
            "job": job,
            "runs": sorted(
                self.job_runs[job.name], key=lambda run: run.stop_time, reverse=True
            ),
        }
        if not os.path.exists(os.path.join(self.config.data_dir, "html", job.name)):
            os.makedirs(os.path.join(self.config.data_dir, "html", job.name))
        job_html_filename = os.path.join(
            self.config.data_dir, "html", job.name, "index.html"
        )
        if self.config.report_html_gz:
            job_html_filename = "{}.gz".format(job_html_filename)
        self.logger.info("Writing {}".format(job_html_filename))
        write_html_file(job_html_filename, self.job_template.render(context))

    def render_index(self):
        base_dir = os.path.join(self.config.data_dir, "html")
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
        css_filename = os.path.join(base_dir, "darkly.min.css")
        if not os.path.exists(css_filename):
            css_template = self.templates.get_template("darkly.min.css")
            with open(css_filename, "wb") as f:
                f.write(css_template.render({}).encode("utf-8"))
        self.index_template = self.templates.get_template("index.html")
        if (len(self.jobs_written) > 0) or self.args.regenerate:
            context = {
                "jobs": self.jobs,
                "runs": sorted(self.runs, key=lambda run: run.stop_time, reverse=True)[
                    :25
                ],
                "failed_runs": sorted(
                    [run for run in self.runs if run.exit_code > 0],
                    key=lambda run: run.stop_time,
                    reverse=True,
                )[:10],
            }
            index_html_filename = os.path.join(base_dir, "index.html")
            if self.config.report_html_gz:
                index_html_filename = "{}.gz".format(index_html_filename)
            self.logger.info("Writing {}".format(index_html_filename))
            write_html_file(index_html_filename, self.index_template.render(context))


def main():
    args = parse_args()
    r = Renderer(args)
    r.render()


if __name__ == "__main__":
    import sys

    sys.exit(main())
