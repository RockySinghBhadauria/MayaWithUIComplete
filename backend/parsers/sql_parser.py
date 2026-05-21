"""sql_parser.py — Read SCT cleaned CSV files and INSERT officer compensation via SPs.

Pipeline step 4 (after sct_parse + data_entry). For each L3 file from sct_parse:
  1. Look up Company_ID (Company table is server-managed — no auto-insert; if absent, skip)
  2. For each officer row in the L3 CSV:
     - Gate: SELECT 1 FROM wk_SummaryComp WHERE Company_ID+FiscalYear+OfficerName → skip if exists
     - Call sp_wk_SummaryComp_IU_MAYA (18 params)  → writes wk_SummaryComp
     - Call sp_wk_SummaryComp_U_MAYA  (16 params)  → writes Officer
     - Call sp_Officer_FirstLastName_U_MAYA (10 params) → splits name on Officer
  3. After all officers for a company are written, call sp_Tracking_Data_Entry_U_MAYA once.

References:
  - SP definitions: docs/SP_Definitions_raw.md
  - SP behavior + gate rationale: docs/SP_Behavior_Analysis.md
  - Reference call pattern: OfficeProjects/zipandothers/Maya_11032026/Maya_11032026/SCT_module/SQL_parser_server_v3.py
"""
import os
import re
import glob
from datetime import datetime

import pandas as pd
import numpy as np

from parsers.base_parser import BaseParser
from utils.csv_manager import get_filing_dir, sct_parsed_path
from core.sp_gate import SPGate, STATUS_PARSED, STATUS_ALREADY_EXIST, STATUS_NOT_PARSED


def _clean_money(val):
    """Convert a compensation string to integer dollars. 0 if junk."""
    if val is None or pd.isna(val):
        return 0
    s = str(val).strip()
    if not s or s in ['-', '—', '–', 'N/A', 'nan', '']:
        return 0
    s = re.sub(r'[\$,\s ​]', '', s)
    if '(' in s and ')' in s:
        s = '-' + s.replace('(', '').replace(')', '')
    s = re.sub(r'[^\d.\-]', '', s)
    if not s or s == '-' or s == '.':
        return 0
    try:
        result = int(float(s))
        if abs(result) > 999999999:
            return 0
        return result
    except (ValueError, TypeError):
        return 0


def _find_column(columns, keywords):
    for col in columns:
        col_lower = str(col).lower().replace('\n', ' ').replace('  ', ' ')
        for kw in keywords:
            if kw in col_lower:
                return col
    return None


def _split_name(full_name):
    """Split 'First [M.] Last [Suffix]' into (first, middle, last, suffix). Best-effort."""
    parts = (full_name or "").strip().split()
    if not parts:
        return ("", "", "", "")
    if len(parts) == 1:
        return ("", "", parts[0], "")
    suffixes = {"Jr", "Jr.", "Sr", "Sr.", "II", "III", "IV", "PhD", "MD", "Ph.D.", "M.D."}
    suffix = ""
    if parts[-1] in suffixes:
        suffix = parts.pop()
    first = parts[0]
    last = parts[-1]
    middle = " ".join(parts[1:-1])
    return (first, middle, last, suffix)


