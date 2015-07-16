# Getting Started

## Installation

dsari may be installed as any normal Python package:

```
$ sudo python setup.py install
```

When this is done, dsari will expect its configuration file -- `dsari.json` -- in `/usr/local/etc/dsari/`, and will store its data in `/usr/local/lib/dsari/`.

These locations may be customized by passing `-c` argument to `dsari-*` to specify the configuration directory, and the `data_dir` configuration option, respectively.

When dsari is installed directly in `/usr/` (i.e. as part of distribution packaging), the default configuration and data directories will be `/etc/dsari/` and `/var/lib/dsari`, respectively.

dsari does not need to be installed at all, it can be run directly from the repository directory.  In this case, the default configuration and data directories will be `~/.dsari/etc/` and `~/.dsari/var/`, respectively.

The rest of these documents assume a locally-running setup, i.e. `~/.dsari/`.

## Configuration

A basic configuration for `dsari.json` looks as follows:

```
{
    "jobs": {
        "sample-job": {
            "command": ["/usr/bin/env"],
            "schedule": "*/5 * * * *"
        }
    }
}
```

This defines a job named "sample-job", which is run every 5 minutes.  Many more [configuration options](configuration.md) are available, and an explanation of the [schedule format](scheduler.md) is also available.

## Running

Once dsari is configured, run `dsari-daemon`.  Despite its name, `dsari-daemon` does not fork itself to the background; it is up to you to run it with an appropriate supervisor (upstart, systemd, supervisord, etc).

When a job is scheduled to be run, it produces a "run".  Runs are identified by a UUID, the run output is stored in `~/.dsari/var/runs/`, and data related to the run (start time, stop time, exit code, etc) is stored in a SQLite database at `~/.dsari/var/dsari.sqlite3`.

When a run is executed, several environment variables are passed to the program to be run:

```
JOB_NAME=sample-job
RUN_ID=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
PREVIOUS_RUN_ID=e5bd61b3-27f3-46ca-8169-372433056fc2
PREVIOUS_START_TIME=1437004689.65
PREVIOUS_STOP_TIME=1437004689.71
PREVIOUS_EXIT_CODE=0
```

`PREVIOUS_*` variables are not set if there is no previous run.  In addition, several extra environment variables are set to aid with migrations from Jenkins setups:

```
BUILD_NUMBER=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
BUILD_ID=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
BUILD_TAG=dsari-sample-job-fa0490b8-7a8e-4f6b-b73c-160199a9ff75
```

## Reports

To render HTML reports, run `dsari-render` occasionally.  This will produce a series of HTML files in `~/.dsari/var/html/`.  You may then serve these files, rsync them to a remote server, etc.
