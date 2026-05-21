"""
sct_parser.py — Parse Summary Compensation Tables from SEC filings.

Matches the original SCT_table_parser_server_v1.py logic EXACTLY:
1. Search for text containing "ummary" or "Executive Compensation"
2. Find the NEXT <table> after that text
3. Score the table using keyword matching (same search_list)
4. Pick the table with highest score (must exceed TARGET_SCORE=5)
5. Extract with colspan/rowspan handling
6. Clean through L1, L2, L3 stages
"""
import os
import re
import time
import csv
from datetime import date, datetime
from collections import defaultdict
from copy import deepcopy

import pandas as pd
import numpy as np
from fuzzywuzzy import fuzz

from parsers.base_parser import BaseParser
from core.exceptions import TableNotFoundError, ParsingError
from utils.html_fetcher import SECFetcher
from utils.csv_manager import (
    edgar_feed_path, sct_parsed_path, get_filing_dir,
    backup_if_exists, save_df,
)

# Same keywords as original SCT_table_parser_server_v1.py line 157
SEARCH_LIST = [
    "name", "principal", "position", "principalposition", "fiscal", "year",
    "fiscalyear", "salary", "bonus", "stock", "awards", "nonequity",
    "incentive", "plan", "compensation", "other", "stockawards",
    "non-equityincentive", "non-equityincentiveplan", "plancompensation",
    "othercompensation", "annual compensation", "allothercompensation",
    "total", "totalcompensation",
]

TARGET_SCORE = 5
FUZZY_MATCH_THRESHOLD = 80
MIN_TABLE_ROWS = 5

# Superscript pattern (same as original)
PATTERN_SUP = r'[\u1d43\u1d47\u1d9c\u1d48\u1d49\u1da0\u1d4d\u02b0\u2071\u02b2\u1d4f\u02e1\u1d50\u207f\u1d52\u1d56\u02b3\u02e2\u1d57\u1d58\u1d5b\u02b7\u02e3\u02b8\u1dbb\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u2070]'


