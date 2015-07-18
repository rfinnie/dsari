# Configuration

dsari is configured via a JSON file, `dsari.json`.
Here is a sample format:

    {
        "shutdown_kill_runs": true,
        "jobs": {
            "sample-job": {
                "command": ["/usr/bin/env"],
                "schedule": "H/5 * * * *",
                "concurrency_groups": ["sample-group"]
            }
        },
        "concurrency_groups": {
            "sample-group": {
                "max": 1
            }
        }
    }

## Main

Main options are in the root of the configuration array.

    "data_dir": "/path/to/data/dir"

Overridden path to the data (var) directory.

Default: (varies by installation)

    "shutdown_kill_runs": true

When `dsari-daemon` is shut down (via SIGTERM or SIGINT), this controls what to do with running jobs.
If false, `dsari-daemon` waits until running jobs complete naturally, but no new jobs are run.
If true, `dsari-daemon` sends a SIGTERM to running jobs and waits for them to finish.

Default: false

    "shutdown_kill_grace": 5.0

If set and `shutdown_kill_runs` is true, this is the grace period allowed between a SIGTERM and a SIGKILL.
Note that individual jobs also have a grace period ("max_execution_grace"), which will be considered as well during a shutdown.

Default: null

    "template_dir": "/path/to/custom/templates"

If set, this directory is also checked by `dsari-render`, and templates in it will override default templates.

## Jobs

"jobs" is an associative array of job definitions, each of which is an associative array.
Each job definition may have the following options:

    "command": ["ssh", "host", "command"]

An array of the command arguments to be run.
The command is searched against the PATH used to start `dsari-daemon`.

Default: null (but required)

    "command_append_run": true

If true, two arguments are appended to the command when run: the job name, and the run ID.

Default: false

    "schedule": "H/5 * * * *"

The [schedule format](schedule-format.md) definition.
If not set, no recurring schedule is set up, and the job only responds to [manual triggers](triggers.md).

Default: null

    "environment": {
        "ENV_NAME": "value"
    }

An associative array of environment variables to be set for the job's run.

Default: {}

    "max_execution": 300.0

The maximum number of seconds to wait for a run to finish.
If reached, the run will be sent a SIGTERM.
If the run does not exit within "max_execution_grace" seconds of the SIGTERM, it will be sent a SIGKILL.

Default: null (wait forever)

    "max_execution_grace": 60.0

The number of seconds to wait after a SIGTERM before the run is sent a SIGKILL.
If "max_execution" is set and reached, the run will be sent a SIGTERM.
If the run does not exit within this number of seconds of the SIGTERM, it will be sent a SIGKILL.

Default: 60.0

    "concurrency_groups": ["group-a", "group-b"]

A list of [concurrency groups](concurrency.md) the job is a member of.

Default: []

    "render_reports:" false

If false, the job and all of its runs will be hidden from `dsari-render`.

Default: true

## Concurrency Groups

"concurrency_groups" is an associative array of [concurrency group](concurrency.md) definitions, each of which is an associative array.
Each concurrency group definition may have the following options:

    "max": 2

The maximum number of jobs which may be concurrently running in a concurrency group.

Default: 1
