"""Pipeline state tracking — persisted to Pipeline_Runs table for UI visibility."""
from datetime import datetime
from core.logging_config import get_logger

logger = get_logger('pipeline.state')


class PipelineState(object):
    """Tracks pipeline run progress in the Pipeline_Runs table."""

    def __init__(self, db, run_group=None):
        self.db = db
        self.run_group = run_group or datetime.now().strftime('%Y%m%d-%H%M%S')

    def start_step(self, step_name):
        """Record that a pipeline step has started."""
        now = datetime.now().isoformat()
        self.db.execute(
            """INSERT INTO Pipeline_Runs
               (run_date, step_name, status, started_at, run_group)
               VALUES (?, ?, 'running', ?, ?)""",
            [datetime.now().strftime('%Y-%m-%d'), step_name, now, self.run_group]
        )
        self.db.commit()
        logger.info("Step '%s' started", step_name)

    def update_progress(self, step_name, processed=0, parsed=0, failed=0):
        """Update progress counts for a running step (called during processing)."""
        try:
            self.db.execute(
                """UPDATE Pipeline_Runs
                   SET companies_processed=?, companies_parsed=?, companies_failed=?
                   WHERE run_group=? AND step_name=? AND status='running'""",
                [processed, parsed, failed, self.run_group, step_name]
            )
            self.db.commit()
        except Exception:
            pass  # Don't let progress updates break the pipeline

    def complete_step(self, step_name, result=None):
        """Record that a pipeline step completed successfully.

        Counter semantics — important:
          - companies_failed counts REAL errors (SP raised, parser crashed).
          - 'No qualifying table found' is NOT a failure — it's a normal
            outcome for filings that genuinely don't have that section
            (small companies, investment funds). It used to be lumped into
            companies_failed, which made every successful run look broken.
            Those are now stored in error_message so the UI can show them
            separately if desired, but not counted as failures.
        """
        now = datetime.now().isoformat()
        result = result or {}
        # 'failed' means SP/parser exception. 'no_table_found' is normal.
        real_failed = result.get('failed', 0)
        no_table = result.get('no_table_found', 0)
        info_msg = None
        if no_table:
            info_msg = "{} compan(y/ies) had no qualifying table (normal for funds / small companies)".format(no_table)
        self.db.execute(
            """UPDATE Pipeline_Runs
               SET status='completed', completed_at=?,
                   companies_processed=?, companies_parsed=?, companies_failed=?,
                   error_message=?
               WHERE run_group=? AND step_name=? AND status='running'""",
            [now,
             result.get('companies_processed', result.get('companies_found', result.get('officers_inserted', 0))),
             result.get('parsed', result.get('companies_saved', result.get('inserted', result.get('officers_inserted', 0)))),
             real_failed,
             info_msg,
             self.run_group, step_name]
        )
        self.db.commit()
        logger.info("Step '%s' completed: %s", step_name, result)

    def fail_step(self, step_name, error_message):
        """Record that a pipeline step failed."""
        now = datetime.now().isoformat()
        self.db.execute(
            """UPDATE Pipeline_Runs
               SET status='failed', completed_at=?, error_message=?
               WHERE run_group=? AND step_name=? AND status='running'""",
            [now, str(error_message)[:500], self.run_group, step_name]
        )
        self.db.commit()
        logger.error("Step '%s' failed: %s", step_name, error_message)

    def get_run_status(self, run_group=None):
        """Get status of all steps in a run."""
        rg = run_group or self.run_group
        return self.db.fetch_all(
            """SELECT step_name, status, started_at, completed_at,
                      companies_processed, companies_parsed, companies_failed,
                      error_message
               FROM Pipeline_Runs WHERE run_group=?
               ORDER BY id""",
            [rg]
        )

    def get_recent_runs(self, limit=10):
        """Get recent pipeline runs grouped by run_group."""
        # Use SQL Server TOP syntax for compatibility (LIMIT isn't supported)
        try:
            n = int(limit)
        except Exception:
            n = 10
        sql = (
            "SELECT TOP {} run_group, run_date,"
            " COUNT(*) as total_steps,"
            " SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,"
            " SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed,"
            " SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) as running,"
            " MIN(started_at) as started,"
            " MAX(completed_at) as finished"
            " FROM Pipeline_Runs"
            " GROUP BY run_group, run_date"
            " ORDER BY MAX(id) DESC"
        ).format(n)
        return self.db.fetch_all(sql)

    def get_latest_run_group(self):
        """Get the most recent run_group."""
        # SQL Server: use TOP 1 instead of LIMIT
        row = self.db.fetch_one("SELECT TOP 1 run_group FROM Pipeline_Runs ORDER BY id DESC")
        return row['run_group'] if row else None
