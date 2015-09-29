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

    "jenkins_environment": true

If true, several extra environment variables are available to the run, to aid with migrations from Jenkins setups:

*   `BUILD_NUMBER=fa0490b8-7a8e-4f6b-b73c-160199a9ff75`
*   `BUILD_ID=fa0490b8-7a8e-4f6b-b73c-160199a9ff75`
*   `BUILD_URL=file:///home/user/.dsari/var/runs/sample-job/fa0490b8-7a8e-4f6b-b73c-160199a9ff75/`
*   `NODE_NAME=master`
*   `BUILD_TAG=dsari-sample-job-fa0490b8-7a8e-4f6b-b73c-160199a9ff75`
*   `JENKINS_URL=file:///home/user/.dsari/var/`
*   `EXECUTOR_NUMBER=0`
*   `WORKSPACE=/home/user/.dsari/var/runs/sample-job/fa0490b8-7a8e-4f6b-b73c-160199a9ff75`

These values may not be ideal in all situations (e.g. a migrated Jenkins job may expect a VCS checkout in `WORKSPACE`), but are present for maximum Jenkins compatibility.
They can be individually overridden by explicit `environment` options.

Default: false

    "job_group": "sample-job"

If set, the `JOB_GROUP` environment variable is set to this during a run.
Normally this is not set by hand, but is set automatically when a job_groups definition (see below) is expanded into multiple jobs.

Default: none

    "concurrent_runs": true

By default, dsari will not allow a job's scheduled or triggered run to be run while the job has an existing running run.
For example, a trigger may be detected while a scheduled run is running, or a long-running run overlaps with the next scheduled run of the job.
If this happens, the next run will be executed after the existing run is finished.

If "concurrent_runs" is true for a job, multiple runs of the same job can run concurrently at the times they are scheduled, regardless of whether a job has a run currently executing..

Default: false

## Job Groups

"job_groups" is an associative array of job group definitions.
A job group accepts all standard job options, plus the addition of the list "job_names".
Job groups are a way to save configuration effort when you have multiple jobs with the same configuration.

For example, this:

    {
        "job_groups": {
            "sample-jobs": {
                "job_names": [
                    "sample-job-1",
                    "sample-job-2"
                ],
                "command": ["job-wrapper"],
                "schedule": "H H * * *"
            }
        }
    }

is the exact same as this:

    {
        "jobs": {
            "sample-job-1": {
                "command": ["job-wrapper"],
                "schedule": "H H * * *",
                "job_group": "sample-jobs"
            },
            "sample-job-2": {
                "command": ["job-wrapper"],
                "schedule": "H H * * *",
                "job_group": "sample-jobs"
            }
        }
    }

When a job_groups definition is internally expanded into multiple jobs, the group name is added to each job as "job_group", which sets the `JOB_GROUP` environment variable.

## Concurrency Groups

"concurrency_groups" is an associative array of [concurrency group](concurrency.md) definitions, each of which is an associative array.
Each concurrency group definition may have the following options:

    "max": 2

The maximum number of jobs which may be concurrently running in a concurrency group.

Default: 1
