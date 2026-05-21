"""SQL Server database access layer for the UI Maya project.

Single backend: SQL Server via pyodbc. Connection string from core/dbDetails.py (.env).
There is no SQLite mode — the project rule is "never UPDATE existing rows", which is
enforced by core/sp_gate.SPGate before any stored-procedure call.
"""
import pyodbc

from core.dbDetails import database_details
from core.logging_config import get_logger
from core.exceptions import DatabaseError

logger = get_logger('database')


class DatabaseManager(object):
    """Thin pyodbc wrapper. All writes go through stored procedures via call_procedure()."""

    def __init__(self):
        self._conn = None

    def connect(self):
        try:
            self._conn = pyodbc.connect(database_details)
            logger.debug("Connected to SQL Server")
        except Exception as e:
            raise DatabaseError("Failed to connect: {}".format(e))
        return self._conn

    @property
    def connection(self):
        if self._conn is None:
            self.connect()
        return self._conn

    def execute(self, query, params=None):
        """Run a parameterized query and return the cursor."""
        params = params or []
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            return cursor
        except Exception as e:
            logger.error("Query failed: %s | Params: %s | Error: %s", query[:200], params, e)
            raise DatabaseError("Query failed: {}".format(e))

    def execute_many(self, query, params_list):
        try:
            cursor = self.connection.cursor()
            cursor.executemany(query, params_list)
            return cursor
        except Exception as e:
            logger.error("Batch query failed: %s | Error: %s", query[:200], e)
            raise DatabaseError("Batch query failed: {}".format(e))

    def fetch_one(self, query, params=None):
        cursor = self.execute(query, params)
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    def fetch_all(self, query, params=None):
        cursor = self.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def fetch_df(self, query, params=None):
        import pandas as pd
        return pd.read_sql(query, self.connection, params=params)

    def call_procedure(self, proc_name, params):
        """Call a SQL Server stored procedure. Uses pyodbc {call NAME(?,?,...)} syntax.

        IMPORTANT: this writes to the database. Callers MUST gate the call with
        core.sp_gate.SPGate.call_if_absent() to enforce the no-UPDATE rule.
        """
        placeholders = ','.join(['?'] * len(params))
        query = "{{call {}({})}}".format(proc_name, placeholders)
        return self.execute(query, params)

    def commit(self):
        if self._conn:
            self._conn.commit()

    def rollback(self):
        if self._conn:
            self._conn.rollback()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.debug("Database connection closed")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False


# ============================================================
# SQL Server helpers (date functions, pagination)
# ============================================================

def today_date_sql():
    """SQL fragment for 'today's date'. Use in WHERE clauses with cast_date_sql()."""
    return "CAST(GETDATE() AS DATE)"


def cast_date_sql(column):
    """SQL fragment for CAST(column AS DATE)."""
    return "CAST({} AS DATE)".format(column)
