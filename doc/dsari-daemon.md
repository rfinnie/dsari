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
    A file named `dsari.json` is expected in this directory.

--daemonize, -d
:   Fork into the background after starting.

--debug
:   Print extra debugging information while running.

# SEE ALSO

* `dsari-render`
* [dsari](https://github.com/rfinnie/dsari)