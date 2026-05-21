"""
exercise_parser.py
Parses Option Exercises & Stock Vested tables from SEC filings and updates
officer exercise/vesting data in the database.  Ported from
exer_parser_server_v1.py (968 lines).

Python 3.7 compatible.
"""

import os
import re
import traceback

import numpy as np
import pandas as pd

from parsers.base_parser import BaseParser
from utils.csv_manager import (
    edgar_feed_path,
    sct_parsed_path,
    load_df,
)
from utils.html_fetcher import SECFetcher
from utils.table_extractor import extract_table_data, extract_table_with_spans
from utils.table_scorer import score_table
from utils.data_cleaner import (
    clean_text,
    clean_numeric,
    clean_l1,
    clean_l2,
    remove_total_rows,
)
from utils.officer_matcher import (
    match_officer,
    get_officer_id,
    get_company_officers,
)
from utils.header_mapper import separate_stuck_headers, map_columns
import config


# Keywords used to score tables for exercise & vested content
EXERCISE_KEYWORDS = [
    'option', 'exercise', 'stock', 'vested', 'shares', 'acquired',
    'value', 'realized', 'aggregate', 'number',
]

# Header keywords for separating stuck headers
EXERCISE_HEADER_KEYWORDS = [
    'option', 'exercise', 'stock', 'vested', 'shares', 'acquired',
    'value', 'realized', 'aggregate', 'number', 'name', 'award',
    'upon', 'vesting', 'officer',
]

# Column-matching patterns for exercise/vested fields
_OPTION_SHARES_PATTERNS = [
    'option awards number of shares acquired on exercise',
    'number of shares acquired on exercise',
    'shares acquired on exercise',
    'option shares acquired',
]

_OPTION_VALUE_PATTERNS = [
    'option awards value realized on exercise',
    'value realized on exercise',
    'option value realized',
]

_STOCK_SHARES_PATTERNS = [
    'stock awards number of shares acquired on vesting',
    'number of shares acquired on vesting',
    'shares acquired on vesting',
    'stock shares acquired',
]

_STOCK_VALUE_PATTERNS = [
    'stock awards value realized on vesting',
    'value realized on vesting',
    'stock value realized',
]


def _match_column(col_name, patterns, threshold=65):
    """Check if a column name fuzzy-matches any of the given patterns.

    Parameters
    ----------
    col_name : str
    patterns : list[str]
    threshold : int

    Returns
    -------
    bool
    """
    from fuzzywuzzy import fuzz

    col_lower = str(col_name).lower().strip()
    for pattern in patterns:
        score = fuzz.partial_ratio(col_lower, pattern.lower())
        if score >= threshold:
            return True
    return False


