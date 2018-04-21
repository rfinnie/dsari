% DSARI-PROMETHEUS-EXPORTER(1) | dsari
% Ryan Finnie
# NAME

dsari-prometheus-exporter - dsari Prometheus metrics exporter

# SYNOPSIS

dsari-prometheus-exporter [*options*]

# DESCRIPTION

`dsari-prometheus-exporter` takes data produced by `dsari-daemon`, and serves metrics suitable for ingestion into [Prometheus](https://prometheus.io/).

# OPTIONS

--config-dir=*directory*, -c *directory*
:   Base configuration directory.
    A file named `dsari.json` is expected in this directory.

--debug
:   Print extra debugging information while running.

--metrics-path=*path*
:   Path to serve metrics from in daemon mode (default `/metrics`).

--listen-address=*address*
:   IP address to listen on in daemon mode (default `0.0.0.0`).

--listen-port=*port*
:   Port address to listen on in daemon mode (default `50575`).

--job-cache-time=*seconds*
:   Seconds to cache non-running run metrics (default `120`).

--quantiles=*quantiles*
:   Comma-separated list of quantiles to use for summaries (default `0.01,0.1,0.5,0.9,0.99`).

--no-running
:   Do not gather running run metrics.

--dump
:   Dump metrics to stdout and exit, do not start daemon.

# WSGI

Instead of using its built-in daemon, `dsari-prometheus-exporter` may be run as a WSGI application.
To use, call the `dsari.prometheus_exporter:wsgi_application` application.

When run as a WSGI application, you may send the `WSGI_ARGS` environment variable, containing a JSON list of arguments.

# SEE ALSO

* `dsari-daemon`
* [dsari](https://github.com/rfinnie/dsari)
