"""
equity_parser.py
Parses Outstanding Equity Holdings tables from SEC filings and inserts
equity award data into the database.  Ported from eq_parser_server_v2.py
(1870 lines).

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
    get_filing_dir,
    load_df,
    save_df,
)
from utils.html_fetcher import SECFetcher
from utils.table_extractor import extract_table_data, extract_table_with_spans
from utils.table_scorer import score_table
from utils.data_cleaner import clean_text, clean_numeric, clean_l1, clean_l2, remove_total_rows
from utils.officer_matcher import (
    match_officer,
    get_officer_id,
    get_company_officers,
)
from utils.header_mapper import separate_stuck_headers, map_columns
import config


# Keywords used to score tables for outstanding equity content
EQUITY_KEYWORDS = [
    'option', 'award', 'outstanding', 'equity', 'number', 'securities',
    'underlying', 'unexercised', 'exercisable', 'unexercisable', 'exercise',
    'price', 'expiration', 'unvested', 'shares', 'market', 'value', 'grant',
    'date',
]

# Header keywords for separating stuck headers in equity tables
EQUITY_HEADER_KEYWORDS = [
    'option', 'award', 'outstanding', 'equity', 'number', 'securities',
    'underlying', 'unexercised', 'exercisable', 'unexercisable', 'exercise',
    'price', 'expiration', 'unvested', 'shares', 'market', 'value', 'grant',
    'date', 'name', 'stock', 'incentive', 'plan', 'earned', 'unearned',
    'vested', 'payout',
]

# ------------------------------------------------------------------
# Column-matching patterns for the 5 equity types
# ------------------------------------------------------------------

# Type 1: Exercisable Options -- Number of Securities Underlying
#          Unexercised Options - Exercisable
_TYPE1_PATTERNS = [
    'exercisable', 'securities underlying unexercised options exercisable',
    'number of securities underlying unexercised options exercisable',
    'unexercised exercisable',
]

# Type 2: Unexercisable Options -- Number of Securities Underlying
#          Unexercised Options - Unexercisable
_TYPE2_PATTERNS = [
    'unexercisable', 'securities underlying unexercised options unexercisable',
    'number of securities underlying unexercised options unexercisable',
    'unexercised unexercisable',
]

# Type 3: Unearned EIP Options -- Equity Incentive Plan Awards: Number of
#          Securities Underlying Unexercised Unearned Options
_TYPE3_PATTERNS = [
    'equity incentive plan awards number',
    'equity incentive plan awards unearned options',
    'unearned options', 'unexercised unearned',
    'incentive plan unearned',
]

# Type 4: Unvested Stock (Number of Shares) -- Number of Shares or Units
#          of Stock That Have Not Vested
_TYPE4_PATTERNS = [
    'shares or units of stock that have not vested',
    'number of shares that have not vested',
    'shares not vested', 'unvested shares number',
    'number of shares or units',
    'stock that have not vested',
]

# Type 5: Unvested Shares (Market Value) -- Market Value of Shares or Units
#          of Stock That Have Not Vested
_TYPE5_PATTERNS = [
    'market value of shares or units of stock that have not vested',
    'market value shares not vested',
    'market value of shares that have not vested',
    'market value unvested',
    'market value of shares or units',
]


def _match_column_type(col_name, patterns, threshold=65):
    """Check if a column name fuzzy-matches any of the given patterns.

    Parameters
    ----------
    col_name : str
        The column header text.
    patterns : list[str]
        Reference patterns to match against.
    threshold : int
        Minimum fuzz.partial_ratio score.

    Returns
    -------
    bool
        True if the column matches at least one pattern.
    """
    from fuzzywuzzy import fuzz

    col_lower = str(col_name).lower().strip()
    for pattern in patterns:
        score = fuzz.partial_ratio(col_lower, pattern.lower())
        if score >= threshold:
            return True
    return False


def _identify_equity_columns(columns):
    """Map DataFrame columns to equity types (1-5).

    Parameters
    ----------
    columns : list[str]
        Column header names from the equity table.

    Returns
    -------
    dict
        Mapping of equity type (int 1-5) to column name.
        Only types that were matched are included.
    """
    type_map = {}
    patterns_by_type = {
        1: _TYPE1_PATTERNS,
        2: _TYPE2_PATTERNS,
        3: _TYPE3_PATTERNS,
        4: _TYPE4_PATTERNS,
        5: _TYPE5_PATTERNS,
    }

    for eq_type, patterns in patterns_by_type.items():
        for col in columns:
            if _match_column_type(col, patterns):
                type_map[eq_type] = col
                break

    return type_map


def _safe_equity_value(value):
    """Convert an equity cell value to a numeric, returning 0 on failure."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return 0
    result = clean_numeric(value)
    if isinstance(result, float) and np.isnan(result):
        return 0
    return result


