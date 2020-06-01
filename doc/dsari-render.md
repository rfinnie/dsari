% DSARI-RENDER(1) | dsari
% Ryan Finnie
# NAME

dsari-render - dsari HTML report rendering

# SYNOPSIS

dsari-render [*options*]

# DESCRIPTION

`dsari-render` takes data produced by `dsari-daemon`, and formats it as HTML reports.

# OPTIONS

--config-dir=*directory*, -c *directory*
:   Base configuration directory.
    Files named `dsari.yaml` and/or `dsari.json` are expected in this directory.

--regenerate, -r
:   (Re)generate all report files, even if `dsari-render` determines regeneration is not needed.

--debug
:   Print extra debugging information while running.

# SEE ALSO

* `dsari-daemon`
* [dsari](https://github.com/rfinnie/dsari)