class SQLParser(BaseParser):
    """Insert SCT officer compensation into SQL Server via stored procedures (gated)."""

    def __init__(self, db, logger_name=None):
        super(SQLParser, self).__init__(db, logger_name)
        self.gate = SPGate(db, self.logger)

    def run(self):
        result = {
            'companies_processed': 0,
            'officers_inserted': 0,
            'officers_already_exist': 0,
            'failed': 0,
        }

        sct_path = sct_parsed_path()
        if not os.path.exists(sct_path):
            self.logger.warning("No SCT parsed CSV at %s — nothing to process", sct_path)
            return result

        sct_df = pd.read_csv(sct_path)
        parsed_companies = sct_df[sct_df['SCT_Parsed'] == 'Parsed']['CompanyName'].tolist()
        if not parsed_companies:
            self.logger.info("No parsed companies in SCT output — nothing to process")
            return result

        # Locate L3 files for these companies
        base = os.path.join(os.path.dirname(os.path.dirname(get_filing_dir('SCT_filings_dump'))))
        all_l3 = glob.glob(os.path.join(base, '**', '*_cleaned_L3*'), recursive=True)
        if not all_l3:
            # Fallback for old layout — current production puts CSVs under logs/<year>/filing_dump/
            all_l3 = glob.glob(os.path.join('logs', '**', 'filing_dump', '**', '*_cleaned_L3*'), recursive=True)

        l3_files = []
        for f in all_l3:
            basename = os.path.basename(f).replace('_cleaned_L3_table.csv', '').strip()
            for comp in parsed_companies:
                if basename.lower() == comp.lower() or basename.lower().replace('_', ' ') == comp.lower():
                    l3_files.append((f, comp))
                    break

        self.logger.info("Found %d L3 files to process", len(l3_files))

        for f_path, company_name in l3_files:
            try:
                result['companies_processed'] += 1
                self.report_progress(processed=result['companies_processed'],
                                     parsed=result['officers_inserted'],
                                     failed=result['failed'])
                self.logger.info("[%d/%d] %s", result['companies_processed'], len(l3_files), company_name)

                ok = self._process_one_company(f_path, company_name, result)
                if not ok:
                    result['failed'] += 1
            except Exception as e:
                result['failed'] += 1
                self.logger.error("  Error processing %s: %s", os.path.basename(f_path), e, exc_info=True)

        self.logger.info("SQL parse complete: %s | Gate summary: %s", result, self.gate.summary())
        return result

    # ------------------------------------------------------------------
    # Per-company processing
    # ------------------------------------------------------------------

    def _process_one_company(self, f_path, company_name, result):
        """Returns True if anything was processed, False if file unusable."""
        df = self._load_l3(f_path)
        if df is None:
            return False

        # Identify columns
        all_cols = [str(c) for c in df.columns]
        name_col = _find_column(all_cols, ['name', 'principal', 'executive']) or (all_cols[0] if all_cols else None)
        if name_col is None:
            return False

        year_col = _find_column(all_cols, ['year', 'fiscal'])
        salary_col = _find_column(all_cols, ['salary'])
        bonus_col = _find_column(all_cols, ['bonus'])
        stock_col = _find_column(all_cols, ['stock'])
        option_col = _find_column(all_cols, ['option'])
        non_eq_col = _find_column(all_cols, ['non-equity', 'nonequity', 'incentive plan'])
        pension_col = _find_column(all_cols, ['pension', 'change in', 'nqdc'])
        other_col = _find_column(all_cols, ['all other', 'other comp'])
        total_col = _find_column(all_cols, ['total'])
        desig_col = _find_column(all_cols, ['designation', 'title', 'position'])

        # Company_ID lookup (no auto-insert — Company table is server-managed)
        comp = self.db.fetch_one("SELECT Company_ID FROM Company WHERE CompanyName=?", [company_name])
        if not comp:
            comp = self.db.fetch_one(
                "SELECT TOP 1 Company_ID FROM Company WHERE CompanyName LIKE ?",
                ['%' + company_name.split()[0] + '%']
            )
        if not comp:
            self.logger.warning("  Company '%s' not in Company table — skipping (DBA must add it)", company_name)
            return False
        company_id = comp['Company_ID']

        officers_inserted = 0
        officers_skipped = 0
        fiscal_year_seen = None

        # SCT tables frequently split a multi-line "Name and Principal Position" cell
        # into separate rows. e.g. Blink Charging Co.'s L3 file:
        #     row 1: "Michael C. Battaglia(1)"          (real name + comp for FY2025)
        #     row 2: "President and Chief Executive"    (title line + comp for FY2024)
        #     row 3: "Officer"                          (title line + comp for FY2023)
        # All 3 rows belong to the SAME person. Rows 2-3 are title fragments AND
        # additional fiscal-year compensation rows.
        #
        # Strategy: walk rows in order, carry forward the last seen real name and
        # accumulate title fragments. When a fragment row is hit, attribute its
        # money to the last real name and append its text to the designation.

        _TITLE_RE = re.compile(
            r'^\s*('
            r'president|vice\s*president|svp|evp|chief|officer|executive|'
            r'former|interim|director|chairman|chair|secretary|treasurer|'
            r'general\s*counsel|operating|financial|operations|technology|'
            r'commercial|strategy|legal|administrative|principal|managing|'
            r'senior|head\s+of|controller|cfo|ceo|coo|cto|cmo|cio|chro|'
            r'co\s*-?\s*founder|founder|board|member|'
            r'and\b|of\b|the\b|&|/|-|\s)+\s*$', re.I)

        def _is_title_fragment(s):
            if not s:
                return False
            stripped = re.sub(r'\([^\)]*\)', '', s).strip()
            return bool(_TITLE_RE.match(stripped))

        # Pass 1: derive each officer block's full designation text by walking
        # the rows in order. Map real_name -> joined designation.
        block_designation = {}
        _cur_name = None
        _cur_title = []
        for _, row in df.iterrows():
            nm = str(row.get(name_col, '')).strip() if name_col else ''
            if not nm or len(nm) < 3:
                continue
            low = nm.lower()
            if any(s in low for s in
                   ['total', 'name and', 'principal position', '---', 'salary', 'compensation']):
                continue
            if _is_title_fragment(nm):
                if _cur_name:
                    _cur_title.append(nm)
                    block_designation[_cur_name] = ' '.join(_cur_title).strip()
            else:
                _cur_name = nm
                _cur_title = []
                block_designation.setdefault(_cur_name, '')

        # Pass 2: insert rows. Title-fragment rows get rewritten to use the real
        # owner's name + the block's accumulated designation.
        last_real_name = None
        for _, row in df.iterrows():
            officer_name = str(row.get(name_col, '')).strip() if name_col else ''
            if not officer_name or len(officer_name) < 3:
                continue
            lower_name = officer_name.lower()
            if any(skip in lower_name for skip in
                   ['total', 'name and', 'principal position', '---', 'salary', 'compensation']):
                continue
            if _is_title_fragment(officer_name):
                if not last_real_name:
                    self.logger.debug("  [TITLE-LEAD] '%s' has no preceding officer — skipped", officer_name)
                    continue
                officer_name = last_real_name
            else:
                last_real_name = officer_name

            # Fiscal year
            fy = None
            if year_col:
                try:
                    fy = int(float(str(row.get(year_col, '')).strip()))
                except (ValueError, TypeError):
                    fy = None
            if not fy:
                # Fall back to most-recent FY from Maya_Parsing_Summary
                mps = self.db.fetch_one(
                    "SELECT TOP 1 FiscalYear FROM Maya_Parsing_Summary "
                    "WHERE Company_ID=? ORDER BY Parsed_Date DESC",
                    [company_id]
                )
                fy = mps['FiscalYear'] if mps and mps.get('FiscalYear') else datetime.now().year - 1
            if fiscal_year_seen is None:
                fiscal_year_seen = fy

            salary = _clean_money(row.get(salary_col)) if salary_col else 0
            bonus = _clean_money(row.get(bonus_col)) if bonus_col else 0
            stock = _clean_money(row.get(stock_col)) if stock_col else 0
            options = _clean_money(row.get(option_col)) if option_col else 0
            non_eq = _clean_money(row.get(non_eq_col)) if non_eq_col else 0
            pension = _clean_money(row.get(pension_col)) if pension_col else 0
            all_other = _clean_money(row.get(other_col)) if other_col else 0
            total = _clean_money(row.get(total_col)) if total_col else 0

            if salary == 0 and bonus == 0 and stock == 0 and total == 0:
                continue  # junk row

            # Designation priority:
            #   1. an explicit designation column on the same row (rare in real SCT tables)
            #   2. block_designation from pass-1 multi-line title accumulation
            #   3. empty (SP will write '' / SC_Tag stays unset)
            designation = str(row.get(desig_col, '')).strip() if desig_col else ''
            if not designation:
                designation = block_designation.get(officer_name, '').strip()
            scope = "{} FY{} {}".format(company_name, fy, officer_name)

            # --- SP 1: sp_wk_SummaryComp_IU_MAYA (18 params) ---
            # Per docs/SP_Behavior_Analysis.md §2 — gate at (Company_ID + FiscalYear + OfficerName)
            sp1_status = self.gate.call_if_absent(
                exists_sql=(
                    "SELECT 1 FROM wk_SummaryComp "
                    "WHERE Company_ID=? AND FiscalYear=? AND OfficerName=?"
                ),
                exists_params=[company_id, fy, officer_name],
                sp_name="sp_wk_SummaryComp_IU_MAYA",
                sp_params=[
                    None,            # @Officer_ID (NULL → SP will lookup/create)
                    officer_name,    # @ParsedName
                    officer_name,    # @OfficerName
                    fy,              # @FiscalYear
                    salary,          # @Salary
                    bonus,           # @Bonus
                    stock,           # @Stock_Award
                    options,         # @Option_Awards
                    non_eq,          # @Non_Eq_Incentive_Plan_Comp
                    pension,         # @Chg_PensionValue_NQDC_Earnings
                    0,               # @Chg_Retention_Plan_Value
                    all_other,       # @All_Other
                    total,           # @Total
                    designation or 'MAYA',  # @TagName
                    company_id,      # @Company_ID
                    datetime.now(),  # @CreateDate
                    'MAYA',          # @CreatedBy
                    None,            # @Role_ID1
                ],
                scope_label="SCT-wk:" + scope,
            )

            if sp1_status == STATUS_ALREADY_EXIST:
                officers_skipped += 1
                continue
            if sp1_status == STATUS_NOT_PARSED:
                continue

            # --- SP 2: sp_wk_SummaryComp_U_MAYA (16 params) — creates Officer ---
            # Gate at (Company_ID + FiscalYear + OfficerName) on Officer table
            wk = self.db.fetch_one(
                "SELECT TOP 1 ID, Officer_ID FROM wk_SummaryComp "
                "WHERE Company_ID=? AND FiscalYear=? AND OfficerName=? ORDER BY ID DESC",
                [company_id, fy, officer_name]
            )
            wk_id = wk['ID'] if wk else None
            wk_officer_id = wk['Officer_ID'] if wk else None

            self.gate.call_if_absent(
                exists_sql=(
                    "SELECT 1 FROM Officer "
                    "WHERE Company_ID=? AND FiscalYear=? AND OfficerName=?"
                ),
                exists_params=[company_id, fy, officer_name],
                sp_name="sp_wk_SummaryComp_U_MAYA",
                sp_params=[
                    wk_id,           # @ID (wk_SummaryComp row ID)
                    designation or 'MAYA',  # @TagName
                    None,            # @Last_Officer_ID
                    wk_officer_id,   # @Officer_ID
                    company_id,      # @Company_ID
                    fy,              # @FiscalYear
                    officer_name,    # @OfficerName
                    salary,          # @Salary
                    bonus,           # @Bonus
                    stock,           # @Stock_Award
                    options,         # @Option_Awards
                    non_eq,          # @Non_Eq_Incentive_Plan_Comp
                    pension,         # @Chg_PensionValue_NQDC_Earnings
                    all_other,       # @All_Other
                    total,           # @Total
                    'MAYA',          # @UserID
                ],
                scope_label="SCT-officer:" + scope,
            )

            # --- SP 3: sp_Officer_FirstLastName_U_MAYA (10 params) ---
            officer_row = self.db.fetch_one(
                "SELECT TOP 1 Officer_ID, First_Name, Last_Name FROM Officer "
                "WHERE Company_ID=? AND FiscalYear=? AND OfficerName=?",
                [company_id, fy, officer_name]
            )
            if officer_row and not (officer_row.get('First_Name') and officer_row.get('Last_Name')):
                first, middle, last, suffix = _split_name(officer_name)
                self.gate.call_if_absent(
                    exists_sql=(
                        "SELECT 1 FROM Officer "
                        "WHERE Officer_ID=? AND First_Name IS NOT NULL AND Last_Name IS NOT NULL"
                    ),
                    exists_params=[officer_row['Officer_ID']],
                    sp_name="sp_Officer_FirstLastName_U_MAYA",
                    sp_params=[
                        officer_row['Officer_ID'],  # @Officer_ID
                        company_id,                 # @Company_ID
                        fy,                         # @FiscalYear
                        officer_name,               # @OfficerName
                        first,                      # @First_Name
                        middle,                     # @Middle_Name
                        last,                       # @Last_Name
                        suffix,                     # @Suffix
                        '',                         # @Prefix
                        'MAYA',                     # @UserID
                    ],
                    scope_label="SCT-name:" + scope,
                )

            officers_inserted += 1

        result['officers_inserted'] += officers_inserted
        result['officers_already_exist'] += officers_skipped

        # --- SP 5: sp_Tracking_Data_Entry_U_MAYA (9 params) — once per company ---
        if officers_inserted > 0 and fiscal_year_seen:
            self.gate.call_if_absent(
                exists_sql=(
                    "SELECT 1 FROM Tracking_Data_Entry "
                    "WHERE Company_ID=? AND FiscalYear=? AND Perquisites_entered_Name IS NOT NULL"
                ),
                exists_params=[company_id, fiscal_year_seen],
                sp_name="sp_Tracking_Data_Entry_U_MAYA",
                sp_params=[
                    int(company_id),
                    int(fiscal_year_seen),
                    'SCT',
                    'DataEntry',
                    None,
                    None,
                    None,
                    None,
                    'SCT',
                ],
                scope_label="SCT-track:" + company_name,
            )

        self.logger.info("  %s: inserted=%d, skipped(already-exist)=%d",
                         company_name, officers_inserted, officers_skipped)
        return officers_inserted > 0 or officers_skipped > 0

    # ------------------------------------------------------------------
    # L3 CSV loader (header detection)
    # ------------------------------------------------------------------

    def _load_l3(self, f_path):
        df = pd.read_csv(f_path)
        if df.empty or len(df) < 2:
            return None
        cols = list(df.columns)
        if all(str(c).replace('.', '').isdigit() for c in cols):
            # Numeric headers — search for the real header row
            for try_row in range(min(10, len(df))):
                header_row = df.iloc[try_row].fillna('')
                all_text = ' '.join(str(v).lower().strip().replace('\n', ' ') for v in header_row)
                has_name = 'name' in all_text
                has_salary = 'salary' in all_text
                has_year = 'year' in all_text
                has_principal = 'principal' in all_text or 'position' in all_text
                if (has_name and has_principal) or (has_name and has_salary) or (has_salary and has_year):
                    new_cols = []
                    for i, v in enumerate(header_row):
                        col_name = str(v).strip()
                        if not col_name or col_name in new_cols:
                            col_name = 'col_{}'.format(i)
                        new_cols.append(col_name)
                    df.columns = new_cols
                    df = df.iloc[try_row + 1:].reset_index(drop=True)
                    break
            else:
                return None
        # Dedupe column names
        seen, unique_cols = {}, []
        for c in df.columns:
            c_str = str(c)
            if c_str in seen:
                seen[c_str] += 1
                unique_cols.append('{}_{}'.format(c_str, seen[c_str]))
            else:
                seen[c_str] = 0
                unique_cols.append(c_str)
        df.columns = unique_cols
        return df
