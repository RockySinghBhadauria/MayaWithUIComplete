"""Schema management for the UI Maya project.

The production tables (Company, Officer, wk_SummaryComp, Officer_Outstanding_Equity,
Officer_Awards, Director, BOD_*) ALREADY EXIST on the SQL Server and are managed by
the DBA team. This module only creates the UI-specific Pipeline_Runs table.

We deliberately do NOT define DDL for production tables — that would let a typo here
diverge from the real schema. If you need column lists for queries, see
docs/SP_Behavior_Analysis.md.
"""
from core.logging_config import get_logger

logger = get_logger('schema')


PIPELINE_RUNS_DDL = """
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Pipeline_Runs')
BEGIN
    CREATE TABLE Pipeline_Runs (
        id INT IDENTITY(1,1) PRIMARY KEY,
        run_date NVARCHAR(50) NOT NULL,
        step_name NVARCHAR(50) NOT NULL,
        status NVARCHAR(20) DEFAULT 'pending',
        started_at NVARCHAR(50),
        completed_at NVARCHAR(50),
        companies_processed INT DEFAULT 0,
        companies_parsed INT DEFAULT 0,
        companies_failed INT DEFAULT 0,
        error_message NVARCHAR(MAX),
        run_group NVARCHAR(100)
    )
END
"""


def init_database(db):
    """Create UI-specific tables. Idempotent. Production tables are server-managed."""
    db.execute(PIPELINE_RUNS_DDL)
    db.commit()
    logger.info("Pipeline_Runs table ensured")
