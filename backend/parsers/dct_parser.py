"""
dct_parser.py
Parses Director Compensation Tables from SEC filings and inserts
director compensation data into the database.  Ported from
DCT_parser_server.py (1117 lines).

Python 3.7 compatible.
"""

import os
import re
import traceback

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from parsers.base_parser import BaseParser
from utils.csv_manager import (
    edgar_feed_path,
    sct_parsed_path,
    load_df,
)
from utils.table_extractor import extract_table_data, extract_table_with_spans
from utils.table_scorer import score_table
from utils.data_cleaner import (
    clean_text,
    clean_numeric,
    clean_l1,
    clean_l2,
    remove_total_rows,
)
from utils.header_mapper import separate_stuck_headers, map_columns
import config


# Keywords used to score tables for director compensation content
DCT_KEYWORDS = [
    'director', 'fee', 'earned', 'paid', 'cash', 'stock', 'award',
    'option', 'compensation', 'total', 'name',
]

# Header keywords for separating stuck headers
DCT_HEADER_KEYWORDS = [
    'director', 'fee', 'earned', 'paid', 'cash', 'stock', 'award',
    'option', 'compensation', 'total', 'name', 'other', 'all',
    'non-equity', 'incentive', 'change', 'pension', 'deferred',
]

# Patterns to identify DCT tables by text content near/in the table
_DCT_TABLE_PATTERNS = [
    re.compile(r'fees?\s+earned', re.IGNORECASE),
    re.compile(r'paid\s+in\s+cash', re.IGNORECASE),
]

# ------------------------------------------------------------------
# Column-matching patterns for DCT fields
# ------------------------------------------------------------------

_FEES_EARNED_PATTERNS = [
    'fees earned or paid in cash',
    'fees earned',
    'paid in cash',
    'cash fees',
]

_STOCK_AWARDS_PATTERNS = [
    'stock awards',
    'stock award',
]

_OPTION_AWARDS_PATTERNS = [
    'option awards',
    'option award',
]

_ALL_OTHER_COMP_PATTERNS = [
    'all other compensation',
    'other compensation',
    'all other',
]

_TOTAL_PATTERNS = [
    'total',
    'total compensation',
]


def _match_column(col_name, patterns, threshold=65):
    """Check if a column name fuzzy-matches any of the given patterns."""
    from fuzzywuzzy import fuzz

    col_lower = str(col_name).lower().strip()
    for pattern in patterns:
        score = fuzz.partial_ratio(col_lower, pattern.lower())
        if score >= threshold:
            return True
    return False


def _identify_dct_columns(columns):
    """Map DataFrame columns to DCT field names.

    Parameters
    ----------
    columns : list[str]

    Returns
    -------
    dict
        Mapping of DCT field name to column name.
    """
    field_map = {}
    patterns_by_field = {
        'FeesEarnedorPaid': _FEES_EARNED_PATTERNS,
        'StockAwards': _STOCK_AWARDS_PATTERNS,
        'OptionAwards': _OPTION_AWARDS_PATTERNS,
        'AllotherComp': _ALL_OTHER_COMP_PATTERNS,
        'Total': _TOTAL_PATTERNS,
    }

    for field, patterns in patterns_by_field.items():
        for col in columns:
            if _match_column(col, patterns):
                field_map[field] = col
                break

    return field_map


