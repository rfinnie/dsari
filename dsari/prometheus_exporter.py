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
import datetime
import json
import logging
import math
import os
import signal
import sys
import time
from urllib.parse import parse_qs

import dsari
import dsari.config
import dsari.database
from dsari.utils import dt_to_epoch

__version__ = dsari.__version__


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Do Something and Record It - Prometheus exporter ({})".format(
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
        "--debug", action="store_true", help="output additional debugging information"
    )
    parser.add_argument(
        "--config-dir",
        "-c",
        type=str,
        default=dsari.config.DEFAULT_CONFIG_DIR,
        help="configuration directory for dsari.json",
    )
    parser.add_argument(
        "--metrics-path",
        type=str,
        default="/metrics",
        help="path to serve metrics from in daemon mode",
    )
    parser.add_argument(
        "--listen-address",
        type=str,
        default="0.0.0.0",
        help="IP address to listen on in daemon mode",
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=50575,
        help="port address to listen on in daemon mode",
    )
    parser.add_argument(
        "--job-cache-time",
        type=float,
        default=120,
        help="Seconds to cache non-running run metrics",
    )
    parser.add_argument(
        "--quantiles",
        type=str,
        default="0.01,0.1,0.5,0.9,0.99",
        help="comma-separated list of quantiles to use for summaries",
    )
    parser.add_argument(
        "--no-running", action="store_true", help="do not gather running run metrics"
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help="dump metrics to stdout and exit, do not start daemon",
    )

    args = parser.parse_args(argv)
    args.parser = parser

    return args


def percentile(N, percent, key=lambda x: x):
    """
    Find the percentile of a list of values.

    @parameter N - is a list of values. Note N MUST BE already sorted.
    @parameter percent - a float value from 0.0 to 1.0.
    @parameter key - optional key function to compute value from each element of N.

    @return - the percentile of the values
    """
    if not N:
        return None
    k = (len(N) - 1) * percent
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return key(N[int(k)])
    d0 = key(N[int(f)]) * (c - k)
    d1 = key(N[int(c)]) * (k - f)
    return d0 + d1


def entry(values, type="gauge", help=None):
    out = {"values": values, "type": type, "help": help}
    return out


