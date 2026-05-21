"""
Centralized CSV path construction and I/O utilities.

Replaces the scattered path-building pattern found throughout the codebase,
e.g.::

    '../SCT_metadata_dump/' + str(today_month) + '/edgar_feed_live_' + str(date.today()) + '.csv'

All path helpers create intermediate directories automatically.
"""

import os
from datetime import date, datetime

import pandas as pd

import config


def get_metadata_dir(month=None, year=None):
    """Get metadata dump directory: ``logs/<year>/sct_metadata_dump/<month>/`` (production layout).

    Args:
        month: Month number as string. Defaults to current month.
        year:  Year string. Defaults to current year.

    Returns:
        Absolute path to the metadata directory (created if absent).
    """
    today = date.today()
    month = month or str(today.month)
    year = year or str(today.year)
    path = os.path.join(config.metadata_dump_dir(year), month)
    os.makedirs(path, exist_ok=True)
    return path


def get_filing_dir(module_name, year=None, month=None, day=None):
    """Get filing dump directory: ``logs/<year>/filing_dump/<module>/<month>/<day>/`` (production layout).

    Args:
        module_name: Parser module identifier (e.g. ``'SCT_filings_dump'``, ``'Equity_filings_dump'``).
        year: Year string. Defaults to current year.
        month: Month string. Defaults to current month.
        day: Day string. Defaults to current day.

    Returns:
        Absolute path to the filing directory (created if absent).
    """
    today = date.today()
    year = year or str(today.year)
    month = month or str(today.month)
    day = day or str(today.day)
    path = os.path.join(config.filing_dump_dir(year), module_name, month, day)
    os.makedirs(path, exist_ok=True)
    return path


def edgar_feed_path(today_date=None):
    """Path for the ``edgar_feed_live`` CSV.

    Args:
        today_date: A :class:`datetime.date`. Defaults to today.

    Returns:
        Full file path string.
    """
    today_date = today_date or date.today()
    return os.path.join(
        get_metadata_dir(),
        'edgar_feed_live_{}.csv'.format(today_date),
    )


def sct_parsed_path(today_date=None):
    """Path for the ``SCT_Parsed_transactions_live`` CSV.

    Args:
        today_date: A :class:`datetime.date`. Defaults to today.

    Returns:
        Full file path string.
    """
    today_date = today_date or date.today()
    return os.path.join(
        get_metadata_dir(),
        'SCT_Parsed_transactions_live_{}.csv'.format(today_date),
    )


def out_of_bound_path(today_date=None):
    """Path for the ``outOfBound_companies`` CSV.

    Args:
        today_date: A :class:`datetime.date`. Defaults to today.

    Returns:
        Full file path string.
    """
    today_date = today_date or date.today()
    return os.path.join(
        get_metadata_dir(),
        'outOfBound_companies_live_{}.csv'.format(today_date),
    )


def module_parsed_path(module_prefix, today_date=None):
    """Generic path for a module's parsed-transactions CSV.

    Args:
        module_prefix: Module name prefix (e.g. ``'Equity'``, ``'PBA'``).
        today_date: A :class:`datetime.date`. Defaults to today.

    Returns:
        Full file path string.
    """
    today_date = today_date or date.today()
    return os.path.join(
        get_metadata_dir(),
        '{}_Parsed_transactions_live_{}.csv'.format(module_prefix, today_date),
    )


def backup_if_exists(filepath):
    """If *filepath* exists, rename it with a timestamp to prevent overwrite.

    Also ensures the parent directory exists for the caller's upcoming write
    (saves callers from having to add os.makedirs themselves).

    Args:
        filepath: Path to check.

    Returns:
        The new backup path if a rename occurred, otherwise None.
    """
    parent = os.path.dirname(filepath)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(filepath):
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        base, ext = os.path.splitext(filepath)
        new_name = '{}_{}{}'.format(base, ts, ext)
        os.rename(filepath, new_name)
        return new_name
    return None


def save_df(df, filepath, index=False):
    """Save a DataFrame to CSV, creating parent directories as needed.

    Args:
        df: pandas DataFrame.
        filepath: Destination CSV path.
        index: Whether to write the row index. Defaults to False.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df.to_csv(filepath, index=index)


def load_df(filepath):
    """Load a CSV file into a pandas DataFrame.

    Args:
        filepath: Source CSV path.

    Returns:
        pandas DataFrame.
    """
    return pd.read_csv(filepath)
