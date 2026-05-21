"""
pba_parser.py
Parses Plan-Based Awards tables from SEC filings and inserts award data
into the database.  Ported from pba_parser_server_v1.py (1212 lines).

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
    clean_l3,
    remove_total_rows,
)
from utils.officer_matcher import (
    match_officer,
    get_officer_id,
    get_company_officers,
)
from utils.header_mapper import separate_stuck_headers, map_columns
import config


# Keywords used to score tables for plan-based award content
PBA_KEYWORDS = [
    'grant', 'plan', 'based', 'award', 'estimated', 'future', 'payout',
    'equity', 'threshold', 'target', 'maximum', 'non-equity', 'option',
    'stock', 'incentive', 'date', 'action',
]

# Header keywords for separating stuck headers
PBA_HEADER_KEYWORDS = [
    'grant', 'plan', 'based', 'award', 'estimated', 'future', 'payout',
    'equity', 'threshold', 'target', 'maximum', 'non-equity', 'option',
    'stock', 'incentive', 'date', 'action', 'name', 'officer', 'all',
    'other', 'base', 'price', 'fair', 'value',
]

# ------------------------------------------------------------------
# Column-matching patterns for PBA fields
# ------------------------------------------------------------------

_GRANT_DATE_PATTERNS = [
    'grant date', 'date of grant',
]

_ACTION_DATE_PATTERNS = [
    'action date', 'approval date', 'date of action',
]

_NE_THRESHOLD_PATTERNS = [
    'estimated future payouts under non-equity incentive plan awards threshold',
    'non-equity incentive plan threshold',
    'non-equity threshold',
]

_NE_TARGET_PATTERNS = [
    'estimated future payouts under non-equity incentive plan awards target',
    'non-equity incentive plan target',
    'non-equity target',
]

_NE_MAXIMUM_PATTERNS = [
    'estimated future payouts under non-equity incentive plan awards maximum',
    'non-equity incentive plan maximum',
    'non-equity maximum',
]

_EQ_THRESHOLD_PATTERNS = [
    'estimated future payouts under equity incentive plan awards threshold',
    'equity incentive plan threshold',
    'equity threshold',
]

_EQ_TARGET_PATTERNS = [
    'estimated future payouts under equity incentive plan awards target',
    'equity incentive plan target',
    'equity target',
]

_EQ_MAXIMUM_PATTERNS = [
    'estimated future payouts under equity incentive plan awards maximum',
    'equity incentive plan maximum',
    'equity maximum',
]

_OPT_THRESHOLD_PATTERNS = [
    'option threshold',
    'options threshold',
]

_OPT_TARGET_PATTERNS = [
    'option target',
    'options target',
]

_OPT_MAXIMUM_PATTERNS = [
    'option maximum',
    'options maximum',
]

_ALL_OTHER_STOCK_PATTERNS = [
    'all other stock awards number of shares of stock or units',
    'all other stock awards',
    'shares of stock or units',
]

_ALL_OTHER_OPTIONS_PATTERNS = [
    'all other option awards number of securities underlying options',
    'all other option awards',
    'securities underlying options',
]

_BASE_PRICE_PATTERNS = [
    'exercise or base price of option awards',
    'exercise or base price',
    'base price',
]

_GRANT_DATE_PRICE_PATTERNS = [
    'grant date fair value of stock and option awards',
    'grant date fair value',
    'closing market price on grant date',
    'grant date price',
]

_GDFV_PATTERNS = [
    'grant date fair value of stock and option awards',
    'grant date fair value',
    'full grant date fair value',
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


def _identify_pba_columns(columns):
    """Map DataFrame columns to PBA field names.

    Parameters
    ----------
    columns : list[str]

    Returns
    -------
    dict
        Mapping of PBA field name to column name.
    """
    field_map = {}
    patterns_by_field = {
        'GrantDate': _GRANT_DATE_PATTERNS,
        'ActionDate': _ACTION_DATE_PATTERNS,
        'NonEquity_Threshold': _NE_THRESHOLD_PATTERNS,
        'NonEquity_Target': _NE_TARGET_PATTERNS,
        'NonEquity_Maximum': _NE_MAXIMUM_PATTERNS,
        'Equity_Threshold': _EQ_THRESHOLD_PATTERNS,
        'Equity_Target': _EQ_TARGET_PATTERNS,
        'Equity_Maximum': _EQ_MAXIMUM_PATTERNS,
        'Option_Threshold': _OPT_THRESHOLD_PATTERNS,
        'Option_Target': _OPT_TARGET_PATTERNS,
        'Option_Maximum': _OPT_MAXIMUM_PATTERNS,
        'AllOther_Stock': _ALL_OTHER_STOCK_PATTERNS,
        'AllOther_Options': _ALL_OTHER_OPTIONS_PATTERNS,
        'Base_Price': _BASE_PRICE_PATTERNS,
        'GrantDate_Price': _GRANT_DATE_PRICE_PATTERNS,
        'GDFV_Stock_Option': _GDFV_PATTERNS,
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


def _safe_date(value):
    """Parse a cell value into a datetime object (SQL Server datetime-compatible) or None.

    Production sp_wk_PlanBasedAward_U_MAYA declares @GrantDate / @ActionDate as DATETIME —
    passing a non-date string ('$100,000', '10%', etc.) errors out with
    'Error converting data type nvarchar to datetime'. We return None for anything that
    isn't parseable as a date so the SP just stores NULL.
    """
    import re as _re
    from datetime import datetime as _dt
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    val = clean_text(str(value)).strip()
    if not val or val.lower() in ('nan', 'none', ''):
        return None
    # If the cell starts with $, %, parentheses, or pure digits/commas → it's a money/number, not a date
    if _re.match(r'^[\$\(\-]', val) or _re.search(r'[%]', val):
        return None
    if _re.match(r'^[\d,]+(\.\d+)?$', val):
        return None
    # Try a handful of common SEC date formats
    for fmt in ('%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d', '%B %d, %Y', '%b %d, %Y', '%d-%b-%Y', '%d-%b-%y'):
        try:
            return _dt.strptime(val, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _extract_person_names_spacy(text):
    """Use spaCy NLP to extract PERSON entities from text.

    Parameters
    ----------
    text : str
        Text that may contain person names.

    Returns
    -------
    list[str]
        List of extracted person names.
    """
    try:
        import spacy
        nlp = spacy.load('en_core_web_sm')
        doc = nlp(text)
        return [ent.text.strip() for ent in doc.ents if ent.label_ == 'PERSON']
    except Exception:
        return []


class PBAParser(BaseParser):
    """Parse Plan-Based Awards tables from SEC filing HTML.

    For each company, fetches the filing page, identifies the PBA table
    via keyword scoring, extracts and cleans the data, maps columns,
    uses spaCy NLP to extract PERSON entities for officer name detection,
    matches officers, and inserts records via
    ``sp_wk_PlanBasedAward_U_MAYA``.
    """

    def __init__(self, db, logger_name=None):
        super(PBAParser, self).__init__(db, logger_name or 'PBAParser')
        self.fetcher = SECFetcher()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self):
        """Execute the plan-based award parsing step.

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

                # 2a. Check if award data already exists
                if self._pba_already_parsed(company_id, fiscal_year):
                    self.logger.info(
                        'PBA already parsed for %s (ID=%d, FY=%d), skipping',
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
            'PBA parsing complete. Processed=%d, Parsed=%d, '
            'Skipped=%d, NoTable=%d',
            result['companies_processed'], result['parsed'],
            result['skipped'], result['no_table_found'],
        )
        return result

    # ------------------------------------------------------------------
    # Pre-checks
    # ------------------------------------------------------------------

    def _pba_already_parsed(self, company_id, fiscal_year):
        """Check if plan-based award data already exists for this company/year.

        Returns
        -------
        bool
        """
        row = self.db.fetch_one(
            "SELECT oa.Officer_Awards_ID "
            "FROM Officer_Awards oa "
            "JOIN Officer o ON oa.Officer_ID = o.Officer_ID "
            "WHERE o.Company_ID=? AND o.FiscalYear=?",
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
        """Fetch filing, find PBA table, extract and insert data.

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
            'Processing PBA for %s (ID=%d, FY=%d)',
            company_name, company_id, fiscal_year,
        )

        # Fetch filing HTML
        soup = self.fetcher.fetch_page(link)
        if soup is None:
            self.logger.warning('Failed to fetch filing page: %s', link)
            return False

        from utils.table_scorer import classify_table
        import re as _re

        # === Find PBA table — text search FIRST (most precise), then classify ===
        best_table = None
        best_score = 0

        # METHOD 1: Search for "Grants of Plan" text (same as old project — most reliable)
        grant_texts = soup(text=_re.compile("Grants? of Plan|Plan.Based Award", _re.I))
        for text_match in grant_texts:
            try:
                table = text_match.parent.find_next('table')
                if table and len(table.find_all('tr')) >= 5:
                    if classify_table(table) not in ('SCT', 'EQUITY', 'EXERCISE'):
                        # Validate: must have officer names (not just percentages)
                        text = table.get_text(separator=' ', strip=True).lower()
                        if '$' in text or 'name' in text:
                            best_table = table
                            best_score = 18
                            self.logger.info('PBA: Found via "Grants of Plan" text (score=18)')
                            break
            except Exception:
                continue

        # METHOD 2: classify_table — but validate it has actual data
        if best_table is None:
            tables = soup.find_all('table')
            for table in tables:
                if len(table.find_all('tr')) < 5:
                    continue
                if classify_table(table) == 'PBA':
                    text = table.get_text(separator=' ', strip=True).lower()
                    # Must have dollar signs or "name" — not just performance metrics
                    if '$' in text or 'name' in text:
                        best_table = table
                        best_score = 15
                        self.logger.info('PBA: Found via classify_table (PBA)')
                        break

        # METHOD 3: scan for threshold+target+maximum
        if best_table is None:
            for table in (tables if 'tables' in dir() else soup.find_all('table')):
                if len(table.find_all('tr')) < 5:
                    continue
                text = table.get_text(separator=' ', strip=True).lower().replace('\xa0', ' ')
                if 'threshold' in text and 'target' in text and 'maximum' in text:
                    if classify_table(table) not in ('SCT', 'EQUITY', 'EXERCISE'):
                        if '$' in text or 'name' in text:
                            best_table = table
                            best_score = 10
                            self.logger.info('PBA: Found via keyword scan')
                            break

        self.logger.info(
            'Best PBA table score: %d (type: %s)',
            best_score, classify_table(best_table) if best_table else 'NONE',
        )

        if best_score < 5 or best_table is None:
            self.logger.warning(
                'No qualifying PBA table found for %s (best score=%d, '
                'required=%d)',
                company_name, best_score, config.TARGET_TABLE_SCORE,
            )
            return False

        # Extract and clean table data
        raw_data = extract_table_with_spans(best_table)
        if not raw_data or len(raw_data) < 2:
            self.logger.warning(
                'Extracted PBA table has insufficient data',
            )
            return False

        df = pd.DataFrame(raw_data)

        # Use multi-row header merger for SEC multi-row headers
        from utils.multirow_header import merge_multirow_headers, find_column_by_keywords
        df, merged_headers = merge_multirow_headers(df)
        self.logger.debug('Merged headers: %s', merged_headers[:8])

        if df.empty:
            self.logger.warning('PBA table is empty after header merge')
            return False

        # Map columns to PBA fields — sequential matching like old project
        # PBA headers: Name | Grant Date | [Non-Equity: Threshold|Target|Max] | [Equity: Threshold|Target|Max] | AllOther Stock | AllOther Options | Base Price | GDFV
        cols = list(df.columns)
        field_map = {}

        # First pass: keyword-based for specific fields
        for i, col in enumerate(cols):
            cl = str(col).lower()
            if 'grant' in cl and 'date' in cl and 'GrantDate' not in field_map:
                field_map['GrantDate'] = col
            elif 'action' in cl and 'date' in cl and 'ActionDate' not in field_map:
                field_map['ActionDate'] = col
            elif ('all other' in cl or 'all other' in cl.replace('\n',' ')) and 'stock' in cl and 'AllOther_Stock' not in field_map:
                field_map['AllOther_Stock'] = col
            elif ('all other' in cl or 'all other' in cl.replace('\n',' ')) and 'option' in cl and 'AllOther_Options' not in field_map:
                field_map['AllOther_Options'] = col
            elif ('base' in cl or 'exercise') and 'price' in cl and 'Base_Price' not in field_map:
                field_map['Base_Price'] = col
            elif 'fair value' in cl and 'grant' in cl and 'GDFV_Stock_Option' not in field_map:
                field_map['GDFV_Stock_Option'] = col

        # Second pass: find threshold/target/maximum in ORDER (first set = non-equity, second = equity)
        threshold_cols = [c for c in cols if 'threshold' in str(c).lower()]
        target_cols = [c for c in cols if 'target' in str(c).lower() and c not in threshold_cols]
        maximum_cols = [c for c in cols if 'maximum' in str(c).lower() or 'max' in str(c).lower().split()]

        if threshold_cols:
            field_map['NonEquity_Threshold'] = threshold_cols[0]
            if len(threshold_cols) > 1:
                field_map['Equity_Threshold'] = threshold_cols[1]
        if target_cols:
            field_map['NonEquity_Target'] = target_cols[0]
            if len(target_cols) > 1:
                field_map['Equity_Target'] = target_cols[1]
        if maximum_cols:
            field_map['NonEquity_Maximum'] = maximum_cols[0]
            if len(maximum_cols) > 1:
                field_map['Equity_Maximum'] = maximum_cols[1]

        # Fallback: position-based for data columns
        # Also check for RSU/PRSU/PSU patterns (common alternate headers)
        if not field_map.get('Equity_Threshold'):
            for col in cols:
                cl = str(col).lower()
                if ('prsu' in cl or 'psu' in cl or 'performance' in cl) and 'threshold' in cl:
                    field_map['Equity_Threshold'] = col
                elif ('prsu' in cl or 'psu' in cl or 'performance' in cl) and 'target' in cl:
                    field_map['Equity_Target'] = col
                elif ('prsu' in cl or 'psu' in cl or 'performance' in cl) and 'maximum' in cl:
                    field_map['Equity_Maximum'] = col

        if not field_map.get('AllOther_Stock'):
            for col in cols:
                cl = str(col).lower()
                if ('rsu' in cl and 'prsu' not in cl) or ('restricted' in cl and 'unit' in cl):
                    field_map['AllOther_Stock'] = col
                    break

        if not field_map.get('GDFV_Stock_Option'):
            for col in cols:
                cl = str(col).lower()
                if 'fair value' in cl or 'grant date' in cl and 'value' in cl:
                    field_map['GDFV_Stock_Option'] = col
                    break

        # Fallback: position-based
        if not field_map:
            data_cols = [c for c in cols if 'name' not in str(c).lower() and 'col_' not in str(c) and 'officer' not in str(c).lower() and 'executive' not in str(c).lower()]
            if len(data_cols) >= 3:
                field_map['Equity_Threshold'] = data_cols[0]
                if len(data_cols) > 1: field_map['Equity_Target'] = data_cols[1]
                if len(data_cols) > 2: field_map['Equity_Maximum'] = data_cols[2]
                if len(data_cols) > 3: field_map['GDFV_Stock_Option'] = data_cols[-1]

        self.logger.info('Identified PBA columns: %s', field_map)

        if not field_map:
            self.logger.warning(
                'Could not identify any PBA columns for %s', company_name,
            )
            return False

        # Get officer list for matching
        officers = get_company_officers(self.db, company_id, fiscal_year)
        if not officers:
            self.logger.warning(
                'No officers found in DB for %s (ID=%d, FY=%d)',
                company_name, company_id, fiscal_year,
            )
            return False

        # Identify the name column -- try standard detection first, then
        # fall back to spaCy NLP entity extraction
        name_col = self._find_name_column(df)
        use_spacy_names = False

        if name_col is None:
            self.logger.info(
                'Standard name column detection failed; attempting spaCy NLP',
            )
            use_spacy_names = True

        # Process each row
        inserted_count = 0
        current_officer_name = None
        current_officer_id = None

        for _, data_row in df.iterrows():
            # Determine officer name
            if use_spacy_names:
                # Concatenate all text in the row and extract PERSON entities
                row_text = ' '.join(
                    str(v) for v in data_row.values
                    if pd.notna(v) and str(v).strip()
                )
                person_names = _extract_person_names_spacy(row_text)
                officer_name_raw = person_names[0] if person_names else ''
            else:
                officer_name_raw = str(data_row.get(name_col, ''))

            # If a name is found, update the current officer context
            # (PBA tables often have the officer name on one row with
            # multiple data rows following)
            if officer_name_raw and officer_name_raw != 'nan':
                officer_name_raw = clean_text(officer_name_raw)
                if officer_name_raw:
                    if officers:
                        matched_name, match_score = match_officer(
                            officer_name_raw, officers,
                            threshold=config.FUZZY_OFFICER_THRESHOLD,
                        )
                        if matched_name:
                            current_officer_name = matched_name
                            current_officer_id = get_officer_id(
                                self.db, matched_name, company_id, fiscal_year,
                            )

                    # No-update rule: Officer table is owned by SCT — PBA never auto-inserts.
                    if current_officer_id is None:
                        self.logger.info(
                            "PBA: officer not found in Officer table (Company_ID=%s FY=%s name=%r) — skipping",
                            company_id, fiscal_year, officer_name_raw
                        )

            if current_officer_id is None:
                continue

            # Extract values — handle $ in separate cell
            all_cols = list(data_row.index)
            def _get_pba_val(col_name):
                if not col_name:
                    return 0
                val = str(data_row.get(col_name, '')).strip()
                if val in ('$', '', '-', '—', 'nan') and col_name in all_cols:
                    idx = all_cols.index(col_name)
                    # Look at next 1-2 columns for the actual number
                    for offset in [1, 2]:
                        if idx + offset < len(all_cols):
                            next_val = str(data_row.get(all_cols[idx + offset], '')).strip()
                            if next_val and next_val not in ('$', '', '-', '—', 'nan'):
                                return _safe_value(next_val)
                return _safe_value(val)

            grant_date = _safe_date(data_row.get(field_map.get('GrantDate', ''), ''))
            action_date = _safe_date(data_row.get(field_map.get('ActionDate', ''), ''))
            ne_threshold = _get_pba_val(field_map.get('NonEquity_Threshold', ''))
            ne_target = _get_pba_val(field_map.get('NonEquity_Target', ''))
            ne_maximum = _get_pba_val(field_map.get('NonEquity_Maximum', ''))
            eq_threshold = _get_pba_val(field_map.get('Equity_Threshold', ''))
            eq_target = _get_pba_val(field_map.get('Equity_Target', ''))
            eq_maximum = _get_pba_val(field_map.get('Equity_Maximum', ''))
            opt_threshold = _get_pba_val(field_map.get('Option_Threshold', ''))
            opt_target = _get_pba_val(field_map.get('Option_Target', ''))
            opt_maximum = _get_pba_val(field_map.get('Option_Maximum', ''))
            all_other_stock = _get_pba_val(field_map.get('AllOther_Stock', ''))
            all_other_options = _get_pba_val(field_map.get('AllOther_Options', ''))
            base_price = _get_pba_val(field_map.get('Base_Price', ''))
            grant_date_price = _get_pba_val(field_map.get('GrantDate_Price', ''))
            gdfv = _get_pba_val(field_map.get('GDFV_Stock_Option', ''))

            # Skip rows where all numeric values are zero
            all_values = [
                ne_threshold, ne_target, ne_maximum,
                eq_threshold, eq_target, eq_maximum,
                opt_threshold, opt_target, opt_maximum,
                all_other_stock, all_other_options,
                base_price, grant_date_price, gdfv,
            ]
            if all(v == 0 for v in all_values) and not grant_date and not action_date:
                continue

            # sp_wk_PlanBasedAward_U_MAYA: Officer_Awards_ID=0 → INSERT branch (safe for Maya).
            # Gate at (Company_ID + FiscalYear + Officer_ID) so we don't insert duplicates
            # for an officer who already has PBA rows. See docs/SP_Behavior_Analysis.md §9.
            from core.sp_gate import SPGate, STATUS_PARSED
            if not hasattr(self, '_sp_gate'):
                self._sp_gate = SPGate(self.db, self.logger)
            try:
                # Pick Award_Category based on which threshold/target group is populated.
                # 1=NonEquity, 2=Equity, 3=Option (mapped to Officer_Awards.Award_Category)
                if ne_threshold or ne_target or ne_maximum:
                    award_category = 1
                elif eq_threshold or eq_target or eq_maximum:
                    award_category = 2
                elif opt_threshold or opt_target or opt_maximum:
                    award_category = 3
                elif all_other_stock:
                    award_category = 4
                elif all_other_options:
                    award_category = 5
                else:
                    award_category = 1
                status = self._sp_gate.call_if_absent(
                    exists_sql=(
                        "SELECT 1 FROM Officer_Awards oa "
                        "INNER JOIN Officer o ON o.Officer_ID = oa.Officer_ID "
                        "WHERE o.Company_ID=? AND o.FiscalYear=? AND oa.Officer_ID=?"
                    ),
                    exists_params=[company_id, fiscal_year, current_officer_id],
                    sp_name="sp_wk_PlanBasedAward_U_MAYA",
                    sp_params=[
                        0,                    # @ID (wk_PlanBasedAward.ID — 0 means new)
                        None,                 # @TagName
                        0,                    # @Officer_Awards_ID — 0 ⇒ SP INSERTs
                        current_officer_id,   # @Officer_ID
                        company_id,           # @Company_ID
                        fiscal_year,          # @FiscalYear
                        award_category,       # @Award_Category
                        grant_date,           # @GrantDate
                        action_date,          # @ActionDate
                        ne_threshold,         # @NonEquity_Threshold
                        ne_target,            # @NonEquity_Target
                        ne_maximum,           # @NonEquity_Maximum
                        eq_threshold,         # @Equity_Threshold
                        eq_target,            # @Equity_Target
                        eq_maximum,           # @Equity_Maximum
                        opt_threshold,        # @Option_Threshold
                        opt_target,           # @Option_Target
                        opt_maximum,          # @Option_Maximum
                        all_other_stock,      # @AllOther_Stock
                        all_other_options,    # @AllOther_Options
                        base_price,           # @Base_Price
                        grant_date_price,     # @GrantDate_Price
                        gdfv,                 # @GDFV_Stock_Option
                    ],
                    scope_label="PBA:" + str(current_officer_name) + " FY" + str(fiscal_year),
                )
                if status == STATUS_PARSED:
                    inserted_count += 1
            except Exception:
                self.logger.error(
                    'Failed inserting PBA data for officer %s: %s',
                    current_officer_name, traceback.format_exc(),
                )

        self.logger.info(
            'Company %s: inserted %d PBA records',
            company_name, inserted_count,
        )

        # Update parsing status
        if inserted_count > 0:
            self.update_parsing_status(
                company_id, fiscal_year, 'PBA_Parsed', 'Parsed',
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
        """Mark PBA parsing as failed for a company row."""
        try:
            company_id = int(sct_row.get('Company_ID', 0))
            fiscal_year = int(sct_row.get('FiscalYear', 0))
            if company_id and fiscal_year:
                self.update_parsing_status(
                    company_id, fiscal_year,
                    'PBA_Parsed', 'Not Parsed',
                )
        except Exception:
            self.logger.error(
                'Failed updating error status: %s', traceback.format_exc(),
            )