class Prometheus:
    def __init__(self, args):
        self.args = args
        self.load_config()
        self.db = dsari.database.get_database(self.config)

    def load_config(self):
        self.config = dsari.config.get_config(self.args.config_dir)
        self.job_cache = None
        self.job_cache_time = None

    def build_metrics_text(self, metrics):
        output = ""
        for k in sorted(metrics):
            if len(metrics[k]["values"]) == 0:
                continue
            if metrics[k]["help"]:
                output += "# HELP {} {}\n".format(k, metrics[k]["help"])
            if metrics[k]["type"]:
                output += "# TYPE {} {}\n".format(k, metrics[k]["type"])
            for a in metrics[k]["values"]:
                if a[0]:
                    output += "{}{{{}}} {}\n".format(
                        k,
                        ",".join(
                            ['{}="{}"'.format(x, a[0][x]) for x in sorted(a[0].keys())]
                        ),
                        a[1],
                    )
                else:
                    output += "{} {}\n".format(k, a[1])
        return output

    def get_job_metrics(self):
        quantiles = [float(x) for x in self.args.quantiles.split(",")]
        run_count = []
        run_success_count = []
        run_failure_count = []
        run_duration_seconds = []
        run_duration_seconds_sum = []
        run_duration_seconds_count = []
        run_latency_seconds = []
        run_latency_seconds_sum = []
        run_latency_seconds_count = []
        last_run_exit_code = []
        last_run_schedule_time = []
        last_run_start_time = []
        last_run_stop_time = []

        for job in sorted(self.config.jobs.values()):
            runs = self.db.get_runs(job_names=[job.name])
            len_runs = len(runs)
            if len_runs > 0:
                last_run = sorted(runs, key=lambda run: run.stop_time)[-1]
            else:
                last_run = None
            run_count.append(({"job_name": job.name}, len_runs))
            run_success_count.append(
                (
                    {"job_name": job.name},
                    len([run for run in runs if run.exit_code == 0]),
                )
            )
            run_failure_count.append(
                (
                    {"job_name": job.name},
                    len([run for run in runs if run.exit_code != 0]),
                )
            )
            if last_run:
                for quantile in quantiles:
                    run_duration_seconds.append(
                        (
                            {"job_name": job.name, "quantile": str(quantile)},
                            percentile(
                                sorted(
                                    [
                                        (run.stop_time - run.start_time).total_seconds()
                                        for run in runs
                                    ]
                                ),
                                quantile,
                            ),
                        )
                    )
                    run_latency_seconds.append(
                        (
                            {"job_name": job.name, "quantile": str(quantile)},
                            percentile(
                                sorted(
                                    [
                                        (
                                            run.start_time - run.schedule_time
                                        ).total_seconds()
                                        for run in runs
                                    ]
                                ),
                                quantile,
                            ),
                        )
                    )
                run_duration_seconds_sum.append(
                    (
                        {"job_name": job.name},
                        sum(
                            [
                                (run.stop_time - run.start_time).total_seconds()
                                for run in runs
                            ]
                        ),
                    )
                )
                run_duration_seconds_count.append(({"job_name": job.name}, len_runs))
                run_latency_seconds_sum.append(
                    (
                        {"job_name": job.name},
                        sum(
                            [
                                (run.start_time - run.schedule_time).total_seconds()
                                for run in runs
                            ]
                        ),
                    )
                )
                run_latency_seconds_count.append(({"job_name": job.name}, len_runs))
                last_run_exit_code.append(({"job_name": job.name}, last_run.exit_code))
                last_run_schedule_time.append(
                    ({"job_name": job.name}, dt_to_epoch(last_run.schedule_time))
                )
                last_run_start_time.append(
                    ({"job_name": job.name}, dt_to_epoch(last_run.start_time))
                )
                last_run_stop_time.append(
                    ({"job_name": job.name}, dt_to_epoch(last_run.stop_time))
                )

        metrics = {
            "dsari_run_count": entry(
                run_count, type="counter", help="Number of runs performed for a job"
            ),
            "dsari_run_success_count": entry(
                run_success_count,
                type="counter",
                help="Number of successful runs performed for a job",
            ),
            "dsari_run_failure_count": entry(
                run_failure_count,
                type="counter",
                help="Number of failed runs performed for a job",
            ),
            "dsari_run_duration_seconds": entry(
                run_duration_seconds,
                type="summary",
                help="Length of time spent in a run",
            ),
            "dsari_run_duration_seconds_count": entry(
                run_duration_seconds_count, type=None, help=None
            ),
            "dsari_run_duration_seconds_sum": entry(
                run_duration_seconds_sum, type=None, help=None
            ),
            "dsari_run_latency_seconds": entry(
                run_latency_seconds,
                type="summary",
                help="Length of time spent between scheduled start and actual start",
            ),
            "dsari_run_latency_seconds_count": entry(
                run_latency_seconds_count, type=None, help=None
            ),
            "dsari_run_latency_seconds_sum": entry(
                run_latency_seconds_sum, type=None, help=None
            ),
            "dsari_last_run_exit_code": entry(
                last_run_exit_code, help="Numeric exit code of the last run for a job"
            ),
            "dsari_last_run_schedule_time": entry(
                last_run_schedule_time,
                help="Schedule time of the last run for a job, seconds since epoch",
            ),
            "dsari_last_run_start_time": entry(
                last_run_start_time,
                help="Start time of the last run for a job, seconds since epoch",
            ),
            "dsari_last_run_stop_time": entry(
                last_run_stop_time,
                help="Stop time of the last run for a job, seconds since epoch",
            ),
        }

        return metrics

    def get_running_metrics(self):
        running_run_schedule_time = []
        running_run_start_time = []

        for job in sorted(self.config.jobs.values()):
            runs = self.db.get_runs(job_names=[job.name], runs_running=True)
            for run in runs:
                running_run_schedule_time.append(
                    (
                        {"job_name": job.name, "run_id": run.id},
                        dt_to_epoch(run.schedule_time),
                    )
                )
                running_run_start_time.append(
                    (
                        {"job_name": job.name, "run_id": run.id},
                        dt_to_epoch(run.start_time),
                    )
                )

        metrics = {
            "dsari_running_run_schedule_time": entry(
                running_run_schedule_time,
                help="Schedule time of a currently running job, seconds since epoch",
            ),
            "dsari_running_run_start_time": entry(
                running_run_start_time,
                help="Start time of a currently running job, seconds since epoch",
            ),
        }

        return metrics

    def get_metrics(self):
        exporter_start = datetime.datetime.now()
        metrics = {}

        if (self.job_cache is None) or (
            (self.job_cache_time + datetime.timedelta(seconds=self.args.job_cache_time))
            < datetime.datetime.now()
        ):
            self.job_cache = self.get_job_metrics()
            self.job_cache_time = datetime.datetime.now()
        metrics.update(self.job_cache)

        if not self.args.no_running:
            metrics.update(self.get_running_metrics())

        metrics.update(
            {
                "dsari_time": entry(
                    [({}, time.time())], help="Current time, seconds since epoch"
                ),
                "dsari_exporter_collect_seconds": entry(
                    [({}, (datetime.datetime.now() - exporter_start).total_seconds())],
                    help="Time spent collecting metrics",
                ),
                "dsari_version_info": entry(
                    [({"version": __version__}, 1)],
                    help="dsari version information, constant value 1",
                ),
            }
        )

        return self.build_metrics_text(metrics)


