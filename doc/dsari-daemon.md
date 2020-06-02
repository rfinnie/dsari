% DSARI-DAEMON(1) | dsari
% Ryan Finnie
# NAME

dsari-daemon - dsari scheduling daemon

# SYNOPSIS

dsari-daemon [*options*]

# DESCRIPTION

`dsari-daemon` is a scheduling daemon.
It reads a configuration file containing job information, and schedules runs of the jobs.

# OPTIONS

--config-dir=*directory*, -c *directory*
:   Base configuration directory.
    Files named `dsari.yaml` and/or `dsari.json` are expected in this directory.

--fork
:   Fork into the background after starting.

--debug
:   Print extra debugging information while running.

# SIGNALS

*SIGINT* (^C), *SIGTERM*
:   Begin shutdown of the daemon.
    By default, all scheduled runs will be cancelled, and any runs in progress will be left to complete naturally.
    The `shutdown_kill_runs` configuration option changes this behavior.

*SIGHUP*
:   Reload the configuration.
    If a job's configuration changes while a run is in progress, its changes will take effect once the run is complete.

*SIGQUIT* (^\\\\)
:   Outputs the current status of the `dsari-daemon` process, including which jobs have runs in progress, and when the jobs' next runs are scheduled for.

# SEE ALSO

* `dsari-render`
* [dsari](https://github.com/rfinnie/dsari)