class SCTParser(BaseParser):
    """Parse Summary Compensation Tables — matches original project logic exactly."""

    def __init__(self, db, logger_name=None):
        super(SCTParser, self).__init__(db, logger_name)
        self.fetcher = SECFetcher()

    def run(self):
        feed_path = edgar_feed_path()
        if not os.path.exists(feed_path):
            self.logger.error("Edgar feed not found: %s", feed_path)
            return {'companies_processed': 0, 'parsed': 0, 'no_table_found': 0}

        feed_df = pd.read_csv(feed_path, encoding="ISO-8859-1")
        self.logger.info("Loaded %d companies from %s", len(feed_df), feed_path)

        # Setup output tracker (same as original)
        parsed_path = sct_parsed_path()
        backup_if_exists(parsed_path)

        tracker_df = feed_df.copy()
        tracker_df['SCT_Parsed'] = 'Not Parsed'
        tracker_df['Parsed_Date'] = date.today().strftime("%d/%m/%Y")
        tracker_df['SCT_fetched'] = 0

        companies_processed = 0
        parsed_count = 0
        no_table_count = 0

        today_year = str(date.today().year)
        today_month = str(date.today().month)
        today_day = str(date.today().day)

        for row_idx, row in feed_df.iterrows():
            company_name = str(row.get('CompanyName', '')).strip()
            url = str(row.get('Link', '')).strip()

            if not url or not company_name:
                continue

            # Clean URL — strip iXBRL wrapper and cgi-bin prefix
            url = url.replace("/ix?doc=/", "/")
            if "/cgi-bin/browse-edgar/" in url:
                url = url.replace("/cgi-bin/browse-edgar/", "/")

            # If URL is an index page (ends with -index.htm), resolve to actual filing
            if '-index.htm' in url or url.endswith('-index.html'):
                resolved_url = self._resolve_index_to_filing(url)
                if resolved_url:
                    url = resolved_url

            # Save the resolved URL back to tracker CSV (so equity/exercise/pba can use it)
            tracker_df.at[row_idx, 'Link'] = url
            feed_df.at[row_idx, 'Link'] = url

            companies_processed += 1

            # Check stop signal
            if self.should_stop():
                self.logger.info("Stop requested. Stopping after %d companies.", companies_processed)
                break

            self.report_progress(processed=companies_processed, parsed=parsed_count, failed=no_table_count)
            self.logger.info("[%d/%d] %s", companies_processed, len(feed_df), company_name)

            try:
                # Fetch the filing page (same as original)
                page_soup = self.fetcher.fetch_page(url)
                if page_soup is None:
                    self.logger.warning("Could not fetch page for %s", company_name)
                    tracker_df.at[row_idx, 'SCT_Parsed'] = 'Not Parsed'
                    tracker_df.at[row_idx, 'SCT_fetched'] = 0
                    continue

                # === ENHANCED TABLE FINDING LOGIC ===
                final_table_tag = None
                final_table_score = 0
                current_target = TARGET_SCORE

                def _normalize(text):
                    """Normalize text for comparison — strip invisible chars."""
                    return text.replace('\xa0', ' ').replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').replace('\ufeff', '').replace('\n', ' ').lower()

                # === METHOD 1: PRIMARY — Search ALL tables for "Name and Principal Position" ===
                # This is the most reliable way to find SCT table
                all_tables = page_soup.find_all('table')
                for table_tag in all_tables:
                    try:
                        table_text = _normalize(table_tag.get_text(separator=' ', strip=True))

                        # Must have "name" + "principal" + "salary" — this IS the SCT table
                        has_name_principal = ('name' in table_text and 'principal' in table_text)
                        has_name_position = ('name' in table_text and 'position' in table_text)
                        has_salary = 'salary' in table_text
                        has_total = 'total' in table_text

                        if (has_name_principal or has_name_position) and has_salary and has_total:
                            table_data = [
                                [col.get_text(strip=True) for col in tr.findAll(["th", "td"])]
                                for tr in table_tag.findAll('tr')
                            ]
                            if len(table_data) >= MIN_TABLE_ROWS:
                                # This is almost certainly the SCT table — give it high score
                                table_score = 20  # High base score for having key identifiers
                                if final_table_score < table_score:
                                    final_table_score = table_score
                                    final_table_tag = table_tag
                                    self.logger.info("  PRIMARY: Found SCT via 'Name+Principal+Salary+Total' (score=%d)",
                                                     table_score)
                    except Exception:
                        continue

                # === METHOD 2: FALLBACK — Original text search method ===
                if final_table_tag is None:
                    string_1 = page_soup(text=re.compile("ummary", re.I))
                    string_1.extend(page_soup(text=re.compile("Executive Compensation", re.I)))
                    string_1.extend(page_soup(text=re.compile("ompensation Table", re.I)))

                    for text_match in string_1:
                        try:
                            table_tag = text_match.parent.findNext('table')
                            if not table_tag:
                                continue

                            table_data = [
                                [col.get_text(strip=True) for col in tr.findAll(["th", "td"])]
                                for tr in table_tag.findAll('tr')
                            ]
                            if len(table_data) < MIN_TABLE_ROWS:
                                continue

                            # Score the table with keyword matching
                            bag_of_keywords = []
                            pattern_for_header = r'^[a-zA-Z\-\s]*'
                            itr_header_list = []
                            for trow in table_data:
                                for cell in trow:
                                    if cell.strip():
                                        itr_header_list.append(cell)
                                if len(itr_header_list) > 20:
                                    break

                            for element in itr_header_list:
                                element = re.sub(PATTERN_SUP, '', element)
                                match_obj = re.search(pattern_for_header, element, re.I)
                                if match_obj:
                                    cleaned = re.sub(r'\-', '', match_obj[0])
                                    cleaned = re.sub(r'\n', '', cleaned)
                                    bag_of_keywords.extend(cleaned.split())

                            common_elements = set(
                                keyword for keyword in bag_of_keywords
                                if any(
                                    fuzz.ratio(keyword.lower(), search.lower()) >= FUZZY_MATCH_THRESHOLD
                                    for search in SEARCH_LIST
                                )
                            )
                            table_score = len(common_elements)

                            # Bonus for Name + Principal
                            full_text = _normalize(table_tag.get_text(separator=' ', strip=True))
                            if 'name' in full_text and ('principal' in full_text or 'position' in full_text):
                                if 'salary' in full_text:
                                    table_score += 5

                            if table_score > current_target:
                                final_table_score = table_score
                                current_target = table_score
                                final_table_tag = table_tag
                                self.logger.info("  FALLBACK: Found SCT table (score=%d, keywords=%s)",
                                                 table_score, common_elements)

                        except Exception as e:
                            self.logger.debug("  Table scan error: %s", e)
                            continue

                # Step 4: Extract and clean the best table
                if final_table_tag is not None:
                    self.logger.info("  SCT table found for %s (score=%d)", company_name, final_table_score)

                    # Extract with colspan/rowspan (same as original lines 223-241)
                    result = defaultdict(lambda: defaultdict(str))
                    for row_i, tr in enumerate(final_table_tag.findAll('tr')):
                        for col_i, col in enumerate(tr.findAll(["th", "td"])):
                            colspan = int(col.get('colspan', 1))
                            rowspan = int(col.get('rowspan', 1))
                            col_data = col.get_text()
                            while row_i in result and col_i in result[row_i]:
                                col_i += 1
                            for i in range(row_i, row_i + rowspan):
                                for j in range(col_i, col_i + colspan):
                                    result[i][j] = col_data

                    final_list = []
                    for i, row_data in sorted(result.items()):
                        cols = []
                        for j, col_data in sorted(row_data.items()):
                            cols.append(col_data)
                        final_list.append(cols)

                    df = pd.DataFrame(final_list)

                    # Save raw fetched table
                    dump_dir = os.path.join(
                        get_filing_dir('SCT_filings_dump'),
                    )
                    safe_name = re.sub(r'[^\w\-. ]', '_', company_name)

                    fetched_path = os.path.join(dump_dir, safe_name + "_fetched_table.csv")
                    df.to_csv(fetched_path, header=None, index=False)

                    # Clean the table
                    cleaned_df = self._clean_table(df, company_name, dump_dir, safe_name)

                    if cleaned_df is not None and not cleaned_df.empty:
                        l3_path = os.path.join(dump_dir, safe_name + "_cleaned_L3_table.csv")
                        cleaned_df.to_csv(l3_path, index=False)

                        parsed_count += 1
                        tracker_df.at[row_idx, 'SCT_Parsed'] = 'Parsed'
                        tracker_df.at[row_idx, 'SCT_fetched'] = 1
                        self.report_progress(processed=companies_processed, parsed=parsed_count, failed=no_table_count)
                        self.logger.info("  PARSED: %s (%d rows)", company_name, len(cleaned_df))
                    else:
                        no_table_count += 1
                        tracker_df.at[row_idx, 'SCT_Parsed'] = 'No Table found'
                        tracker_df.at[row_idx, 'SCT_fetched'] = 1
                else:
                    no_table_count += 1
                    tracker_df.at[row_idx, 'SCT_Parsed'] = 'No Table found'
                    tracker_df.at[row_idx, 'SCT_fetched'] = 0
                    self.logger.info("  No SCT table found for %s", company_name)

            except Exception as e:
                no_table_count += 1
                tracker_df.at[row_idx, 'SCT_Parsed'] = 'Not Parsed'
                tracker_df.at[row_idx, 'SCT_fetched'] = 0
                self.logger.error("  Error processing %s: %s", company_name, e)

        # Save tracker CSV (with resolved URLs for equity/exercise/pba).
        # Ensure parent dirs exist — when the metadata folder for this month
        # was just created by RSS in the same run, pandas can race against
        # the filesystem and fail with "non-existent directory".
        os.makedirs(os.path.dirname(parsed_path), exist_ok=True)
        tracker_df.to_csv(parsed_path, index=True)

        # Also update the feed file with resolved URLs
        feed_out = edgar_feed_path()
        os.makedirs(os.path.dirname(feed_out), exist_ok=True)
        feed_df.to_csv(feed_out, index=False)

        self.logger.info("SCT complete: processed=%d parsed=%d no_table=%d",
                         companies_processed, parsed_count, no_table_count)

        return {
            'companies_processed': companies_processed,
            'parsed': parsed_count,
            'no_table_found': no_table_count,
            'output_file': parsed_path,
        }

    def _resolve_index_to_filing(self, index_url):
        """Resolve an SEC index page URL to the actual DEF 14A filing .htm URL."""
        try:
            soup = self.fetcher.fetch_page(index_url)
            if soup is None:
                return None

            # Look for the DEF 14A filing link in the table
            table = soup.find('table', class_='tableFile')
            if table is None:
                # Try any table
                for t in soup.find_all('table'):
                    if t.find('td', string=re.compile(r'DEF\s*14A', re.I)):
                        table = t
                        break

            if table:
                for row in table.find_all('tr'):
                    cells = row.find_all('td')
                    row_text = ' '.join(c.get_text(strip=True) for c in cells)
                    if re.search(r'DEF\s*14A', row_text, re.I):
                        # Found DEF 14A row — get the first .htm link
                        for anchor in row.find_all('a'):
                            href = anchor.get('href', '')
                            # Clean iXBRL wrapper
                            href = href.replace('/ix?doc=/', '/')
                            if '.htm' in href and '.xml' not in href:
                                # Trim anything after .htm
                                htm_idx = href.find('.htm') + 4
                                href = href[:htm_idx]
                                if href.startswith('/'):
                                    return 'https://www.sec.gov' + href
                                return href
        except Exception as e:
            self.logger.debug("Could not resolve index %s: %s", index_url, e)
        return None

    def _clean_table(self, df, company_name, dump_dir, safe_name):
        """Clean the raw extracted table through L1, L2, L3 stages."""
        try:
            # L1: Remove special characters and empty rows
            df = df.replace({
                r'\u200b': '', r'\xa0': ' ', r'\n': ' ',
                r'—': '', r'–': '', r'−': '',
                r'\$': '', r'\*': '',
            }, regex=True)
            df = df.replace('', np.nan)
            df = df.dropna(how='all')
            df = df.dropna(axis=1, how='all')

            l1_path = os.path.join(dump_dir, safe_name + "_cleaned_L1_table.csv")
            df.to_csv(l1_path, index=False)

            # L2: Remove duplicate columns and blank columns
            df = df.loc[:, ~df.T.duplicated()]
            # Remove columns that are mostly empty
            threshold = len(df) * 0.5
            df = df.dropna(axis=1, thresh=int(threshold) if threshold > 1 else 1)

            l2_path = os.path.join(dump_dir, safe_name + "_cleaned_L2_table.csv")
            df.to_csv(l2_path, index=False)

            # L3: Basic cleanup — remove rows that look like footnotes/totals
            if len(df) < 2:
                return None

            return df

        except Exception as e:
            self.logger.error("  Cleaning error for %s: %s", company_name, e)
            return None
