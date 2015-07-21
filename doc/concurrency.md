# Concurrency

dsari recognizes and supports concurrency management.
Consider the following example configuration:

    {
        "jobs": {
            "job1": {
                "command": ["/bin/sleep", "90"],
                "schedule": "* * * * *"
            },
            "job2": {
                "command": ["/bin/sleep", "90"],
                "schedule": "* * * * *"
            },
            "job3": {
                "command": ["/bin/sleep", "90"],
                "schedule": "* * * * *"
            }
        }
    }

Since each of these jobs take 90 seconds to run, and each run every minute, there will be overlap, with multiple jobs running at the same time.
In this synthetic example it's not a problem, but if they were actual jobs which conflicted with each other or took significant resources, it could be a problem.

This can be managed with concurrency groups.
For example:

    {
        "jobs": {
            "job1": {
                "command": ["ssh", "host-a", "build_job1"],
                "concurrency_groups": ["host-a_group"],
                "schedule": "* * * * *"
            },
            "job2": {
                "command": ["ssh", "host-a", "build_job2"],
                "concurrency_groups": ["host-a_group"],
                "schedule": "* * * * *"
            },
            "job3": {
                "command": ["ssh", "host-a", "build_job3"],
                "concurrency_groups": ["host-a_group"],
                "schedule": "* * * * *"
            },
            "job4": {
                "command": ["ssh", "host-b", "build_job4"],
                "concurrency_groups": ["host-b_group"],
                "schedule": "* * * * *"
            },
            "job5": {
                "command": ["ssh", "host-b", "build_job5"],
                "concurrency_groups": ["host-b_group"],
                "schedule": "* * * * *"
            }
        },
        "concurrency_groups": {
            "host-a_group": {
                "max": 2
            }
        }
    }

Here, of the first three jobs ("job1", "job2" and "job3"), only two of them may be running at the same time, as they are all part of the "host-a_group" concurrency group, which is configured for a maximum of 2.
"job4" and "job5" are part of the "host-b_group" concurrency group, but this group is not defined.
In this case, the implicit limit is 1, so only "job4" or "job5" can be running at any given time, not both.

Jobs may belong to multiple concurrency groups, which can allow for run distribution.
For example:

    {
        "jobs": {
            "job1": {
                "command": ["build_job_wrapper"],
                "concurrency_groups": ["host-a_group", "host-b_group"],
                "schedule": "* * * * *"
            },
            "job2": {
                "command": ["build_job_wrapper"],
                "concurrency_groups": ["host-a_group", "host-b_group"],
                "schedule": "* * * * *"
            },
            "job3": {
                "command": ["build_job_wrapper"],
                "concurrency_groups": ["host-a_group", "host-b_group"],
                "schedule": "* * * * *"
            },
            "job4": {
                "command": ["build_job_wrapper"],
                "concurrency_groups": ["host-a_group", "host-b_group"],
                "schedule": "* * * * *"
            },
            "job5": {
                "command": ["build_job_wrapper"],
                "concurrency_groups": ["host-a_group", "host-b_group"],
                "schedule": "* * * * *"
            }
        },
        "concurrency_groups": {
            "host-a_group": {
                "max": 2
            },
            "host-b_group": {
                "max": 1
            }
        }
    }

Here, the scheduler will pick a viable target concurrency group from each job, ensuring that no more than 2 jobs are running as part of "host-a_group", and no more than 1 job is running as part of "host-b_group".
Each run will have the `CONCURRENCY_GROUP` environment variable set to the picked group, which our example `build_job_wrapper` can use (along with `JOB_NAME` and `RUN_ID`) to determine what to do.
(In this example, SSHing to host-a or host-b.)

If a scheduled run cannot be started due to concurrency limits, it is retried later on an exponential backoff scale, up to 5 minutes in the future.
If a job is configured for multiple concurrency groups, it will not be backed off unless all groups have reached their max.
