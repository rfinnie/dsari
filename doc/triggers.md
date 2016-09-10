# Triggers

In most situations, job runs are triggered on a recurring schedule.
However, you may also trigger a run manually.
It can be as simple as the following:

    $ mkdir -p ~/.dsari/var/trigger/sample-job
    $ echo '{}' >~/.dsari/var/trigger/sample-job/trigger.json

The daemon will notice this trigger within 60 seconds, set up a new one-off run, and delete the trigger JSON file.

The contents of the JSON file can be as simple as the empty dict above, but it can also be more complex.
For example, you could write a script which periodically checks a git repository and triggers a run when a new commit is detected.
That script could produce JSON which looks like this:

    {
        "type": "git",
        "description": "A new commit has been detected",
        "environment": {
            "GIT_COMMIT": "d1700a76c4e703040fa4545c9a40d702fb23e8eb",
            "GIT_AUTHOR": "Joe User <joe@example.com>"
        }
    }

The contents of the "environment" dict are set as environment variables in the run.
"type" and "description" are rendered in the HTML report; if "type" is not specified, it is shown simply as "file" in the HTML report.

By default, triggered runs will be run immediately, but can also be scheduled for the future using an epoch time:

    {
        "schedule_time": 1473546507
    }

Or, if the `python-dateutil` Python package is installed, ISO 8601 times may be specified:

    {
        "schedule_time": "2016-09-10T14:28:27"
    }

Care should be taken when scheduling in the future via triggers, as scheduled triggers do not survive across `dsari-daemon` restarts.
