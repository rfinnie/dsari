# Run Environment Variables

Runs can have many environment variables set automatically or manually, to assist the command script in performing the desired task.
Some variables are always set, and some are set according to the manner in which the run was scheduled.
Arbitrary variables can be set in the job definition, and in the run trigger.

A run's environment is set built from scratch, and does not inherit `dsari-daemon`'s environment.
For example, the MAILNAME of the user starting `dsari-daemon` is not set, even if it was present in the environment.

## Standard

The following variables should always be present in a run:

    LOGNAME=user
    HOME=/home/user
    PWD=/home/user/.dsari/var/runs/sample-job/fa0490b8-7a8e-4f6b-b73c-160199a9ff75
    PATH=/usr/bin:/bin
    JOB_NAME=sample-job
    RUN_ID=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
    SCHEDULE_TIME=1460822675.99
    START_TIME=1460822677.34
    TRIGGER_TYPE=schedule

### LOGNAME / HOME

Username and home directory of the running user.
This should be present in almost all cases, but if `dsari-daemon` cannot determine the running user from the system password database, they will not be set.

### PWD

Working directory of the current run, same as the cwd when the run command is started.
Shells such as bash will modify PWD when the directory is changed, but compiled programs and other scripting languages will not.
PWD may be set in the job configuration and/or trigger environment to set the initial cwd of the run.

### PATH

Inherited from the process calling `dsari-daemon`.
If it cannot be determined, it's set to "/usr/bin:/bin".

### DATA_DIR

The configured data base directory.
This may be used to construct a trigger path (${DATA_DIR}/trigger/${OTHER_JOB}/trigger.json) for cascading job runs.

### JOB_NAME

The defined name of the running job.

### RUN_ID

An automatically created UUID to uniquely identify the run.

### RUN_DIR

The directory used by the run for storing the execution output (output.txt).
By default, this will be the same as PWD at command execution time, but shells will usually update PWD when the cwd is changed during the script (see above).
PWD may also be defined by the job and/or trigger and hence may be different at command execution time, so RUN_DIR may be easily referred to for knowing where output.txt is stored.

### SCHEDULE_TIME

Unix epoch time when the run was scheduled or triggered.

### START_TIME

Unix epoch time when the run actually began, sometime after SCHEDULE_TIME.

### TRIGGER_TYPE

The type of event which triggered the run, either "schedule" or "file".

## Conditional

The following variables may be present depending on how the job and/or run were set up:

    CONCURRENCY_GROUP=host-a_group
    JOB_GROUP=common-jobs
    PREVIOUS_RUN_ID=281b8322-cf1d-44f4-8d23-889a6c5051e9
    PREVIOUS_SCHEDULE_TIME=1460224658.62
    PREVIOUS_START_TIME=1460224658.84
    PREVIOUS_STOP_TIME=1460224661.02
    PREVIOUS_EXIT_CODE=0
    PREVIOUS_GOOD_RUN_ID=281b8322-cf1d-44f4-8d23-889a6c5051e9
    PREVIOUS_GOOD_SCHEDULE_TIME=1460224658.62
    PREVIOUS_GOOD_START_TIME=1460224658.84
    PREVIOUS_GOOD_STOP_TIME=1460224661.02
    PREVIOUS_GOOD_EXIT_CODE=0
    PREVIOUS_BAD_RUN_ID=0edc1a75-9a2e-4588-8722-fc52596b6041
    PREVIOUS_BAD_SCHEDULE_TIME=1460216442.33
    PREVIOUS_BAD_START_TIME=1460216443.14
    PREVIOUS_BAD_STOP_TIME=1460216484.66
    PREVIOUS_BAD_EXIT_CODE=2

### CONCURRENCY_GROUP

Set to the picked [concurrency group](concurrency.md), if the job has the `concurrency_groups` option set.

### JOB_GROUP

Set to the job group name, if the job is part of a job group.