class EquityParser(BaseParser):
    """Parse Outstanding Equity Holdings tables from SEC filing HTML.

    For each company, fetches the filing page, identifies the equity table
    via keyword scoring, extracts and cleans the data, maps columns to the
    5 standard equity types, matches officers, and inserts records via
    ``sp_Outstanding_Equity_Awards_IU_MAYA``.
    """

    def __init__(self, db, logger_name=None):
        super(EquityParser, self).__init__(db, logger_name or 'EquityParser')
        self.fetcher = SECFetcher()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self):
        """Execute the equity parsing step.

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

                # Look up Company_ID from DB by name (not from CSV)
                comp_row = self.db.fetch_one(
                    "SELECT Company_ID FROM Company WHERE CompanyName=?",
                    [company_name]
                )
                if not comp_row:
                    comp_row = self.db.fetch_one(
                        "SELECT Company_ID FROM Company WHERE CompanyName LIKE ?",
                        ['%' + company_name.split()[0] + '%']
                    )
                company_id = comp_row['Company_ID'] if comp_row else 0

                result['companies_processed'] += 1
                self.report_progress(processed=result['companies_processed'], parsed=result.get('parsed', 0), failed=result.get('no_table_found', 0))

                # 2a. Check if equity data already exists
                if self._equity_already_parsed(company_id, fiscal_year):
                    self.logger.info(
                        'Equity already parsed for %s (ID=%d, FY=%d), skipping',
                        company_name, company_id, fiscal_year,
                    )
                    result['skipped'] += 1
                    continue

                # Get the filing link — try SCT row first, then edgar_feed
                link = str(sct_row.get('Link', '')).strip()
                # Clean URL
                if link:
                    link = link.replace('/ix?doc=/', '/')
                    link = link.replace('/cgi-bin/browse-edgar/', '/')
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
            'Equity parsing complete. Processed=%d, Parsed=%d, '
            'Skipped=%d, NoTable=%d',
            result['companies_processed'], result['parsed'],
            result['skipped'], result['no_table_found'],
        )
        return result

    # ------------------------------------------------------------------
    # Pre-checks
    # ------------------------------------------------------------------

    def _equity_already_parsed(self, company_id, fiscal_year):
        """Check if equity data already exists for this company/year.

        Returns
        -------
        bool
        """
        row = self.db.fetch_one(
            "SELECT oea.Officer_ID "
            "FROM Officer_Outstanding_Equity oea "
            "JOIN Officer o ON oea.Officer_ID = o.Officer_ID "
            "WHERE o.Company_ID=? AND o.FiscalYear=?",
            [company_id, fiscal_year],
        )
        return row is not None

    def _get_filing_link(self, edgar_df, sct_row):
        """Extract the filing URL for this company from the edgar_feed.

        Parameters
        ----------
        edgar_df : pd.DataFrame
            The edgar_feed DataFrame.
        sct_row : pd.Series
            Current company row from SCT parsed transactions.

        Returns
        -------
        str or None
            Filing URL, or None if not found.
        """
        company_id = int(sct_row.get('Company_ID', 0))

        # Try matching on Company_ID
        if 'Company_ID' in edgar_df.columns:
            match = edgar_df[edgar_df['Company_ID'] == company_id]
            if not match.empty:
                for col_name in ['Link', 'link', 'Filing_Link', 'filing_link', 'URL', 'url']:
                    if col_name in match.columns:
                        link = str(match.iloc[0][col_name])
                        if link and link != 'nan':
                            return link

        # Fallback: try matching on CIK
        cik = sct_row.get('CIK', None)
        if cik is not None and 'CIK' in edgar_df.columns:
            match = edgar_df[edgar_df['CIK'] == int(cik)]
            if not match.empty:
                for col_name in ['Link', 'link', 'Filing_Link', 'filing_link', 'URL', 'url']:
                    if col_name in match.columns:
                        link = str(match.iloc[0][col_name])
                        if link and link != 'nan':
                            return link

        return None

    # ------------------------------------------------------------------
    # Per-company processing
    # ------------------------------------------------------------------

    def _process_company(self, company_id, fiscal_year, company_name, link):
        """Fetch filing, find equity table, extract and insert data.

        Parameters
        ----------
        company_id : int
        fiscal_year : int
        company_name : str
        link : str
            URL of the SEC filing page.

        Returns
        -------
        bool
            True if equity data was successfully parsed and inserted.
        """
        self.logger.info(
            'Processing equity for %s (ID=%d, FY=%d)',
            company_name, company_id, fiscal_year,
        )

        # 2b. Fetch filing HTML
        soup = self.fetcher.fetch_page(link)
        if soup is None:
            self.logger.warning('Failed to fetch filing page: %s', link)
            return False

        from utils.table_scorer import classify_table

        # === Find EQUITY table using classification ===
        best_table = None
        best_score = 0
        best_matched = []

        tables = soup.find_all('table')
        for table in tables:
            if len(table.find_all('tr')) < 5:
                continue
            table_type = classify_table(table)
            if table_type == 'EQUITY':
                best_table = table
                best_score = 15
                self.logger.info('Equity: Found via classify_table (EQUITY)')
                break

        # Fallback: text search for "Outstanding Equity Awards"
        if best_table is None:
            import re as _re
            equity_texts = soup(text=_re.compile("utstanding.*Equity|utstanding.*Award", _re.I))
            for text_match in equity_texts:
                try:
                    table = text_match.parent.find_next('table')
                    if table and len(table.find_all('tr')) >= 5:
                        if classify_table(table) != 'SCT':  # Skip SCT tables!
                            best_table = table
                            best_score = 12
                            self.logger.info('Equity: Found via text search (skipped SCT)')
                            break
                except Exception:
                    continue

        self.logger.info(
            'Best equity table score: %d (type: %s)',
            best_score, classify_table(best_table) if best_table else 'NONE',
        )

        if best_score < 5 or best_table is None:
            self.logger.warning(
                'No qualifying equity table found for %s (best score=%d, '
                'required=%d)',
                company_name, best_score, config.TARGET_TABLE_SCORE,
            )
            return False

        # 2d. Extract and clean table data
        raw_data = extract_table_with_spans(best_table)
        if not raw_data or len(raw_data) < 2:
            self.logger.warning('Extracted equity table has insufficient data')
            return False

        df = pd.DataFrame(raw_data)

        # Use multi-row header merger for SEC multi-row headers
        from utils.multirow_header import merge_multirow_headers, find_column_by_keywords
        df, merged_headers = merge_multirow_headers(df)
        self.logger.debug('Merged headers: %s', merged_headers[:8])

        if df.empty:
            self.logger.warning('Equity table is empty after header merge')
            return False

        # Map columns to equity fields using merged headers
        type_map = find_column_by_keywords(list(df.columns), {
            'exercisable': ['exercisable', 'number', 'securities'],
            'unexercisable': ['unexercisable', 'number', 'securities'],
            'exercise_price': ['exercise', 'price'],
            'expiration': ['expiration', 'date'],
            'unvested_shares': ['unvested', 'shares', 'number', 'units'],
            'unvested_value': ['unvested', 'market', 'value'],
            'grant_date': ['grant', 'date'],
        })

        # Fallback: position-based for standard equity table layouts
        data_cols = [c for c in df.columns if 'name' not in str(c).lower() and 'col_' not in str(c)]
        if not type_map and len(data_cols) >= 5:
            type_map = {
                'exercisable': data_cols[0],
                'unexercisable': data_cols[1],
                'exercise_price': data_cols[2],
                'expiration': data_cols[3],
                'unvested_shares': data_cols[4],
            }
            if len(data_cols) > 5:
                type_map['unvested_value'] = data_cols[5]

        self.logger.info('Identified equity types: %s', type_map)

        if not type_map:
            self.logger.warning(
                'Could not identify any equity type columns for %s',
                company_name,
            )
            return False

        # 2f. Get officer list for matching (empty is OK — auto-create will handle)
        officers = get_company_officers(self.db, company_id, fiscal_year)
        if not officers:
            self.logger.debug('No existing officers for %s — will auto-create', company_name)

        # Identify the name column
        name_col = self._find_name_column(df)
        if name_col is None:
            self.logger.warning('Could not identify officer name column')
            return False

        # 2g. Process each officer row
        inserted_count = 0
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

            # If no match, create the officer
            if officer_id is None:
                try:
                    self.db.execute(
                        "INSERT INTO Officer (OfficerName, Company_ID, FiscalYear) VALUES (?,?,?)",
                        [officer_name_raw, company_id, fiscal_year]
                    )
                    self.db.commit()
                    row_result = self.db.fetch_one(
                        "SELECT Officer_ID FROM Officer WHERE Company_ID=? AND FiscalYear=? AND OfficerName=?",
                        [company_id, fiscal_year, officer_name_raw]
                    )
                    officer_id = row_result['Officer_ID'] if row_result else None
                except Exception:
                    pass

            if officer_id is None:
                continue

            # Insert equity data directly
            # Helper: get value, handling $ in separate cell
            def _get_val(row, col_name, all_cols):
                if not col_name:
                    return 0
                val = str(row.get(col_name, '')).strip()
                # If value is just '$' or empty, look at the NEXT column
                if val in ('$', '', '-', '—') and col_name in all_cols:
                    idx = all_cols.index(col_name)
                    if idx + 1 < len(all_cols):
                        next_val = str(row.get(all_cols[idx + 1], '')).strip()
                        if next_val and next_val not in ('$', ''):
                            val = next_val
                return _safe_equity_value(val)

            all_cols = list(data_row.index)
            try:
                exercisable = _get_val(data_row, type_map.get('exercisable', ''), all_cols)
                unexercisable = _get_val(data_row, type_map.get('unexercisable', ''), all_cols)
                ex_price = _get_val(data_row, type_map.get('exercise_price', ''), all_cols)
                expiration = str(data_row.get(type_map.get('expiration', ''), '')).strip()
                unvested_shares = _get_val(data_row, type_map.get('unvested_shares', ''), all_cols)
                unvested_value = _get_val(data_row, type_map.get('unvested_value', ''), all_cols)
                grant_date = str(data_row.get(type_map.get('grant_date', ''), '')).strip()

                # Use SPGate to call production SP. Gate at (Company_ID + FiscalYear)
                # so we don't insert duplicate grants for an officer that already has
                # equity rows for this filing.
                # See docs/SP_Behavior_Analysis.md §7 for rationale.
                from core.sp_gate import SPGate, STATUS_PARSED
                if not hasattr(self, '_sp_gate'):
                    self._sp_gate = SPGate(self.db, self.logger)
                expiration_clean = expiration if expiration and expiration != 'nan' else None
                grant_date_clean = grant_date if grant_date and grant_date != 'nan' else None
                num_securities = exercisable + unexercisable + unvested_shares
                status = self._sp_gate.call_if_absent(
                    exists_sql=(
                        "SELECT 1 FROM Officer_Outstanding_Equity oe "
                        "INNER JOIN Officer o ON o.Officer_ID = oe.Officer_ID "
                        "WHERE o.Company_ID=? AND o.FiscalYear=? AND oe.Officer_ID=?"
                    ),
                    exists_params=[company_id, fiscal_year, officer_id],
                    sp_name="sp_Outstanding_Equity_Awards_IU_MAYA",
                    sp_params=[
                        None,            # @Officer_Outstanding_Equity_ID — NULL ⇒ SP INSERTs
                        company_id,      # @Company_ID
                        fiscal_year,     # @FiscalYear
                        1,               # @Equity_Type (1=Exercisable Options)
                        officer_id,      # @Officer_ID
                        grant_date_clean,    # @Grant_Date
                        num_securities,  # @Number_Securities
                        ex_price,        # @Exercise_Price
                        expiration_clean,    # @Expiration_Date
                        None,            # @Market_Value (for types 4/5)
                        None,            # @Tracking_Stock_Ticker
                        None,            # @No_OEA_In_Proxy
                        None,            # @Outstanding_Modification
                    ],
                    scope_label="Equity:" + str(officer_name_raw) + " FY" + str(fiscal_year),
                )
                if status == STATUS_PARSED:
                    inserted_count += 1
            except Exception:
                self.logger.error(
                    'Failed inserting equity for officer %s: %s',
                    matched_name, traceback.format_exc(),
                )

        self.logger.info(
            'Company %s: inserted %d equity records', company_name, inserted_count,
        )

        # 2h. Update parsing status
        if inserted_count > 0:
            self.update_parsing_status(
                company_id, fiscal_year,
                'Outstanding_Equity_Parsed', 'Parsed',
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
            DataFrame with proper column headers, or None if construction
            fails.
        """
        if df.empty or len(df) < 2:
            return None

        # Strategy: use the first row as header.  If it looks numeric (most
        # cells are numbers), try the second row instead.
        header_idx = 0
        first_row = df.iloc[0]
        numeric_count = sum(
            1 for v in first_row
            if re.match(r'^[\d,.$\-()]+$', str(v).strip()) and str(v).strip()
        )
        if numeric_count > len(first_row) / 2 and len(df) > 2:
            header_idx = 1

        headers = [clean_text(str(v)) if pd.notna(v) else 'col_{}'.format(i)
                    for i, v in enumerate(df.iloc[header_idx])]

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
            Column name, or None if not identifiable.
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
        """Mark equity parsing as failed for a company row."""
        try:
            company_id = int(sct_row.get('Company_ID', 0))
            fiscal_year = int(sct_row.get('FiscalYear', 0))
            if company_id and fiscal_year:
                self.update_parsing_status(
                    company_id, fiscal_year,
                    'Outstanding_Equity_Parsed', 'Not Parsed',
                )
        except Exception:
            self.logger.error(
                'Failed updating error status: %s', traceback.format_exc(),
            )
