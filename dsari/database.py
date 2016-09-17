#!/usr/bin/env python

# dsari - Do Something and Record It
# Copyright (C) 2015-2016 Ryan Finnie
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

import sqlite3
import json
import os

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

import dsari
from dsari.utils import epoch_to_dt, dt_to_epoch


def get_database(config):
    if HAS_PSYCOPG2 and (config.database['type'] == 'postgresql'):
        return PostgreSQLDatabase(config)
    else:
        if 'file' not in config.database:
            config.database['file'] = None
        if config.database['file'] is None:
            config.database['file'] = os.path.join(config.data_dir, 'dsari.sqlite3')
        return SQLite3Database(config)


class BaseDatabase():
    placeholder = '%s'

    def __init__(self, config):
        self.config = config
        self.populate_schema()

    def populate_schema(self):
        pass

    def modify_statement(self, sql):
        return sql.format(*((self.placeholder,) * sql.count('{}')))

    def build_insert(self, pairs):
        out = []
        for (k, v) in pairs:
            if k in (
                'trigger_data',
                'run_data',
            ):
                out.append(json.dumps(v))
            else:
                out.append(v)
        return out

    def build_run_from_result(self, job, f):
        run = dsari.Run(job, id=f['run_id'])
        for k in ('schedule_time', 'start_time', 'stop_time'):
            if k not in f:
                continue
            if type(f[k]) in (int, float):
                run.schedule_time = epoch_to_dt(f[k])
            else:
                run.schedule_time = f[k]
        if 'exit_code' in f:
            run.exit_code = f['exit_code']
        run.trigger_type = f['trigger_type']
        for k in ('trigger_data', 'run_data'):
            if type(f[k]) == dict:
                run.trigger_data = f[k]
            else:
                run.trigger_data = json.loads(f[k])

    def get_previous_runs(self, job):
        sql_statement = """
            SELECT
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code,
                trigger_type,
                trigger_data,
                run_data
            FROM
                runs
            WHERE
                job_name = {}
            ORDER BY
                stop_time DESC
        """
        sql_statement = self.modify_statement(sql_statement)
        cur = self.db_conn.cursor()
        cur.execute(sql_statement, (job.name,))
        f = cur.fetchone()
        cur.close()
        if f:
            previous_run = self.build_run_from_result(job, f)
        else:
            previous_run = None

        sql_statement = """
            SELECT
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code,
                trigger_type,
                trigger_data,
                run_data
            FROM
                runs
            WHERE
                job_name = {}
            AND
                exit_code = 0
            ORDER BY
                stop_time DESC
        """
        sql_statement = self.modify_statement(sql_statement)
        cur = self.db_conn.cursor()
        cur.execute(sql_statement, (job.name,))
        f = cur.fetchone()
        cur.close()
        if f:
            previous_good_run = self.build_run_from_result(job, f)
        else:
            previous_good_run = None

        sql_statement = """
            SELECT
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code,
                trigger_type,
                trigger_data,
                run_data
            FROM
                runs
            WHERE
                job_name = {}
            AND
                exit_code != 0
            ORDER BY
                stop_time DESC
        """
        sql_statement = self.modify_statement(sql_statement)
        cur = self.db_conn.cursor()
        cur.execute(sql_statement, (job.name,))
        f = cur.fetchone()
        cur.close()
        if f:
            previous_bad_run = self.build_run_from_result(job, f)
        else:
            previous_bad_run = None

        return (previous_run, previous_good_run, previous_bad_run)

    def insert_running_run(self, run):
        sql_statement = """
            INSERT INTO runs_running (
                job_name,
                run_id,
                schedule_time,
                start_time,
                trigger_type,
                trigger_data,
                run_data
            ) VALUES (
                {}, {}, {}, {}, {}, {}, {}
            )
        """
        sql_statement = self.modify_statement(sql_statement)
        cur = self.db_conn.cursor()
        cur.execute(sql_statement, self.build_insert([
            ('job_name', run.job.name),
            ('run_id', run.id),
            ('schedule_time', run.schedule_time),
            ('start_time', run.start_time),
            ('trigger_type', run.trigger_type),
            ('trigger_data', run.trigger_data),
            ('run_data', {}),
        ]))
        self.db_conn.commit()

    def insert_run(self, run):
        cur = self.db_conn.cursor()
        sql_statement = """
            INSERT INTO runs (
                job_name,
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code,
                trigger_type,
                trigger_data,
                run_data
            ) VALUES (
                {}, {}, {}, {}, {}, {}, {}, {}, {}
            )
        """
        sql_statement = self.modify_statement(sql_statement)
        cur.execute(sql_statement, self.build_insert([
            ('job_name', run.job.name),
            ('run_id', run.id),
            ('schedule_time', run.schedule_time),
            ('start_time', run.start_time),
            ('stop_time', run.stop_time),
            ('exit_code', run.exit_code),
            ('trigger_type', run.trigger_type),
            ('trigger_data', run.trigger_data),
            ('run_data', {}),
        ]))

        sql_statement = """
            DELETE
            FROM
                runs_running
            WHERE
                run_id = {}
        """
        sql_statement = self.modify_statement(sql_statement)
        cur.execute(sql_statement, (
            run.id,
        ))
        self.db_conn.commit()

    def clear_runs_running(self):
        sql_statement = """
            DELETE
            FROM
                runs_running
        """
        sql_statement = self.modify_statement(sql_statement)
        cur = self.db_conn.cursor()
        cur.execute(sql_statement)
        self.db_conn.commit()

    def child_close_fd(self):
        pass

    def get_runs(self, jobs=None, runs=None):
        if runs is not None:
            where = 'run_id'
            where_in = runs
        elif jobs is not None:
            where = 'job_name'
            where_in = jobs
        else:
            where = None
            where_in = []

        sql_statement = """
            SELECT
                job_name,
                run_id,
                schedule_time,
                start_time,
                stop_time,
                exit_code,
                trigger_type,
                trigger_data,
                run_data
            FROM
                runs
        """
        if where is not None:
            sql_statement += """
                WHERE
                    {} in ({})
            """.format(
                where,
                ','.join(['{}'] * len(where_in)),
            )
        sql_statement = self.modify_statement(sql_statement)
        cur = self.db_conn.cursor()
        cur.execute(sql_statement, where_in)
        runs = []
        # Fake up a stub job object if the job has disappeared from
        # the config.
        fake_jobs = {}
        for db_result in cur:
            if db_result['job_name'] in self.config.jobs:
                job = self.config.jobs[db_result['job_name']]
            elif db_result['job_name'] in fake_jobs:
                job = fake_jobs[db_result['job_name']]
            else:
                job = dsari.Job(db_result['job_name'])
                fake_jobs[db_result['job_name']] = job
            runs.append(self.build_run_from_result(job, db_result))
        cur.close()
        return runs


