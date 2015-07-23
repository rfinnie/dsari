# dsari - Do Something and Record It

dsari is a lightweight continuous integration (CI) system.
It provides scheduling, concurrency management and trigger capabilities, and is easy to configure.
Job scheduling is handled via `dsari-daemon`, while `dsari-render` may be used to format job run information as HTML.

## Requirements

dsari requires Python 2.6 or later, and will run on Unix-based platforms.  It requires the following non-core modules:

  - [`croniter`](https://pypi.python.org/pypi/croniter/), for parsing cron-style schedule definitions
  - [`jinja2`](http://jinja.pocoo.org/), for rendering HTML reports

## Installation

dsari may be installed as any normal Python package:

    $ sudo python setup.py install

When this is done, dsari will expect its configuration file -- `dsari.json` -- in `/usr/local/etc/dsari/`, and will store its data in `/usr/local/lib/dsari/`.

These locations may be customized by passing `-c` argument to `dsari-*` to specify the configuration directory, and the `data_dir` configuration option, respectively.

When dsari is installed directly in `/usr/` (i.e. as part of distribution packaging), the default configuration and data directories will be `/etc/dsari/` and `/var/lib/dsari/`, respectively.

dsari does not need to be installed at all, it can be run directly from the repository directory.
In this case, the default configuration and data directories will be `~/.dsari/etc/` and `~/.dsari/var/`, respectively.

The rest of these documents assume a locally-running setup, i.e. `~/.dsari/`.

## Configuration

A basic configuration for `dsari.json` looks as follows:

    {
        "jobs": {
            "sample-job": {
                "command": ["/usr/bin/env"],
                "schedule": "H/5 * * * *"
            }
        }
    }

This defines a job named "sample-job", which is run every 5 minutes.
Many more configuration options are available in the `doc/` directory.

## Running

Once dsari is configured, run `dsari-daemon`.
By default, `dsari-daemon` will run in the foreground, and can be used with a supervisor (upstart, systemd, supervisord, etc).
If given `-d`, it will daemonize.

When a job is scheduled to be run, it produces a "run".
Runs are identified by a UUID, the run output is stored in `~/.dsari/var/runs/`, and data related to the run (start time, stop time, exit code, etc) is stored in a SQLite database at `~/.dsari/var/dsari.sqlite3`.

When a run is executed, several environment variables are passed to the program to be run:

    JOB_NAME=sample-job
    RUN_ID=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
    PREVIOUS_RUN_ID=e5bd61b3-27f3-46ca-8169-372433056fc2
    PREVIOUS_SCHEDULE_TIME=1437004689.27
    PREVIOUS_START_TIME=1437004689.65
    PREVIOUS_STOP_TIME=1437004689.71
    PREVIOUS_EXIT_CODE=0

`PREVIOUS_*` variables are not set if there is no previous run.
In addition, several extra environment variables are present, if the job's `jenkins_environment` option is set, to aid with migrations from Jenkins setups:

    BUILD_NUMBER=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
    BUILD_ID=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
    BUILD_URL=file:///home/user/.dsari/var/runs/sample-job/fa0490b8-7a8e-4f6b-b73c-160199a9ff75/
    NODE_NAME=master
    BUILD_TAG=dsari-sample-job-fa0490b8-7a8e-4f6b-b73c-160199a9ff75
    JENKINS_URL=file:///home/user/.dsari/var/
    EXECUTOR_NUMBER=0
    WORKSPACE=/home/user/.dsari/var/runs/sample-job/fa0490b8-7a8e-4f6b-b73c-160199a9ff75

## Reports

To render HTML reports, run `dsari-render` occasionally.
This will produce a series of HTML files in `~/.dsari/var/html/`.
You may then serve these files, rsync them to a remote server, etc.

## License

dsari - Do Something and Record It

Copyright (C) 2015 [Ryan Finnie](http://www.finnie.org/)

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
02110-1301, USA.

