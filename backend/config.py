"""Central configuration for the MAYA Enhanced Project (UI fork, backend).

Database is SQL Server only. Connection details come from .env via core/dbDetails.py
(same pattern as the production Maya project).

Layout mirrors production Maya: all per-year artifacts live under logs/<year>/.
"""
import os
from datetime import date

# Project root is the backend/ folder (this file's directory)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# SEC EDGAR
SEC_USER_AGENT = 'MainDataGroup support@maindatagroup.com'
SEC_REQUEST_DELAY = 1
SEC_BASE_URL = 'https://www.sec.gov/cgi-bin/browse-edgar'
SEC_RSS_PARAMS = {
    'action': 'getcurrent',
    'type': 'def 14A',
    'company': '',
    'dateb': '',
    'owner': 'include',
    'count': 100,
    'output': 'atom',
}
SEC_RSS_PAGES = 3

# ============================================================
# Filesystem — production-style logs/<year>/{filing_dump, sct_metadata_dump, runs}
# ============================================================

LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')  # logs/
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')  # one-off seed CSVs only (mssql_company_export, etc.)


def _year_dir(year=None):
    year = year or str(date.today().year)
    path = os.path.join(LOG_DIR, year)
    return path


def metadata_dump_dir(year=None):
    """logs/<year>/sct_metadata_dump/ — daily edgar_feed + per-module *_Parsed_transactions CSVs."""
    return os.path.join(_year_dir(year), 'sct_metadata_dump')


def filing_dump_dir(year=None):
    """logs/<year>/filing_dump/ — per-company L1/L2/L3 CSVs grouped by module/month/day."""
    return os.path.join(_year_dir(year), 'filing_dump')


def runs_dir(year=None):
    """logs/<year>/runs/ — flat-file log of each maya_YYYYMMDD.log."""
    return os.path.join(_year_dir(year), 'runs')


# Back-compat aliases (csv_manager.py uses these names)
METADATA_DUMP_DIR = metadata_dump_dir()
FILING_DUMP_DIR = filing_dump_dir()

LOG_LEVEL = os.environ.get('MAYA_LOG_LEVEL', 'INFO')

# Parsing thresholds
FUZZY_TABLE_THRESHOLD = 80
FUZZY_OFFICER_THRESHOLD = 55
TARGET_TABLE_SCORE = 5
MIN_TABLE_ROWS = 5

# SMTP
SMTP_SERVER = 'smtp.office365.com'
SMTP_PORT = 587
SMTP_SENDER = 'sqlmail@maindatagroup.com'
SMTP_PASSWORD = os.environ.get('MAYA_SMTP_PASSWORD', '')
SMTP_TO = os.environ.get('MAYA_SMTP_TO', '')
SMTP_CC = os.environ.get('MAYA_SMTP_CC', '')

# Pipeline step names (execution order is in pipeline/runner.py)
PIPELINE_STEPS = [
    'rss_feed',
    'sct_parse',
    'data_entry',
    'sql_parse',
    'equity_parse',
    'exercise_parse',
    'pba_parse',
    'dct_parse',
    'send_mail',
]
