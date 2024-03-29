# dsari - Do Something and Record It

![ci](https://github.com/rfinnie/dsari/workflows/ci/badge.svg)

dsari is a lightweight continuous integration (CI) system.
It provides scheduling, concurrency management and trigger capabilities, and is easy to configure.
Job scheduling is handled via `dsari-daemon`, while `dsari-render` may be used to format job run information as HTML.

## Requirements

dsari requires Python 3.6 or later, and will run on Unix-based platforms.
It may use the following non-core packages:

  - [`PyYAML`](https://pypi.org/project/PyYAML/), for using YAML files as configuration files, triggers, etc
  - [`croniter`](https://pypi.python.org/pypi/croniter), for parsing cron-style schedule definitions
  - [`python-dateutil`](https://pypi.python.org/pypi/python-dateutil), for parsing iCalendar RRULE-style schedule definitions, parsing human-readable trigger times, timezone support, etc (strongly recommended)
  - [`Jinja2`](https://pypi.python.org/pypi/Jinja2), for rendering HTML reports
  - [`IPython`](https://pypi.python.org/pypi/ipython), for better `dsari-info shell` interaction
  - [`termcolor`](https://pypi.python.org/pypi/termcolor), for colorized `dsari-info` TTY output
  - [`psycopg2`](https://pypi.python.org/pypi/psycopg2), for PostgreSQL database support
  - [`mysqlclient`](https://pypi.python.org/pypi/mysqlclient) (mysqldb), for MySQL database support
  - [`pymongo`](https://pypi.python.org/pypi/pymongo), for MongoDB database support

All non-core packages are optional, with the following limitations:

  - PyYAML is strongly recommended because people tend to prefer writing configuration files in YAML over JSON.
  - If neither `croniter` nor `python-dateutil` are installed, `dsari-daemon` will run, but it will not process scheduled runs (i.e. manual triggers only).
  - `Jinja2` is only required if you intend to use `dsari-render`.
  - `psycopg2`, `mysqlclient` or `pymongo` are only required if you intend to use dsari with an alternative database.
    By default, dsari uses a SQLite 3 database.

## Installation

dsari may be installed as any normal Python package:

```
$ sudo python3 setup.py install
```

When this is done, dsari will expect its configuration file -- `dsari.yaml` and/or `dsari.json` -- in `/usr/local/etc/dsari/`, and will store its data in `/usr/local/lib/dsari/`.

These locations may be customized by passing `-c` argument to `dsari-*` to specify the configuration directory, and the `data_dir` configuration option, respectively.

When dsari is installed directly in `/usr/` (i.e. as part of distribution packaging), the default configuration and data directories will be `/etc/dsari/` and `/var/lib/dsari/`, respectively.

dsari does not need to be installed at all, it can be run directly from the repository directory.
In this case, the default configuration and data directories will be `~/.dsari/etc/` and `~/.dsari/var/`, respectively.

The rest of these documents assume a locally-running setup, i.e. `~/.dsari/`.

## Configuration

A basic configuration for `dsari.yaml` looks as follows:

```yaml
jobs:
  sample-job:
    command:
    - /usr/bin/env
    schedule: "H/5 * * * *"
```

or for `dsari.json`:

```json
{
    "jobs": {
        "sample-job": {
            "command": ["/usr/bin/env"],
            "schedule": "H/5 * * * *"
        }
    }
}
```

This defines a job named "sample-job", which is run every 5 minutes.
Many more configuration options are available in the `doc/` directory.

## Running

Once dsari is configured, run `dsari-daemon`.
By default, `dsari-daemon` will run in the foreground, and can be used with a supervisor (upstart, systemd, supervisord, etc).
If given `-d`, it will daemonize.

When a job is scheduled to be run, it produces a "run".
Runs are identified by a UUID, the run output is stored in `~/.dsari/var/runs/`, and data related to the run (start time, stop time, exit code, etc) is stored in a SQLite database at `~/.dsari/var/dsari.sqlite3`.

When a run is executed, several environment variables are passed to the program to be run:

```bash
CI=true
DSARI=true
JOB_NAME=sample-job
RUN_ID=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
PREVIOUS_RUN_ID=e5bd61b3-27f3-46ca-8169-372433056fc2
PREVIOUS_SCHEDULE_TIME=1437004689.27
PREVIOUS_START_TIME=1437004689.65
PREVIOUS_STOP_TIME=1437004689.71
PREVIOUS_EXIT_CODE=0
```

`PREVIOUS_*` variables are not set if there is no previous run.
In addition, several extra environment variables are present, if the job's `jenkins_environment` option is set, to aid with migrations from Jenkins setups:

```bash
BUILD_NUMBER=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
BUILD_ID=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
BUILD_URL=file:///home/user/.dsari/var/runs/sample-job/fa0490b8-7a8e-4f6b-b73c-160199a9ff75/
NODE_NAME=master
BUILD_TAG=dsari-sample-job-fa0490b8-7a8e-4f6b-b73c-160199a9ff75
JENKINS_URL=file:///home/user/.dsari/var/
EXECUTOR_NUMBER=0
WORKSPACE=/home/user/.dsari/var/runs/sample-job/fa0490b8-7a8e-4f6b-b73c-160199a9ff75
```

## Reports

To render HTML reports, run `dsari-render` occasionally.
This will produce a series of HTML files in `~/.dsari/var/html/`.
You may then serve these files, rsync them to a remote server, etc.

The `dsari-info` command may be used to retrieve information about jobs and runs.

The `dsari-prometheus-exporter` command may be used to start a metrics daemon suitable for ingestion into [Prometheus](https://prometheus.io/).

## License

dsari - Do Something and Record It

Copyright (C) 2015-2021 [Ryan Finnie](https://www.finnie.org/)

This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