class PostgreSQLDatabase(BaseDatabase):
    def __init__(self, config):
        self.config = config
        self.db_conn = psycopg2.connect(config.database['dsn'])
        self.db_conn.cursor_factory = psycopg2.extras.DictCursor
        self.populate_schema()

    def populate_schema(self):
        sql_statement = """
            SELECT
                table_name
            FROM
                information_schema.tables
            WHERE
                table_name = 'runs'
        """
        cur = self.db_conn.cursor()
        cur.execute(sql_statement)
        runs_exists = cur.fetchone()
        cur.close()

        if not runs_exists:
            sql_statement = """
                CREATE TABLE runs (
                    job_name text,
                    run_id uuid,
                    schedule_time timestamp,
                    start_time timestamp,
                    stop_time timestamp,
                    exit_code integer,
                    trigger_type text,
                    trigger_data json,
                    run_data json
                )
            """
            cur = self.db_conn.cursor()
            cur.execute(sql_statement)
            cur.close()
            self.db_conn.commit()

        sql_statement = """
            SELECT
                table_name
            FROM
                information_schema.tables
            WHERE
                table_name = 'runs_running'
        """
        cur = self.db_conn.cursor()
        cur.execute(sql_statement)
        runs_running_exists = cur.fetchone()
        cur.close()

        if not runs_running_exists:
            sql_statement = """
                CREATE TABLE runs_running (
                    job_name text,
                    run_id uuid,
                    schedule_time timestamp,
                    start_time timestamp,
                    trigger_type text,
                    trigger_data text,
                    run_data json
                )
            """
            cur = self.db_conn.cursor()
            cur.execute(sql_statement)
            cur.close()
            self.db_conn.commit()


class SQLite3Database(BaseDatabase):
    placeholder = '?'

    def __init__(self, config):
        self.config = config
        print repr(config.database)
        self.db_conn = sqlite3.connect(config.database['file'])
        self.db_conn.row_factory = sqlite3.Row
        self.populate_schema()

    def populate_schema(self):
        sql_statement = """
            SELECT
                name
            FROM
                sqlite_master
            WHERE
                type = 'table'
            AND
                name = 'runs'
        """
        cur = self.db_conn.cursor()
        cur.execute(sql_statement)
        runs_exists = cur.fetchone()
        cur.close()

        if not runs_exists:
            sql_statement = """
                CREATE TABLE runs (
                    job_name text,
                    run_id text,
                    schedule_time real,
                    start_time real,
                    stop_time real,
                    exit_code integer,
                    trigger_type text,
                    trigger_data text,
                    run_data text
                )
            """
            cur = self.db_conn.cursor()
            cur.execute(sql_statement)
            cur.close()
            self.db_conn.commit()

        sql_statement = """
            SELECT
                name
            FROM
                sqlite_master
            WHERE
                type = 'table'
            AND
                name = 'runs_running'
        """
        cur = self.db_conn.cursor()
        cur.execute(sql_statement)
        runs_running_exists = cur.fetchone()
        cur.close()

        if not runs_running_exists:
            sql_statement = """
                CREATE TABLE runs_running (
                    job_name text,
                    run_id text,
                    schedule_time real,
                    start_time real,
                    trigger_type text,
                    trigger_data text,
                    run_data text
                )
            """
            cur = self.db_conn.cursor()
            cur.execute(sql_statement)
            cur.close()
            self.db_conn.commit()

    def child_close_fd(self):
        self.db_conn.close()

    def build_insert(self, pairs):
        out = []
        for (k, v) in pairs:
            if k in (
                'schedule_time',
                'start_time',
                'stop_time',
            ):
                out.append(dt_to_epoch(v))
            elif k in (
                'trigger_data',
                'run_data',
            ):
                out.append(json.dumps(v))
            else:
                out.append(v)
        return out