### PREVIOUS_RUN_ID

Set to the previous run UUID, if a previous run has been completed.

### PREVIOUS_SCHEDULE_TIME / PREVIOUS_START_TIME / PREVIOUS_STOP_TIME

Unix epoch times of the previous run.
Start time and stop time are when the run command actually began and ended, while the schedule time is when the run was scheduled to begin.
PREVIOUS_SCHEDULE_TIME is always equal to or before PREVIOUS_START_TIME, but may be significantly earlier due to blocking on a free concurrency group.

### PREVIOUS_EXIT_CODE

Numeric exit code of the previous run.

### PREVIOUS_GOOD_*

Set if a previous run has been completed, and it was a good (exit 0) run.
Due to this, if set, PREVIOUS_GOOD_EXIT_CODE will always be 0.

### PREVIOUS_BAD_*

Set if a previous run has been completed, and it was a bad (not exit 0) run.

## Jenkins-Compatible

The following variables are set if the job has the `jenkins_envionment` option set:

    BUILD_ID=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
    BUILD_NUMBER=fa0490b8-7a8e-4f6b-b73c-160199a9ff75
    BUILD_TAG=dsari-sample-job-fa0490b8-7a8e-4f6b-b73c-160199a9ff75
    BUILD_URL=file:///home/user/.dsari/var/runs/sample-job/fa0490b8-7a8e-4f6b-b73c-160199a9ff75/
    EXECUTOR_NUMBER=0
    JENKINS_URL=file:///home/user/.dsari/var/
    NODE_NAME=master
    WORKSPACE=/home/user/.dsari/var/runs/sample-job/fa0490b8-7a8e-4f6b-b73c-160199a9ff75

### BUILD_ID / BUILD_NUMBER

Set to the value of RUN_ID.

### BUILD_TAG

Set to dsari-${JOB_NAME}-${RUN_ID}.

### BUILD_URL

Set to a URL representation of the run directory (cwd of the run).

### EXECUTOR_NUMBER

Always set to 0.

### JENKINS_URL

Set to a URL representation of the base var directory of the dsari installation.

### NODE_NAME

Always set to "master".

### WORKSPACE

Set to the run directory (cwd of the run).

## Global-Defined Configuration

The global dsari.json may have multiple arbitrary variables set for all jobs' runs in the installation.
For example:

    {
        "environment": {
            "INSTALLATION_LOCATION": "dc-west",
            "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        }
    }

would produce:

    INSTALLATION_LOCATION=dc-west
    PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin/sbin

Globally-defined variables always override automatically-generated variables.
In certain situations this is desirable (for example, PATH), but it wouldn't be a good idea to override e.g. RUN_ID.

## Job-Defined

The run can have multiple arbitrary variables set as defined in the job's JSON.
For example:

    {
        "jobs": {
            "example_job": {
                "environment": {
                    "JOB_LOCATION": "datacenter",
                    "JOB_CONTACT": "Jane User <jane@example.com>",
                    "PATH": "/usr/local/bin:/usr/bin:/bin"
                }
            }
        }
    }

would produce:

    JOB_LOCATION=datacenter
    JOB_CONTACT="Jane User <jane@example.com>"
    PATH=/usr/local/bin:/usr/bin:/bin

Job-defined variables always override globally-defined and automatically-generated variables.

## Trigger-Defined

[Triggers](triggers.md) may also set environment variables.
For example:

    {
        "type": "git",
        "description": "A new commit has been detected",
        "environment": {
            "GIT_COMMIT": "d1700a76c4e703040fa4545c9a40d702fb23e8eb",
            "GIT_AUTHOR": "Joe User <joe@example.com>"
        }
    }

would produce:

    GIT_COMMIT=d1700a76c4e703040fa4545c9a40d702fb23e8eb
    GIT_AUTHOR="Joe User <joe@example.com>"

Trigger-defined variables always override job-defined, globally-defined and automatically-generated variables.
