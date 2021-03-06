% DSARI-INFO(1) | dsari
% Ryan Finnie
# NAME

dsari-info - dsari job/run information

# SYNOPSIS

dsari-info *argument* [*options*]

# DESCRIPTION

`dsari-info` lets you filter and output the dsari job configuration and run data.

# ARGUMENTS

config check
:   Check the configuration, return 0 for a valid configuration or 1 for invalid.

    Options: None

config dump
:   Dump a compiled, assembled configuration.

    Options: *\-\-raw*, *\-\-format*

job list
:   List known jobs.
    Note that while *\-\-format=yaml* or *\-\-format=json* look like valid job configurations, they are not guaranteed to be.
    For a guaranteed loadable configuration, use *dump-config* instead.

    Options: *\-\-job*, *\-\-format*

run list
:   List recorded runs.

    Options: *\-\-job*, *\-\-run*, *\-\-format*

run output *run_id*
:   Print the collected output of a run.
    If a run is currently running, output collected until that point will be printed.

run tail [*run_id* [*run_id* [...]]]
:   Monitor the output of running runs, as they are collected.
    If no runs specified, tail all running runs.

shell
:   Enter a Python shell, with several dsari-specific variables pre-loaded (config, db, etc).

# OPTIONS

\-\-config-dir=*directory*, -c *directory*
:   Base configuration directory.
    A file named `dsari.yaml` and/or `dsari.json` is expected in this directory.

\-\-job=*job_name* [\-\-job=*job_name*]
:   Job name to filter.
    Can be given multiple times.

\-\-run=*run_id* [\-\-run=*run_id*]
:   Run ID to filter.
    Can be given multiple times.

\-\-format=*format*
:   Output format to present data in.
    Valid values: *pretty* (default), *tabular*, *json*, *yaml*

\-\-raw
:   For *dump-config*, instead of a compiled/normalized config, output the raw JSON config.

# SEE ALSO

* `dsari-daemon`
* [dsari](https://github.com/rfinnie/dsari)
