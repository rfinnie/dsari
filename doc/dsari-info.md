% DSARI-INFO(1) | dsari
% Ryan Finnie
# NAME

dsari-info - dsari job/run information

# SYNOPSIS

dsari-info *argument* [*options*]

# DESCRIPTION

`dsari-info` lets you filter and output the dsari job configuration and run data.

# ARGUMENTS

check-config
:   Check the configuration, return 0 for a valid configuration or 1 for invalid.

    Options: None

dump-config
:   Dump a compiled, assembled configuration.

    Options: *--raw*

list-jobs
:   List known jobs.
    Note that while *list-jobs* *--format=json* looks like a valid job configuration array for dsari.json, it is not guaranteed to be.
    For a guaranteed loadable configuration, use *dump-config*.

    Options: *--job*, *--format*

list-runs
:   List recorded runs.

    Options: *--job*, *--run*, *--format*, *--epoch*

get-run-output *run_id*
:   Print the collected output of a run.
    If a run is currently running, output collected until that point will be printed.

tail-run-output *run_id*
:   Monitor the collected output of a run as it is collected.

shell
:   Enter a Python shell, with several dsari-specific variables pre-loaded (config, db, etc).

# OPTIONS

--config-dir=*directory*, -c *directory*
:   Base configuration directory.
    A file named `dsari.json` is expected in this directory.

--job=*job_name* [--job=*job_name*]
:   Job name to filter.
    Can be given multiple times.

--run=*run_id* [--run=*run_id*]
:   Run ID to filter.
    Can be given multiple times.

--format=*format*
:   Output format to present data in.
    Valid values: *tabular* (default), *json*

--epoch
:   Output times in Unix epoch format (seconds since 1970-01-01), instead of ISO 8601.

--raw
:   For *dump-config*, instead of a compiled/normalized config, output the raw JSON config.

# SEE ALSO

* `dsari-daemon`
* [dsari](https://github.com/rfinnie/dsari)