def _identify_exercise_columns(columns):
    """Map DataFrame columns to exercise/vested field names.

    Parameters
    ----------
    columns : list[str]

    Returns
    -------
    dict
        Mapping of field name to column name.  Possible keys:
        ``Option_Shares_Acquired``, ``Option_Value_Realized``,
        ``Stock_Shares_Acquired``, ``Stock_Value_Realized``.
    """
    field_map = {}
    patterns_by_field = {
        'Option_Shares_Acquired': _OPTION_SHARES_PATTERNS,
        'Option_Value_Realized': _OPTION_VALUE_PATTERNS,
        'Stock_Shares_Acquired': _STOCK_SHARES_PATTERNS,
        'Stock_Value_Realized': _STOCK_VALUE_PATTERNS,
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


class ExerciseParser(BaseParser):
    """Parse Option Exercises & Stock Vested tables from SEC filing HTML.

    For each company, fetches the filing page, identifies the exercise/vested
    table via keyword scoring, extracts and cleans the data, maps columns,
    matches officers, and updates records via
    ``sp_ExerciseandVested_U_MAYA``.
    """

    def __init__(self, db, logger_name=None):
        super(ExerciseParser, self).__init__(db, logger_name or 'ExerciseParser')
        self.fetcher = SECFetcher()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self):
        """Execute the exercise/vested parsing step.

        Returns
        -------
        dict
            ``{'companies_processed': N, 'parsed': M, 'skipped': K,
               'no_table_found': L}``
        """
        result = {
            'companies_processed': 0,
            'parsed': 0,
            'skipped': 0,
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
                company_name = str(sct_row.get('CompanyName', '')).strip()
                fiscal_year = int(float(sct_row.get('FiscalYear', 0) or 0))
                comp_row = self.db.fetch_one(
                    "SELECT Company_ID FROM Company WHERE CompanyName=?", [company_name])
                if not comp_row:
                    comp_row = self.db.fetch_one(
                        "SELECT Company_ID FROM Company WHERE CompanyName LIKE ?",
                        ['%' + company_name.split()[0] + '%'])
                company_id = comp_row['Company_ID'] if comp_row else 0

                result['companies_processed'] += 1
                self.report_progress(processed=result['companies_processed'], parsed=result.get('parsed', 0), failed=result.get('no_table_found', 0))

                # 2a. Check if exercise data already exists
                if self._exercise_already_parsed(company_id, fiscal_year):
                    self.logger.info(
                        'Exercise data already parsed for %s (ID=%d, FY=%d), '
                        'skipping',
                        company_name, company_id, fiscal_year,
                    )
                    result['skipped'] += 1
                    continue

                # Get the filing link
                link = str(sct_row.get('Link', '')).strip()
                if link:
                    link = link.replace('/ix?doc=/', '/').replace('/cgi-bin/browse-edgar/', '/')
                if not link or link == 'nan':
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
            'Exercise parsing complete. Processed=%d, Parsed=%d, '
            'Skipped=%d, NoTable=%d',
            result['companies_processed'], result['parsed'],
            result['skipped'], result['no_table_found'],
        )
        return result

    # ------------------------------------------------------------------
    # Pre-checks
    # ------------------------------------------------------------------

    def _exercise_already_parsed(self, company_id, fiscal_year):
        """Check if exercise/vested data already exists for this company/year.

        Looks at the four exercise/vested fields on the Officer table.
        If all four are non-null and non-zero the data is considered present.

        Returns
        -------
        bool
        """
        row = self.db.fetch_one(
            "SELECT Option_Shares_Acquired, Option_Value_Realized, "
            "Stock_Shares_Acquired, Stock_Value_Realized "
            "FROM Officer WHERE Company_ID=? AND FiscalYear=?",
            [company_id, fiscal_year],
        )
        if row is None:
            return False

        # All four fields must be non-null and non-zero to be considered parsed
        fields = [
            row.get('Option_Shares_Acquired'),
            row.get('Option_Value_Realized'),
            row.get('Stock_Shares_Acquired'),
            row.get('Stock_Value_Realized'),
        ]
        for val in fields:
            if val is None or val == 0 or val == '':
                return False
        return True

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
        """Fetch filing, find exercise/vested table, extract and insert data.

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
            'Processing exercise/vested for %s (ID=%d, FY=%d)',
            company_name, company_id, fiscal_year,
        )

        # Fetch filing HTML
        soup = self.fetcher.fetch_page(link)
        if soup is None:
            self.logger.warning('Failed to fetch filing page: %s', link)
            return False

        from utils.table_scorer import classify_table

        # === Find EXERCISE table using classification ===
        best_table = None
        best_score = 0

        tables = soup.find_all('table')
        for table in tables:
            if len(table.find_all('tr')) < 3:
                continue
            table_type = classify_table(table)
            if table_type == 'EXERCISE':
                best_table = table
                best_score = 15
                self.logger.info('Exercise: Found via classify_table (EXERCISE)')
                break

        # Fallback: text search
        if best_table is None:
            import re as _re
            exercise_texts = soup(text=_re.compile("ption.*xercise|tock.*ested|ggregate.*ption", _re.I))
            for text_match in exercise_texts:
                try:
                    table = text_match.parent.find_next('table')
                    if table and len(table.find_all('tr')) >= 3:
                        if classify_table(table) not in ('SCT', 'EQUITY'):
                            best_table = table
                            best_score = 12
                            self.logger.info('Exercise: Found via text search (skipped SCT/EQUITY)')
                            break
                except Exception:
                    continue

        self.logger.info(
            'Best exercise table score: %d (type: %s)',
            best_score, classify_table(best_table) if best_table else 'NONE',
        )

        if best_score < 5 or best_table is None:
            self.logger.warning(
                'No qualifying exercise table found for %s (best score=%d, '
                'required=%d)',
                company_name, best_score, config.TARGET_TABLE_SCORE,
            )
            return False

        # Extract and clean table data
        raw_data = extract_table_with_spans(best_table)
        if not raw_data or len(raw_data) < 2:
            self.logger.warning(
                'Extracted exercise table has insufficient data',
            )
            return False

        df = pd.DataFrame(raw_data)

        # Use multi-row header merger for SEC multi-row headers
        from utils.multirow_header import merge_multirow_headers, find_column_by_keywords
        df, merged_headers = merge_multirow_headers(df)
        self.logger.debug('Merged headers: %s', merged_headers[:6])

        if df.empty:
            self.logger.warning('Exercise table is empty after header merge')
            return False

        # Map columns using keyword matching on merged headers
        field_map = find_column_by_keywords(list(df.columns), {
            'Option_Shares_Acquired': ['option', 'shares', 'acquired', 'number', 'exercised'],
            'Option_Value_Realized': ['option', 'value', 'realized'],
            'Stock_Shares_Acquired': ['stock', 'shares', 'acquired', 'vested', 'number'],
            'Stock_Value_Realized': ['stock', 'value', 'realized', 'vested'],
        })

        # Fallback: try position-based mapping for 4-column exercise tables
        data_cols = [c for c in df.columns if 'name' not in str(c).lower() and 'col_' not in str(c)]
        if not field_map and len(data_cols) >= 4:
            field_map = {
                'Option_Shares_Acquired': data_cols[0],
                'Option_Value_Realized': data_cols[1],
                'Stock_Shares_Acquired': data_cols[2],
                'Stock_Value_Realized': data_cols[3],
            }

        self.logger.info('Identified exercise columns: %s', field_map)

        if not field_map:
            self.logger.warning(
                'Could not identify any exercise/vested columns for %s',
                company_name,
            )
            return False

        # Get officer list for matching (empty is OK — auto-create will handle)
        officers = get_company_officers(self.db, company_id, fiscal_year)
        if not officers:
            self.logger.debug('No existing officers for %s — will auto-create', company_name)

        # Identify the name column
        name_col = self._find_name_column(df)
        if name_col is None:
            self.logger.warning('Could not identify officer name column')
            return False

        # Process each officer row
        updated_count = 0
        for _, data_row in df.iterrows():
            officer_name_raw = str(data_row.get(name_col, ''))
            if not officer_name_raw or officer_name_raw == 'nan':
                continue

            officer_name_raw = clean_text(officer_name_raw)
            if not officer_name_raw:
                continue

            # Match to DB officers — or create if not found
            officer_id = None
            if officers:
                matched_name, match_score = match_officer(
                    officer_name_raw, officers,
                    threshold=config.FUZZY_OFFICER_THRESHOLD,
                )
                if matched_name:
                    officer_id = get_officer_id(
                        self.db, matched_name, company_id, fiscal_year,
                    )

            # No-update rule: Officer table is owned by SCT — Exercise never auto-inserts.
            # Skip rows whose officer wasn't previously created by sql_parser.
            if officer_id is None:
                self.logger.info(
                    "Exercise: officer not found in Officer table (Company_ID=%s FY=%s name=%r) — skipping",
                    company_id, fiscal_year, officer_name_raw
                )

            if officer_id is None:
                self.logger.debug('Could not create officer for: %s', officer_name_raw)
                continue

            # Extract values for each mapped field
            opt_shares = _safe_value(
                data_row.get(field_map.get('Option_Shares_Acquired', ''), 0),
            )
            opt_value = _safe_value(
                data_row.get(field_map.get('Option_Value_Realized', ''), 0),
            )
            stk_shares = _safe_value(
                data_row.get(field_map.get('Stock_Shares_Acquired', ''), 0),
            )
            stk_value = _safe_value(
                data_row.get(field_map.get('Stock_Value_Realized', ''), 0),
            )

            # sp_ExerciseandVested_U_MAYA runs UPDATE unconditionally on Officer's 4 cols.
            # Gate: skip if ANY of the 4 cols is already populated for this officer
            # (no-update rule — human may have entered data).
            # See docs/SP_Behavior_Analysis.md §8.
            from core.sp_gate import SPGate, STATUS_PARSED
            if not hasattr(self, '_sp_gate'):
                self._sp_gate = SPGate(self.db, self.logger)
            try:
                status = self._sp_gate.call_if_absent(
                    exists_sql=(
                        "SELECT 1 FROM Officer "
                        "WHERE Officer_ID=? AND Company_ID=? AND FiscalYear=? "
                        "AND (Option_Shares_Acquired IS NOT NULL OR Option_Value_Realized IS NOT NULL "
                        "  OR Stock_Shares_Acquired IS NOT NULL OR Stock_Value_Realized IS NOT NULL)"
                    ),
                    exists_params=[officer_id, company_id, fiscal_year],
                    sp_name="sp_ExerciseandVested_U_MAYA",
                    sp_params=[
                        company_id,      # @Company_ID
                        fiscal_year,     # @FiscalYear
                        officer_id,      # @Officer_ID
                        opt_shares,      # @Option_Shares_Acquired
                        opt_value,       # @Option_Value_Realized
                        stk_shares,      # @Stock_Shares_Acquired
                        stk_value,       # @Stock_Value_Realized
                        None,            # @Analyst_Notes
                        None,            # @Internal_Notes
                        None,            # @Notes_Comments_ID
                        1,               # @Type (1=option)
                        1,               # @SubType (1=exercised)
                        None,            # @No_EV_In_Proxy
                    ],
                    scope_label="Exercise:" + str(officer_name_raw) + " FY" + str(fiscal_year),
                )
                if status == STATUS_PARSED:
                    updated_count += 1
            except Exception:
                self.logger.error(
                    'Failed updating exercise data for officer %s: %s',
                    matched_name, traceback.format_exc(),
                )

        self.logger.info(
            'Company %s: updated %d exercise/vested records',
            company_name, updated_count,
        )

        # Update parsing status
        if updated_count > 0:
            self.update_parsing_status(
                company_id, fiscal_year, 'Vested_Parsed', 'Parsed',
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
        """Identify the column containing officer names.

        Parameters
        ----------
        df : pd.DataFrame

        Returns
        -------
        str or None
        """
        from fuzzywuzzy import fuzz

        name_keywords = ['name', 'officer', 'executive']
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
        """Mark exercise parsing as failed for a company row."""
        try:
            company_id = int(sct_row.get('Company_ID', 0))
            fiscal_year = int(sct_row.get('FiscalYear', 0))
            if company_id and fiscal_year:
                self.update_parsing_status(
                    company_id, fiscal_year,
                    'Vested_Parsed', 'Not Parsed',
                )
        except Exception:
            self.logger.error(
                'Failed updating error status: %s', traceback.format_exc(),
            )
