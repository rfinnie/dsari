# Database

dsari stores its metadata in a SQLite 3 database.
It currently consists of a single table, `runs`.

*   `job_name` (text) - The name of the job, which must match the regexp `^([- A-Za-z0-9_+.:@]+)$'`.
*   `run_id` (text) - A UUID which uniquely identifies the run.
*   `schedule_time` (real) - The epoch time in which the run was first scheduled to be run.
    This can be significantly before the actual start time due to factors such as concurrency limits.
    For file triggers, this corresponds to the mtime of the file.
*   `start_time` (real) - The epoch time when the run process actually begins.
*   `stop_time` (real) - The epoch time when the run process ends.
*   `exit_code` (integer) - The exit code returned by the run process.
    dsari uses Bourne shell formatting of exit codes, where processes terminated by a signal produce an exit code of 128 + the signal number.
*   `trigger_type` (text) - The major trigger type which caused the run to be created.
    Presently, it may be "schedule" (run as a recurring schedule) or "file" (produced by a job trigger file).
*   `trigger_data` (text) - A JSON associative array containing trigger data.
    For "schedule" triggers, this is an empty array (`{}`).
    For "file" triggers, this is the data set in the trigger file.
    For more about trigger data, please see [Triggers](triggers.md).
*   `run_data` (text) - A JSON associative array containing extra run data.
    Presently, the dsari scheduler inserts an empty array (`{}`) and otherwise does not use this field.
    It is included for third party use, and for future-proofing (additional functionality without requiring an SQL migration).
