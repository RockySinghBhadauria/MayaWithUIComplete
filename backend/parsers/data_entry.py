"""
data_entry.py
Inserts company metadata from the edgar_feed CSV into the
Maya_Parsing_Summary database table.

Ported from Maya_parsing_data_entry.py (146 lines).
"""

import os

from parsers.base_parser import BaseParser
from utils.csv_manager import edgar_feed_path, sct_parsed_path, load_df


class DataEntryParser(BaseParser):
    """Inserts company filing metadata into Maya_Parsing_Summary."""

    def __init__(self, db):
        """
        Parameters
        ----------
        db : core.database.DatabaseManager
        """
        super(DataEntryParser, self).__init__(db, logger_name='DataEntryParser')

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self):
        """Read the edgar_feed CSV and insert rows into Maya_Parsing_Summary.

        For each company in the feed:
        1. Look up the Company table by CompanyName to retrieve metadata
           (Company_ID, CIK, Symbol, Fortune_1000, Russell_3000, etc.).
        2. Skip if the filing Link already exists in Maya_Parsing_Summary.
        3. INSERT the row with ``SCT_Parsed='Not Parsed'`` and
           ``ProcessingType='Automatic'``.

        Returns
        -------
        dict
            Summary with keys ``companies_processed``, ``inserted``,
            and ``skipped_duplicates``.
        """
        feed_path = edgar_feed_path()
        if not os.path.exists(feed_path):
            self.logger.error('Edgar feed not found: %s', feed_path)
            return {
                'companies_processed': 0,
                'inserted': 0,
                'skipped_duplicates': 0,
            }

        feed_df = load_df(feed_path)
        self.logger.info(
            'Loaded edgar feed with %d entries from %s',
            len(feed_df), feed_path,
        )

        # Also load SCT parsed results if available (to get SCT_Parsed status)
        sct_path = sct_parsed_path()
        sct_status = {}
        if os.path.exists(sct_path):
            try:
                sct_df = load_df(sct_path)
                for _, srow in sct_df.iterrows():
                    name = str(srow.get('CompanyName', '')).strip()
                    if name:
                        sct_status[name] = {
                            'SCT_Parsed': str(srow.get('SCT_Parsed', 'Not Parsed')),
                            'Parsed_Date': str(srow.get('Parsed_Date', '')),
                        }
            except Exception:
                pass

        companies_processed = 0
        inserted = 0
        skipped_duplicates = 0

        for idx, row in feed_df.iterrows():
            company_name = str(row.get('CompanyName', '')).strip()
            link = str(row.get('Link', '')).strip()
            fiscal_year = row.get('FiscalYear', '')
            cik_from_feed = row.get('CIK', '')

            if not company_name or not link:
                self.logger.warning(
                    'Row %d: missing CompanyName or Link, skipping.', idx,
                )
                continue

            companies_processed += 1
            self.report_progress(processed=companies_processed, parsed=inserted, failed=skipped_duplicates)

            # --- Check for duplicate link --------------------------------
            # Match production behavior: write status='Already Exist' so the UI badge
            # + mailer + click app all recognize the skip as a successful outcome,
            # not a failure. (Production: SCT_module/maya_data_entry.py)
            if self.check_already_parsed(link):
                self.logger.debug(
                    'Link already in Maya_Parsing_Summary, marking Already Exist: %s', link,
                )
                try:
                    from datetime import datetime as _dt
                    self.db.execute(
                        "UPDATE Maya_Parsing_Summary "
                        "SET SCT_Parsed = 'Already Exist', Parsed_Date = ? "
                        "WHERE Link = ?",
                        [_dt.now().strftime('%Y-%m-%d'), link],
                    )
                    self.db.commit()
                except Exception as _e:
                    self.logger.warning("Could not update Already Exist status for %s: %s", link, _e)
                skipped_duplicates += 1
                continue

            # --- Look up company metadata --------------------------------
            company_row = self._lookup_company(company_name, cik_from_feed)

            if company_row is None:
                # Auto-insert company (enhanced behavior)
                try:
                    from datetime import datetime as dt
                    cik_val = int(str(cik_from_feed).lstrip("0") or "0") if cik_from_feed else 0
                    self.db.execute(
                        "INSERT INTO Company (CompanyName, CIK, UpdateDate) VALUES (?, ?, ?)",
                        [company_name, cik_val, dt.now().isoformat()]
                    )
                    self.db.commit()
                    company_row = self._lookup_company(company_name, cik_from_feed)
                    self.logger.info("Auto-inserted company: %s", company_name)
                except Exception as e:
                    self.logger.warning("Could not auto-insert %s: %s", company_name, e)
                    continue
                if company_row is None:
                    continue

            # --- INSERT into Maya_Parsing_Summary ------------------------
            try:
                sct_info = sct_status.get(company_name, {})
                self._insert_row(company_row, link, fiscal_year, sct_info)
                inserted += 1
            except Exception as exc:
                self.logger.error(
                    'Failed to insert %s: %s', company_name, exc,
                    exc_info=True,
                )

        # Commit once after all inserts
        if inserted > 0:
            self.db.commit()
            self.logger.info('Committed %d new rows.', inserted)

        self.logger.info(
            'Data entry complete. Processed=%d, Inserted=%d, Skipped=%d',
            companies_processed, inserted, skipped_duplicates,
        )

        return {
            'companies_processed': companies_processed,
            'inserted': inserted,
            'skipped_duplicates': skipped_duplicates,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lookup_company(self, company_name, cik):
        """Look up company metadata, first by CIK then by name.

        Parameters
        ----------
        company_name : str
        cik : int or str

        Returns
        -------
        dict or None
            Company row dict with all metadata fields.
        """
        # Prefer CIK lookup (more reliable than name matching)
        if cik:
            try:
                row = self.get_company_by_cik(cik)
                if row is not None:
                    return row
            except (ValueError, TypeError):
                pass

        # Fall back to name lookup
        company_id = self.get_company_id(company_name)
        if company_id is not None:
            return self._fetch_company_by_name(company_name)

        return None

    def _fetch_company_by_name(self, company_name):
        """Fetch the full company row by CompanyName.

        Parameters
        ----------
        company_name : str

        Returns
        -------
        dict or None
        """
        return self.db.fetch_one(
            "SELECT Company_ID, CompanyName, CIK, Symbol, Fortune_1000, "
            "Russell_3000, MDG_Client, Peer_Of_An_MDG_Client, SP_400, "
            "SP_500, SP_600, PM_Client, Peer_of_PM_Client, Priority "
            "FROM Company WHERE CompanyName=? ORDER BY UpdateDate DESC",
            [company_name],
        )

    def _insert_row(self, company_row, link, fiscal_year, sct_info=None):
        """Insert a single row into Maya_Parsing_Summary. Matches production INSERT
        in SCT_module/maya_data_entry.py (includes DCT_Parsed)."""
        sct_info = sct_info or {}
        from datetime import datetime as dt
        self.db.execute(
            "INSERT INTO Maya_Parsing_Summary ("
            "  [Company_ID], [CompanyName], [FiscalYear], [CIK], [Symbol], "
            "  [Priority], [Fortune_1000], [Russell_3000], [MDG_Client], "
            "  [Peer_Of_An_MDG_Client], [SP_400], [SP_500], [SP_600], "
            "  [PM_Client], [Peer_of_PM_Client], "
            "  [FiledDate], [FilingType], [Link], "
            "  [SCT_Parsed], [DCT_Parsed], [Parsed_Date], [ProcessingType]"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                company_row.get('Company_ID'),
                company_row.get('CompanyName'),
                fiscal_year,
                company_row.get('CIK'),
                company_row.get('Symbol'),
                company_row.get('Priority'),
                company_row.get('Fortune_1000'),
                company_row.get('Russell_3000'),
                company_row.get('MDG_Client'),
                company_row.get('Peer_Of_An_MDG_Client'),
                company_row.get('SP_400'),
                company_row.get('SP_500'),
                company_row.get('SP_600'),
                company_row.get('PM_Client'),
                company_row.get('Peer_of_PM_Client'),
                dt.now().strftime('%Y-%m-%d'),
                'DEF 14A',
                link,
                sct_info.get('SCT_Parsed', 'Not Parsed'),
                sct_info.get('DCT_Parsed', None),
                sct_info.get('Parsed_Date', dt.now().strftime('%Y-%m-%d')),
                'Automatic',
            ],
        )
