# Database

dsari stores its metadata in one of a number of supported databases, currently SQLite 3 (default), PostgreSQL, MySQL or MongoDB.

## Configuration

### SQLite 3

    {
        "database": {
            "type": "sqlite3",
            "file": "/path/to/dsari.sqlite3"
        }
    }

`sqlite3` is the default database type if no database array or type is specified.
The default file is "dsari.sqlite3" in the data directory.

### PostgreSQL

    {
        "database": {
            "type": "postgresql",
            "dsn": "host=dbserver dbname=dsari"
        }
    }

`dsn` may be any valid PGSQL Data Source Name (DSN).

### MySQL

    {
        "database": {
            "type": "mysql",
            "connection": {
                "host": "dbserver",
                "user": "dbuser",
                "passwd": "dbpassword",
                "db": "dsari"
            }
        }
    }

### MongoDB

    {
        "database": {
            "type": "mongodb",
            "uri": "mongodb://localhost/dsari",
            "database": "dsari"
        }
    }

## Tables

The following is a quick reference of all defined tables.
Tables are created automatically when a database is successfully connected.

### runs

`runs` contains metadata related to all runs which have completed.

*   `job_name` (text) - The name of the job, which must match the regexp `^([- A-Za-z0-9_+.:@]+)$'`.
*   `run_id` (text, uuid) - A UUID which uniquely identifies the run.
*   `schedule_time` (real, timestamp) - The epoch time in which the run was first scheduled to be run.
    This can be significantly before the actual start time due to factors such as concurrency limits.
    For file triggers, this corresponds to the mtime of the file.
*   `start_time` (real, timestamp) - The epoch time when the run process actually begins.
*   `stop_time` (real, timestamp) - The epoch time when the run process ends.
*   `exit_code` (integer) - The exit code returned by the run process.
    dsari uses Bourne shell formatting of exit codes, where processes terminated by a signal produce an exit code of 128 + the signal number.
*   `trigger_type` (text) - The major trigger type which caused the run to be created.
    Presently, it may be "schedule" (run as a recurring schedule) or "file" (produced by a job trigger file).
*   `trigger_data` (text, json) - A JSON associative array containing trigger data.
    For "schedule" triggers, this is an empty array (`{}`).
    For "file" triggers, this is the data set in the trigger file.
    For more about trigger data, please see [Triggers](triggers.md).
    If using PostgreSQL 9.4 or later, it is recommended you change this column to `jsonb` type to take advantage of native SQL searching of this column.
*   `run_data` (text, json) - A JSON associative array containing extra run data.
    If a run writes a file called `return_data.json`, the JSON contents of this file are added as the "return_data" key.
    Additionally, this column may be utilized for third party use, and for future-proofing (additional functionality without requiring an SQL migration).
    If using PostgreSQL 9.4 or later, it is recommended you change this column to `jsonb` type to take advantage of native SQL searching of this column.

### runs_running

`runs_running` contains metadata related to runs which are currently in progress.
When a run finishes, data is inserted to `runs` and deleted from `runs_running` in a single atomic action.

For a description of each column, see `runs` above.

*   `job_name` (text)
*   `run_id` (text, uuid)
*   `schedule_time` (real, timestamp)
*   `start_time` (real, timestamp)
*   `trigger_type` (text)
*   `trigger_data` (text, json)
*   `run_data` (text, json)
