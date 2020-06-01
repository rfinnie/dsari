# Triggers

In most situations, job runs are triggered on a recurring schedule.
However, you may also trigger a run manually.
It can be as simple as the following:

    $ mkdir -p ~/.dsari/var/trigger/sample-job
    $ echo '{}' >~/.dsari/var/trigger/sample-job/trigger.yaml

The daemon will notice this trigger within 60 seconds, set up a new one-off run, and delete the trigger file.
If you want the trigger to be noticed sooner, send dsari-daemon a USR1 signal.

A trigger file may be valid YAML (`trigger.yaml`) or JSON (`trigger.json`).
If both `trigger.yaml` and `trigger.json` exist when the trigger directory is scanned, `trigger.json` will be taken over `trigger.yaml`.

The contents of the trigger file can be as simple as the empty dict above, but it can also be more complex.
For example, you could write a script which periodically checks a git repository and triggers a run when a new commit is detected.
That script could produce `trigger.json` which looks like this:

```json
{
    "type": "git",
    "description": "A new commit has been detected",
    "environment": {
        "GIT_COMMIT": "d1700a76c4e703040fa4545c9a40d702fb23e8eb",
        "GIT_AUTHOR": "Joe User <joe@example.com>"
    }
}
```

The contents of the "environment" dict are set as environment variables in the run.
"type" and "description" are rendered in the HTML report; if "type" is not specified, it is shown simply as "file" in the HTML report.

By default, triggered runs will be run immediately, but can also be scheduled for the future using an epoch time:

```json
{
    "schedule_time": 1473546507
}
```

Or, if the `python-dateutil` Python package is installed, ISO 8601 times may be specified:

```json
    {
        "schedule_time": "2016-09-10T14:28:27"
    }
```

Care should be taken when scheduling in the future via triggers, as scheduled triggers do not survive across `dsari-daemon` restarts or reloads.

If the job does not have `concurrent_runs` set (default behavior), the triggered run replaces any existing scheduled run, ensuring only one run will be running at any given time.
Afterward, runs will be scheduled as normal, if configured for scheduled runs.
If the job does have `concurrent_runs` set, the triggered run will simply be scheduled as an additional run, regardless of existing triggered runs, scheduled runs or running runs.