class PrometheusHandler:
    def __init__(self, prom):
        self.prom = prom
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        lh_console = logging.StreamHandler()
        lh_console_formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s: %(message)s"
        )
        lh_console.setFormatter(lh_console_formatter)
        if self.prom.args.debug:
            lh_console.setLevel(logging.DEBUG)
        else:
            lh_console.setLevel(logging.INFO)
        self.logger.addHandler(lh_console)

        for signum in (signal.SIGHUP,):
            signal.signal(signum, self.signal_handler)

    def signal_handler(self, signum, frame):
        if signum == signal.SIGHUP:
            self.logger.info("SIGHUP received, reloading")
            self.prom.load_config()

    def __call__(self, environ, start_response):
        self.environ = environ
        self.start_response = start_response
        self.query_params = {}
        if "QUERY_STRING" in self.environ:
            self.query_params = parse_qs(self.environ["QUERY_STRING"])

        if self.environ["PATH_INFO"] != self.prom.args.metrics_path:
            body = b"Not Found"
            self.start_response(
                "404 Not Found",
                [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))],
            )
            return [body]

        body = self.prom.get_metrics().encode("utf-8")
        self.start_response(
            "200 OK",
            [
                ("Content-Type", "text/plain; version=0.0.4"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]


def main():
    args = parse_args(sys.argv[1:])
    r = Prometheus(args)
    if args.dump:
        output = r.get_metrics()
        sys.stdout.write(output)
    else:
        from wsgiref.simple_server import make_server

        application = PrometheusHandler(prom=Prometheus(args))
        srv = make_server(args.listen_address, args.listen_port, application)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    sys.exit(main())
else:
    wsgi_args = os.environ.get("WSGI_ARGS")
    if wsgi_args:
        wsgi_args = json.loads(wsgi_args)
    else:
        wsgi_args = []
    args = parse_args(wsgi_args)
    wsgi_application = PrometheusHandler(prom=Prometheus(args))