def _safe_value(value):
    """Convert a cell value to numeric, returning 0 on failure."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return 0
    result = clean_numeric(value)
    if isinstance(result, float) and np.isnan(result):
        return 0
    return result


def _fetch_page_requests(url):
    """Fetch an SEC filing page using the requests library.

    The DCT parser historically uses requests (not urllib) for HTTP access,
    differing from other parsers that rely on SECFetcher/urllib.

    Parameters
    ----------
    url : str

    Returns
    -------
    BeautifulSoup or None
    """
    headers = {
        'User-Agent': (
            'MAYA/1.0 (SEC Research; compliance@example.com)'
        ),
        'Accept-Encoding': 'gzip, deflate',
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except Exception:
        return None


def _table_has_dct_pattern(table):
    """Check if a table or its immediate context contains DCT-identifying
    text patterns such as "Fees Earned" or "Paid in Cash".

    Parameters
    ----------
    table : bs4.Tag

    Returns
    -------
    bool
    """
    table_text = table.get_text(' ', strip=True)
    for pattern in _DCT_TABLE_PATTERNS:
        if pattern.search(table_text):
            return True

    # Also check the preceding sibling text (some filings put the heading
    # outside the table tag)
    prev_sib = table.find_previous_sibling()
    if prev_sib:
        prev_text = prev_sib.get_text(' ', strip=True)
        for pattern in _DCT_TABLE_PATTERNS:
            if pattern.search(prev_text):
                return True

    return False


class DCTParser(BaseParser):
    """Parse Director Compensation Tables from SEC filing HTML.

    For each company, fetches the filing page using the requests library,
    identifies the DCT table via keyword scoring and pattern matching,
    extracts and cleans the data, maps columns, and inserts records into
    ``Maya_BOD_Parsing_Summary``.
    """

    def __init__(self, db, logger_name=None):
        super(DCTParser, self).__init__(db, logger_name or 'DCTParser')

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self):
        """Execute the director compensation parsing step.

        Returns
        -------
        dict
            ``{'companies_processed': N, 'parsed': M,
               'no_table_found': K}``
        """
        result = {
            'companies_processed': 0,
            'parsed': 0,
            'no_table_found': 0,
        }

        # 1. Read edgar_feed and SCT_Parsed_transactions CSVs
        edgar_path = edgar_feed_path()
        sct_path = sct_parsed_path()

        if not os.path.exists(edgar_path):
            self.logger.warning('Edgar feed file not found: %s', edgar_path)
            return result
        if not os.path.exists(sct_path):
            self.logger.warning('SCT parsed file not found: %s', sct_path)
            return result

        edgar_df = load_df(edgar_path)
        sct_df = load_df(sct_path)
        self.logger.info(
            'Loaded edgar_feed (%d rows) and SCT_parsed (%d rows)',
            len(edgar_df), len(sct_df),
        )

        # Iterate over companies in SCT parsed transactions
        for idx, sct_row in sct_df.iterrows():
            try:
                company_id = int(sct_row.get('Company_ID', 0))
                fiscal_year = int(sct_row.get('FiscalYear', 0))
                company_name = str(sct_row.get('CompanyName', ''))

                result['companies_processed'] += 1

                # 2a. Check if BOD data already exists
                if self._dct_already_parsed(company_id, fiscal_year):
                    self.logger.info(
                        'DCT already parsed for %s (ID=%d, FY=%d), skipping',
                        company_name, company_id, fiscal_year,
                    )
                    continue

                # Get the filing link from edgar_feed
                link = self._get_filing_link(edgar_df, sct_row)
                if not link:
                    self.logger.warning(
                        'No filing link found for company %s', company_name,
                    )
                    result['no_table_found'] += 1
                    continue

                # Process the filing
                parsed = self._process_company(
                    company_id, fiscal_year, company_name, link,
                )
                if parsed:
                    result['parsed'] += 1
                else:
                    result['no_table_found'] += 1

            except Exception:
                self.logger.error(
                    'Failed processing company row %d: %s',
                    idx, traceback.format_exc(),
                )
                self._update_status_failed(sct_row)

        self.logger.info(
            'DCT parsing complete. Processed=%d, Parsed=%d, NoTable=%d',
            result['companies_processed'], result['parsed'],
            result['no_table_found'],
        )
        return result

    # ------------------------------------------------------------------
    # Pre-checks
    # ------------------------------------------------------------------

    def _dct_already_parsed(self, company_id, fiscal_year):
        """Check if director compensation data already exists in
        Maya_BOD_Parsing_Summary for this company/year.

        Returns
        -------
        bool
        """
        row = self.db.fetch_one(
            "SELECT Company_ID FROM Maya_BOD_Parsing_Summary "
            "WHERE Company_ID=? AND FiscalYear=?",
            [company_id, fiscal_year],
        )
        return row is not None

    def _get_filing_link(self, edgar_df, sct_row):
        """Extract the filing URL for this company from the edgar_feed.

        Parameters
        ----------
        edgar_df : pd.DataFrame
        sct_row : pd.Series

        Returns
        -------
        str or None
        """
        company_id = int(sct_row.get('Company_ID', 0))

        # Try matching on Company_ID
        if 'Company_ID' in edgar_df.columns:
            match = edgar_df[edgar_df['Company_ID'] == company_id]
            if not match.empty:
                for col_name in ['Link', 'link', 'Filing_Link', 'filing_link',
                                 'URL', 'url']:
                    if col_name in match.columns:
                        link = str(match.iloc[0][col_name])
                        if link and link != 'nan':
                            return link

        # Fallback: try matching on CIK
        cik = sct_row.get('CIK', None)
        if cik is not None and 'CIK' in edgar_df.columns:
            match = edgar_df[edgar_df['CIK'] == int(cik)]
            if not match.empty:
                for col_name in ['Link', 'link', 'Filing_Link', 'filing_link',
                                 'URL', 'url']:
                    if col_name in match.columns:
                        link = str(match.iloc[0][col_name])
                        if link and link != 'nan':
                            return link

        return None

    # ------------------------------------------------------------------
    # Per-company processing
    # ------------------------------------------------------------------

    def _process_company(self, company_id, fiscal_year, company_name, link):
        """Fetch filing, find DCT table, extract and insert data.

        Parameters
        ----------
        company_id : int
        fiscal_year : int
        company_name : str
        link : str

        Returns
        -------
        bool
            True if data was successfully parsed and inserted.
        """
        self.logger.info(
            'Processing DCT for %s (ID=%d, FY=%d)',
            company_name, company_id, fiscal_year,
        )

        # Fetch filing HTML using requests (different from other parsers)
        soup = _fetch_page_requests(link)
        if soup is None:
            self.logger.warning('Failed to fetch filing page: %s', link)
            return False

        # Find all tables and score them
        tables = soup.find_all('table')
        if not tables:
            self.logger.warning('No tables found in filing: %s', link)
            return False

        # Two-pass table selection:
        # 1. First, look for tables matching the "Fees Earned" / "Paid in Cash"
        #    pattern, then score among those.
        # 2. If no pattern-matched tables, fall back to scoring all tables.
        pattern_tables = [t for t in tables if _table_has_dct_pattern(t)]
        candidate_tables = pattern_tables if pattern_tables else tables

        best_table = None
        best_score = 0
        best_matched = []

        for table in candidate_tables:
            tbl_score, matched = score_table(table, DCT_KEYWORDS)
            if tbl_score > best_score:
                best_score = tbl_score
                best_table = table
                best_matched = matched

        self.logger.info(
            'Best DCT table score: %d/%d (matched: %s, pattern_filtered=%s)',
            best_score, len(DCT_KEYWORDS), best_matched,
            bool(pattern_tables),
        )

        if best_score < config.TARGET_TABLE_SCORE or best_table is None:
            self.logger.warning(
                'No qualifying DCT table found for %s (best score=%d, '
                'required=%d)',
                company_name, best_score, config.TARGET_TABLE_SCORE,
            )
            return False

        # Extract and clean table data
        raw_data = extract_table_with_spans(best_table)
        if not raw_data or len(raw_data) < 2:
            self.logger.warning(
                'Extracted DCT table has insufficient data',
            )
            return False

        df = pd.DataFrame(raw_data)
        df = self._build_dataframe(df)
        if df is None or df.empty:
            self.logger.warning(
                'Could not build valid DataFrame from DCT table',
            )
            return False

        # Clean the dataframe
        df = clean_l1(df)
        df = clean_l2(df)
        df = remove_total_rows(df)

        if df.empty:
            self.logger.warning('DCT table is empty after cleaning')
            return False

        # Separate stuck headers
        df.columns = separate_stuck_headers(df.columns, DCT_HEADER_KEYWORDS)

        # Map columns to DCT fields
        field_map = _identify_dct_columns(list(df.columns))
        self.logger.info('Identified DCT columns: %s', field_map)

        if not field_map:
            self.logger.warning(
                'Could not identify any DCT columns for %s', company_name,
            )
            return False

        # Identify the name column
        name_col = self._find_name_column(df)
        if name_col is None:
            self.logger.warning('Could not identify director name column')
            return False

        # Process each director row
        inserted_count = 0
        for _, data_row in df.iterrows():
            director_name = str(data_row.get(name_col, ''))
            if not director_name or director_name == 'nan':
                continue

            director_name = clean_text(director_name)
            if not director_name:
                continue

            # Skip rows that look like footnotes or headers
            if len(director_name) < 2:
                continue
            if re.match(r'^\(\d+\)', director_name):
                continue

            fees_earned = _safe_value(
                data_row.get(field_map.get('FeesEarnedorPaid', ''), 0),
            )
            stock_awards = _safe_value(
                data_row.get(field_map.get('StockAwards', ''), 0),
            )
            option_awards = _safe_value(
                data_row.get(field_map.get('OptionAwards', ''), 0),
            )
            all_other_comp = _safe_value(
                data_row.get(field_map.get('AllotherComp', ''), 0),
            )
            total = _safe_value(
                data_row.get(field_map.get('Total', ''), 0),
            )

            # Skip rows where all compensation values are zero
            if all(v == 0 for v in [fees_earned, stock_awards, option_awards,
                                    all_other_comp, total]):
                continue

            # sp_GenerateDirector_MAYA INSERTs into 5 BOD_* tables in a transaction.
            # Gate at (Company_ID + FiscalYear) on BOD_Director_FiscalYear — if even one
            # director has been inserted for this filing, skip the whole company.
            # See docs/SP_Behavior_Analysis.md §10.
            from core.sp_gate import SPGate, STATUS_PARSED
            if not hasattr(self, '_sp_gate'):
                self._sp_gate = SPGate(self.db, self.logger)
            try:
                status = self._sp_gate.call_if_absent(
                    exists_sql=(
                        "SELECT 1 FROM BOD_DirectorComp "
                        "WHERE Company_Id=? AND FiscalYear=? AND Name=?"
                    ),
                    exists_params=[company_id, fiscal_year, director_name],
                    sp_name="sp_GenerateDirector_MAYA",
                    sp_params=[
                        director_name,    # @Director_Name
                        'M',              # @Gender (hardcoded — matches reference)
                        company_id,       # @Company_ID
                        fiscal_year,      # @FiscalYear
                        0,                # @MasterNames_ID
                        0,                # @DirFlag
                        None,             # @AGM_Date
                        None,             # @titleDescCnt
                        None,             # @Annual_Mtg_Price
                        None,             # @Is_AGM_Disclosed
                        None,             # @SourceDocument_ID
                        fees_earned,      # @FeesEarnedorPaid
                        stock_awards,     # @StockAwards
                        option_awards,    # @OptionAwards
                        all_other_comp,   # @AllotherComp
                        total,            # @Total
                        None,             # @DirectorTag
                        None,             # @FiscalYearEnd (datetime — None unless provided)
                    ],
                    scope_label="DCT:" + str(director_name) + " FY" + str(fiscal_year),
                )
                if status == STATUS_PARSED:
                    inserted_count += 1
            except Exception:
                self.logger.error(
                    'Failed inserting DCT data for director %s: %s',
                    director_name, traceback.format_exc(),
                )

        self.logger.info(
            'Company %s: inserted %d DCT records',
            company_name, inserted_count,
        )

        # Update parsing status
        if inserted_count > 0:
            self.update_parsing_status(
                company_id, fiscal_year, 'DCT_Parsed', 'Parsed',
            )
            return True

        return False

    # ------------------------------------------------------------------
    # DataFrame construction helpers
    # ------------------------------------------------------------------

    def _build_dataframe(self, df):
        """Promote the header row(s) and clean up the raw extracted DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Raw DataFrame from table extraction (integer column names).

        Returns
        -------
        pd.DataFrame or None
        """
        if df.empty or len(df) < 2:
            return None

        # Use the first row as header; if it looks numeric, try the second row
        header_idx = 0
        first_row = df.iloc[0]
        numeric_count = sum(
            1 for v in first_row
            if re.match(r'^[\d,.$\-()]+$', str(v).strip()) and str(v).strip()
        )
        if numeric_count > len(first_row) / 2 and len(df) > 2:
            header_idx = 1

        headers = [
            clean_text(str(v)) if pd.notna(v) else 'col_{}'.format(i)
            for i, v in enumerate(df.iloc[header_idx])
        ]

        # Deduplicate headers
        seen = {}
        unique_headers = []
        for h in headers:
            if h in seen:
                seen[h] += 1
                unique_headers.append('{}_{}'.format(h, seen[h]))
            else:
                seen[h] = 0
                unique_headers.append(h)

        result = df.iloc[header_idx + 1:].copy()
        result.columns = unique_headers
        result = result.reset_index(drop=True)

        return result

    def _find_name_column(self, df):
        """Identify the column containing director names.

        Parameters
        ----------
        df : pd.DataFrame

        Returns
        -------
        str or None
        """
        from fuzzywuzzy import fuzz

        name_keywords = ['name', 'director']
        best_col = None
        best_score = 0

        for col in df.columns:
            col_lower = str(col).lower().strip()
            for kw in name_keywords:
                score = fuzz.partial_ratio(col_lower, kw)
                if score > best_score:
                    best_score = score
                    best_col = col

        if best_score >= 70:
            return best_col

        # Fallback: use the first column (common layout)
        if len(df.columns) > 0:
            return df.columns[0]

        return None

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _update_status_failed(self, sct_row):
        """Mark DCT parsing as failed for a company row."""
        try:
            company_id = int(sct_row.get('Company_ID', 0))
            fiscal_year = int(sct_row.get('FiscalYear', 0))
            if company_id and fiscal_year:
                self.update_parsing_status(
                    company_id, fiscal_year,
                    'DCT_Parsed', 'Not Parsed',
                )
        except Exception:
            self.logger.error(
                'Failed updating error status: %s', traceback.format_exc(),
            )
