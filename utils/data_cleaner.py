"""Data cleaning utilities for parsed compensation tables.

Consolidates the L1 / L2 / L3 cleaning stages and helper functions that
were duplicated across the SCT, Equity, Exercise, PBA, and DCT modules.
"""
import re

import numpy as np
import pandas as pd

from core.logging_config import get_logger

logger = get_logger('data_cleaner')

# Characters / substrings to strip during text cleaning
SPECIAL_CHARS = [
    '\u200b',   # zero-width space
    '\u00a0',   # non-breaking space
    '\xa0',     # non-breaking space (alias)
    '\u2014',   # em dash
    '\u2013',   # en dash
    '\u2212',   # minus sign
    '\u2020',   # dagger
    '\u2021',   # double dagger
    '*',
    '(1)', '(2)', '(3)', '(4)', '(5)',
    '(a)', '(b)', '(c)', '(d)',
]

# Pattern that detects index-style markers such as (a), (1), (i), (ii)
_INDEX_PATTERN = re.compile(
    r'^\s*\(?[a-z0-9]{1,4}\)?\s*$', re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Text-level helpers
# ---------------------------------------------------------------------------


def clean_text(text):
    """Remove special unicode characters and normalise whitespace.

    Parameters
    ----------
    text : str
        Raw cell text.

    Returns
    -------
    str
        Cleaned text with special characters removed and whitespace collapsed.
    """
    if not isinstance(text, str):
        return text
    for ch in SPECIAL_CHARS:
        text = text.replace(ch, '')
    # Collapse multiple whitespace into a single space
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def clean_numeric(value):
    """Convert a string compensation value to a numeric type.

    Handles:
    * Dollar signs and commas  (``$1,234,567``)
    * Parentheses for negatives (``(1,234)``)
    * Bare dashes representing zero (``-``, ``--``)
    * Already-numeric inputs (returned unchanged)

    Parameters
    ----------
    value : str or numeric
        The raw value from a table cell.

    Returns
    -------
    float or np.nan
        The numeric equivalent, or ``np.nan`` if conversion fails.
    """
    if isinstance(value, (int, float)):
        return value

    if not isinstance(value, str):
        return np.nan

    text = value.strip()

    # Dash(es) alone mean zero
    if re.match(r'^[-\u2013\u2014\u2212]+$', text):
        return 0.0

    # Empty / whitespace-only
    if text == '':
        return np.nan

    # Detect negative from parentheses: (1,234)
    negative = False
    if text.startswith('(') and text.endswith(')'):
        negative = True
        text = text[1:-1]

    # Remove dollar sign, commas, spaces
    text = text.replace('$', '').replace(',', '').replace(' ', '')

    # Remove percent sign (some tables include it)
    text = text.replace('%', '')

    try:
        result = float(text)
        return -result if negative else result
    except ValueError:
        return np.nan


# ---------------------------------------------------------------------------
# DataFrame-level cleaning stages
# ---------------------------------------------------------------------------


def clean_l1(df):
    """L1 cleaning: remove empty / NaN rows and replace special characters.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
    """
    df = df.copy()

    # Apply text cleaning to every cell
    df = df.map(lambda x: clean_text(x) if isinstance(x, str) else x)

    # Replace empty strings with NaN, then drop fully-empty rows
    df = df.replace('', np.nan)
    df = df.dropna(how='all').reset_index(drop=True)

    logger.debug('L1 cleaning complete. Shape: %s', df.shape)
    return df


def clean_l2(df):
    """L2 cleaning: remove blank and duplicate columns.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
    """
    df = df.copy()

    # Drop columns that are entirely NaN or empty string
    df = df.replace('', np.nan)
    df = df.dropna(axis=1, how='all')

    # Remove duplicate columns (same header AND same values)
    df = df.loc[:, ~df.T.duplicated()]

    logger.debug('L2 cleaning complete. Shape: %s', df.shape)
    return df


def clean_l3(df, fiscal_year=None):
    """L3 cleaning: keep only the latest fiscal year records.

    If *fiscal_year* is provided, rows matching that year are kept.
    Otherwise the function looks for a column whose header contains
    ``year`` (case-insensitive) and keeps rows matching the maximum
    year value found.

    Parameters
    ----------
    df : pd.DataFrame
    fiscal_year : int or str, optional

    Returns
    -------
    pd.DataFrame
    """
    df = df.copy()

    # Try to find a year column
    year_col = None
    for col in df.columns:
        if 'year' in str(col).lower():
            year_col = col
            break

    if year_col is None:
        logger.debug('L3: No year column found; returning dataframe as-is.')
        return df

    # Coerce to numeric so we can compare years
    years = pd.to_numeric(df[year_col], errors='coerce')

    if fiscal_year is not None:
        target = float(fiscal_year)
    else:
        target = years.max()

    if pd.isna(target):
        logger.debug('L3: Could not determine target year; returning as-is.')
        return df

    mask = years == target
    df = df.loc[mask].reset_index(drop=True)

    logger.debug('L3 cleaning complete (year=%s). Shape: %s', int(target), df.shape)
    return df


# ---------------------------------------------------------------------------
# Row-removal helpers
# ---------------------------------------------------------------------------


def remove_index_rows(df):
    """Remove rows that look like index markers: (a), (b), (1), (2) etc.

    Checks only the first column of the dataframe.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
    """
    if df.empty:
        return df

    df = df.copy()
    first_col = df.iloc[:, 0].astype(str)
    mask = first_col.apply(lambda x: bool(_INDEX_PATTERN.match(x)))
    removed = mask.sum()
    df = df.loc[~mask].reset_index(drop=True)

    if removed:
        logger.debug('Removed %d index-marker rows.', removed)
    return df


def remove_total_rows(df):
    """Remove rows containing 'total' in the first column (sum / subtotal rows).

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
    """
    if df.empty:
        return df

    df = df.copy()
    first_col = df.iloc[:, 0].astype(str).str.lower()
    mask = first_col.str.contains('total', na=False)
    removed = mask.sum()
    df = df.loc[~mask].reset_index(drop=True)

    if removed:
        logger.debug('Removed %d total/subtotal rows.', removed)
    return df
