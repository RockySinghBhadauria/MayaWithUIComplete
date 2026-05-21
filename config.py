"""Central configuration for the MAYA Enhanced Project (UI fork).

Database is SQL Server only. Connection details come from .env via core/dbDetails.py
(same pattern as the production Maya project).
"""
import os

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

# Filesystem
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
METADATA_DUMP_DIR = os.path.join(DATA_DIR, 'metadata_dump')
FILING_DUMP_DIR = os.path.join(DATA_DIR, 'filing_dump')

# Logging
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
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

# Pipeline step names (execution order is defined in pipeline/runner.py)
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
