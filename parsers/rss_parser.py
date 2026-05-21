"""
rss_parser.py
Pipeline Step 1 -- Fetch and parse the SEC EDGAR full-text-search RSS feed
for DEF 14A filings, resolve each entry to its actual filing URL, and
persist results to the edgar_feed CSV and the database.
"""

import re
import time
from datetime import datetime

import pandas as pd

from config import (
    SEC_BASE_URL,
    SEC_REQUEST_DELAY,
    SEC_RSS_PAGES,
)
from core.exceptions import ParsingError, SECFetchError
from parsers.base_parser import BaseParser
from utils.csv_manager import (
    edgar_feed_path,
    out_of_bound_path,
    backup_if_exists,
    save_df,
)
from utils.html_fetcher import SECFetcher

# Number of entries per RSS page on EDGAR full-text search
_RSS_PAGE_SIZE = 100

# Regex helpers — CIK can be any digits inside parens
_CIK_RE = re.compile(r"\((\d+)\)")
_NAME_RE = re.compile(r"14A\s*-?\s*(.+?)\s*\(")


class RSSParser(BaseParser):
    """Fetch the SEC EDGAR RSS feed for DEF 14A filings and catalogue them.

    For every filing entry the parser:
      * extracts CIK, company name, filing date, and index-page link
      * resolves the actual ``.htm`` DEF 14A document URL
      * extracts the fiscal-year-end date from the EDGAR company header
      * checks whether the company exists in the ``Company`` table
      * skips duplicates already present in ``Maya_Parsing_Summary``
      * writes in-scope rows to the *edgar_feed* CSV and out-of-scope
        rows to a separate CSV

    Returns
    -------
    dict
        ``{'companies_found': N, 'companies_saved': M,
        'out_of_scope': K, 'feed_file': path}``
    """

    def __init__(self, db, fetcher=None, logger_name=None):
        """
        Parameters
        ----------
        db : core.database.DatabaseManager
        fetcher : utils.html_fetcher.SECFetcher, optional
            Reusable fetcher instance; one is created when omitted.
        logger_name : str, optional
        """
        super(RSSParser, self).__init__(db, logger_name)
        self.fetcher = fetcher or SECFetcher()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self):
        """Execute the RSS parsing pipeline step."""
        self.logger.info("Starting RSS feed parsing (%d pages)", SEC_RSS_PAGES)

        entries = self._fetch_all_feed_entries()
        self.logger.info("Total RSS entries fetched: %d", len(entries))

        in_scope_rows = []
        out_of_scope_rows = []
        duplicates = 0

        for entry in entries:
            # Check stop signal
            if self.should_stop():
                self.logger.info("Stop requested. Stopping RSS after %d entries.", len(in_scope_rows))
                break

            parsed = self._parse_entry(entry)
            if parsed is None:
                continue

            company_name = parsed["CompanyName"]
            cik = parsed["CIK"]
            index_link = parsed["Link"]

            # --- duplicate check ---
            if self.check_already_parsed(index_link):
                self.logger.debug(
                    "Skipping already-parsed link: %s", index_link
                )
                duplicates += 1
                continue

            # --- fiscal year = filing year - 1 (no need to resolve URL here) ---
            # The SCT parser will fetch the actual filing page later
            # Just use the RSS feed link directly — saves 2 seconds per company
            try:
                filing_year = int(parsed["Filing_Date"][:4])
                parsed["FiscalYear"] = filing_year - 1
            except (ValueError, TypeError):
                self.logger.warning(
                    "Could not derive fiscal year for %s", company_name
                )
                parsed["FiscalYear"] = None

            # --- scope check: does this CIK exist in our Company table? ---
            company_row = self.get_company_by_cik(cik)
            if company_row is not None:
                parsed["Company_ID"] = company_row["Company_ID"]
                # Update company name from DB (same as old project)
                parsed["CompanyName"] = company_row.get("CompanyName", company_name)
                in_scope_rows.append(parsed)
            else:
                # Company not in DB — out of scope (same as old project)
                out_of_scope_rows.append(parsed)
                self.logger.debug(
                    "Out-of-scope: %s (CIK %s) — not in Company table",
                    company_name, cik,
                )
                continue
            self.report_progress(
                processed=len(in_scope_rows) + len(out_of_scope_rows) + duplicates,
                parsed=len(in_scope_rows),
                failed=len(out_of_scope_rows),
            )
            self.logger.info(
                "Added: %s (CIK %s)", company_name, cik
            )

        # --- persist CSVs ---
        feed_file = self._save_results(in_scope_rows, out_of_scope_rows)

        result = {
            "companies_found": len(entries),
            "companies_saved": len(in_scope_rows),
            "out_of_scope": len(out_of_scope_rows),
            "duplicates_skipped": duplicates,
            "feed_file": feed_file,
        }
        self.logger.info(
            "RSS parsing complete. found=%d  saved=%d  out_of_scope=%d  "
            "duplicates=%d",
            result["companies_found"],
            result["companies_saved"],
            result["out_of_scope"],
            result["duplicates_skipped"],
        )
        return result

    # ------------------------------------------------------------------
    # Feed fetching
    # ------------------------------------------------------------------

    def _fetch_all_feed_entries(self):
        """Fetch *SEC_RSS_PAGES* pages from the EDGAR full-text search RSS.

        Each page contains up to 100 entries.  Start offsets are
        ``0, 100, 200, ...``.
        """
        all_entries = []
        for page_idx in range(SEC_RSS_PAGES):
            start = page_idx * _RSS_PAGE_SIZE
            # Must match original project's URL exactly
            url = (
                "https://www.sec.gov/cgi-bin/browse-edgar"
                "?action=getcurrent&type=def%2014A&company="
                "&dateb=&owner=include&count={count}"
                "&start={start}&output=atom"
            ).format(
                count=_RSS_PAGE_SIZE,
                start=start,
            )
            self.logger.info(
                "Fetching RSS page %d/%d (start=%d)",
                page_idx + 1,
                SEC_RSS_PAGES,
                start,
            )
            try:
                soup = self.fetcher.fetch_xml(url)
            except Exception as exc:
                raise SECFetchError(
                    "Failed to fetch RSS page {}: {}".format(
                        page_idx + 1, exc
                    )
                )

            entries = soup.find_all("entry")
            self.logger.info(
                "  Page %d: %d entries", page_idx + 1, len(entries)
            )
            all_entries.extend(entries)

            if page_idx < SEC_RSS_PAGES - 1:
                time.sleep(SEC_REQUEST_DELAY)

        return all_entries

    # ------------------------------------------------------------------
    # Entry parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_entry(entry):
        """Extract structured fields from a single RSS ``<entry>`` tag.

        Returns
        -------
        dict or None
            Keys: CompanyName, CIK, Link, Filing_Date, Filing_Type,
            fiscalendyear.  Returns ``None`` when extraction fails.
        """
        title_tag = entry.find("title")
        if title_tag is None:
            return None
        title_text = title_tag.get_text(strip=True)

        # CIK is the 10-digit number inside parentheses
        cik_match = _CIK_RE.search(title_text)
        if cik_match is None:
            return None
        cik = cik_match.group(1)

        # Company name sits between "14A" (or variant) and the opening "("
        name_match = _NAME_RE.search(title_text)
        company_name = name_match.group(1).strip() if name_match else ""

        # Link from <link> tag
        link_tag = entry.find("link")
        link = link_tag.get("href", "") if link_tag else ""

        # Filing date is at character positions 16-26 inside <summary>
        summary_tag = entry.find("summary")
        filing_date = ""
        if summary_tag:
            summary_text = summary_tag.get_text()
            if len(summary_text) >= 26:
                filing_date = summary_text[16:26]

        return {
            "CompanyName": company_name,
            "CIK": cik,
            "Link": link,
            "Filing_Date": filing_date,
            "Filing_Type": "DEF 14A",
            "fiscalendyear": "",
            "FiscalYear": None,
        }

    # ------------------------------------------------------------------
    # Filing resolution
    # ------------------------------------------------------------------

    def _resolve_filing(self, index_url):
        """Follow the EDGAR index page to find the actual DEF 14A .htm URL
        and the fiscal-year-end date.

        Parameters
        ----------
        index_url : str
            URL of the filing index page.

        Returns
        -------
        tuple(str or None, str or None)
            ``(filing_url, fiscal_year_end)``
        """
        filing_url = None
        fiscal_end = None

        try:
            soup = self.fetcher.fetch_page(index_url)
        except Exception as exc:
            self.logger.warning(
                "Could not fetch index page %s: %s", index_url, exc
            )
            return filing_url, fiscal_end

        time.sleep(SEC_REQUEST_DELAY)

        # --- extract fiscal year end from companyInfo div ---
        company_info = soup.find("div", {"id": "companyInfo"})
        if company_info is None:
            company_info = soup.find("div", class_="companyInfo")
        if company_info:
            info_text = company_info.get_text()
            fye_match = re.search(
                r"Fiscal\s+Year\s+End:\s*(\d{4})", info_text
            )
            if fye_match:
                fiscal_end = fye_match.group(1)

        # --- find the actual DEF 14A .htm document link ---
        table = soup.find("table", class_="tableFile")
        if table is None:
            tables = soup.find_all("table")
            for t in tables:
                if t.find("td", string=re.compile(r"DEF\s*14A", re.I)):
                    table = t
                    break

        if table:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue
                doc_type = cells[3].get_text(strip=True)
                if re.match(r"DEF\s*14A", doc_type, re.I):
                    anchor = cells[2].find("a") if len(cells) > 2 else None
                    if anchor is None:
                        anchor = row.find("a")
                    if anchor:
                        href = anchor.get("href", "")
                        if href.lower().endswith(".htm") or href.lower().endswith(".html"):
                            if href.startswith("/"):
                                filing_url = SEC_BASE_URL + href
                            else:
                                filing_url = href
                            break

        return filing_url, fiscal_end

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_results(self, in_scope_rows, out_of_scope_rows):
        """Write in-scope and out-of-scope rows to their respective CSVs.

        Returns
        -------
        str
            Path to the saved edgar-feed CSV file.
        """
        columns = [
            "CompanyName",
            "FiscalYear",
            "Filing_Date",
            "Filing_Type",
            "Link",
            "fiscalendyear",
        ]

        feed_path = edgar_feed_path()
        backup_if_exists(feed_path)

        if in_scope_rows:
            df_in = pd.DataFrame(in_scope_rows)
            # Keep only the columns we persist in the CSV
            for col in columns:
                if col not in df_in.columns:
                    df_in[col] = ""
            save_df(df_in[columns], feed_path)
            self.logger.info(
                "Saved %d in-scope rows to %s", len(in_scope_rows), feed_path
            )
        else:
            # Write an empty CSV with the correct header
            save_df(pd.DataFrame(columns=columns), feed_path)
            self.logger.info("No in-scope rows; wrote empty feed CSV.")

        if out_of_scope_rows:
            oob_path = out_of_bound_path()
            backup_if_exists(oob_path)
            df_out = pd.DataFrame(out_of_scope_rows)
            for col in columns:
                if col not in df_out.columns:
                    df_out[col] = ""
            save_df(df_out[columns], oob_path)
            self.logger.info(
                "Saved %d out-of-scope rows to %s",
                len(out_of_scope_rows),
                oob_path,
            )

        return feed_path
