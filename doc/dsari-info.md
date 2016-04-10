% DSARI-INFO(1) | dsari
% Ryan Finnie
# NAME

dsari-info - dsari job/run information

# SYNOPSIS

dsari-info *argument* [*options*]

# DESCRIPTION

`dsari-info` lets you filter and output the dsari job configuration and run data.

# ARGUMENTS

dump-config
:   Dump a compiled, assembled configuration.

    Options: none

list-jobs
:   List known jobs.
    Note that while *list-jobs* *--format=json* looks like a valid job configuration array for dsari.json, it is not guaranteed to be.
    For a guaranteed loadable configuration, use *dump-config*.

    Options: *--job*, *--format*

list-runs
:   List recorded runs.

    Options: *--job*, *--run*, *--format*, *--epoch*

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
    Valid values: *tabular* (default), *json*, *yaml*.

--epoch
:   Output times in Unix epoch format (seconds since 1970-01-01), instead of ISO 8601.

# SEE ALSO

* `dsari-daemon`
* [dsari](https://github.com/rfinnie/dsari)
