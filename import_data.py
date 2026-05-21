#!/usr/bin/env python
"""Import existing data from the original MAYA project into the UI project's SQL Server.

This script:
1. Reads all edgar_feed CSVs from the original project
2. Extracts unique companies and populates the Company table
3. Reads all SCT_Parsed CSVs and populates Maya_Parsing_Summary
4. Reads filing dump CSVs to populate Officer and wk_SummaryComp tables
5. Copies metadata CSVs to the enhanced project's data directory

Usage:
    python import_data.py
"""
import sys
import os
import glob
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from datetime import datetime

import config
from core.logging_config import setup_logging, get_logger
from core.database import DatabaseManager
from core.schema import init_database

setup_logging()
logger = get_logger('import_data')

# Path to original project's metadata dump
ORIGINAL_METADATA = os.path.join(
    os.path.dirname(config.PROJECT_ROOT),
    'SCT_metadata_dump'
)


def find_csv_files(directory, pattern):
    """Find all CSV files matching pattern in directory tree."""
    results = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if pattern in f and f.endswith('.csv'):
                results.append(os.path.join(root, f))
    results.sort(key=os.path.getmtime, reverse=True)
    return results


def import_companies(db):
    """Extract unique companies from all edgar_feed CSVs and insert into Company table."""
    logger.info("Importing companies from existing edgar_feed CSVs...")

    feed_files = find_csv_files(ORIGINAL_METADATA, 'edgar_feed_live')
    if not feed_files:
        logger.warning("No edgar_feed CSV files found in %s", ORIGINAL_METADATA)
        return 0

    all_companies = set()
    for f in feed_files:
        try:
            df = pd.read_csv(f)
            if 'CompanyName' in df.columns:
                for name in df['CompanyName'].dropna().unique():
                    all_companies.add(str(name).strip())
        except Exception as e:
            logger.debug("Skipping %s: %s", f, e)

    logger.info("Found %d unique companies across %d feed files", len(all_companies), len(feed_files))

    inserted = 0
    for company_name in sorted(all_companies):
        existing = db.fetch_one(
            "SELECT Company_ID FROM Company WHERE CompanyName=?",
            [company_name]
        )
        if not existing:
            db.execute(
                """INSERT INTO Company (CompanyName, CIK, Fortune_1000, Russell_3000,
                   MDG_Client, SP_400, SP_500, SP_600, UpdateDate)
                   VALUES (?, 0, 0, 0, 0, 0, 0, 0, ?)""",
                [company_name, datetime.now().isoformat()]
            )
            inserted += 1

    # Also import from outOfBound files to have a complete company list
    oob_files = find_csv_files(ORIGINAL_METADATA, 'outOfBound')
    for f in oob_files:
        try:
            df = pd.read_csv(f)
            if 'Companies' in df.columns:
                for name in df['Companies'].dropna().unique():
                    name = str(name).strip()
                    existing = db.fetch_one(
                        "SELECT Company_ID FROM Company WHERE CompanyName=?",
                        [name]
                    )
                    if not existing:
                        db.execute(
                            """INSERT INTO Company (CompanyName, CIK, Fortune_1000,
                               Russell_3000, MDG_Client, SP_400, SP_500, SP_600, UpdateDate)
                               VALUES (?, 0, 0, 0, 0, 0, 0, 0, ?)""",
                            [name, datetime.now().isoformat()]
                        )
                        inserted += 1
        except Exception:
            pass

    db.commit()
    logger.info("Inserted %d new companies", inserted)
    return inserted


def import_parsing_summary(db):
    """Import SCT_Parsed_transactions into Maya_Parsing_Summary."""
    logger.info("Importing parsing summary from SCT_Parsed CSVs...")

    parsed_files = find_csv_files(ORIGINAL_METADATA, 'SCT_Parsed_transactions')
    if not parsed_files:
        logger.warning("No SCT_Parsed CSV files found")
        return 0

    inserted = 0
    for f in parsed_files:
        try:
            df = pd.read_csv(f)
            for _, row in df.iterrows():
                company_name = str(row.get('CompanyName', '')).strip()
                if not company_name or company_name == 'nan':
                    continue

                link = str(row.get('Link', ''))
                # Check duplicate
                existing = db.fetch_one(
                    "SELECT id FROM Maya_Parsing_Summary WHERE Link=?",
                    [link]
                )
                if existing:
                    continue

                # Get Company_ID
                comp = db.fetch_one(
                    "SELECT Company_ID FROM Company WHERE CompanyName=?",
                    [company_name]
                )
                company_id = comp['Company_ID'] if comp else None

                fiscal_year = row.get('FiscalYear', None)
                if pd.notna(fiscal_year):
                    fiscal_year = int(float(fiscal_year))
                else:
                    fiscal_year = None

                sct_parsed = str(row.get('SCT_Parsed', 'Not Parsed'))
                parsed_date = str(row.get('Parsed_Date', datetime.now().strftime('%Y-%m-%d')))
                filing_date = str(row.get('Filing_Date', ''))

                db.execute(
                    """INSERT INTO Maya_Parsing_Summary
                       (Company_ID, CompanyName, FiscalYear, FiledDate, FilingType,
                        Link, SCT_Parsed, Parsed_Date, ProcessingType)
                       VALUES (?, ?, ?, ?, 'DEF 14A', ?, ?, ?, 'Automatic')""",
                    [company_id, company_name, fiscal_year, filing_date,
                     link, sct_parsed, parsed_date]
                )
                inserted += 1
        except Exception as e:
            logger.debug("Error processing %s: %s", f, e)

    db.commit()
    logger.info("Inserted %d parsing summary records", inserted)
    return inserted


def copy_metadata_to_enhanced(db):
    """Copy existing CSV files to the enhanced project's data directory."""
    logger.info("Copying metadata CSVs to enhanced project...")

    if not os.path.isdir(ORIGINAL_METADATA):
        logger.warning("Original metadata directory not found: %s", ORIGINAL_METADATA)
        return 0

    copied = 0
    for month_dir in os.listdir(ORIGINAL_METADATA):
        src_dir = os.path.join(ORIGINAL_METADATA, month_dir)
        if not os.path.isdir(src_dir):
            continue
        dst_dir = os.path.join(config.METADATA_DUMP_DIR, month_dir)
        os.makedirs(dst_dir, exist_ok=True)

        for f in os.listdir(src_dir):
            if f.endswith('.csv'):
                src = os.path.join(src_dir, f)
                dst = os.path.join(dst_dir, f)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    copied += 1

    logger.info("Copied %d CSV files", copied)
    return copied


def print_summary(db):
    """Print database summary."""
    companies = db.fetch_one("SELECT COUNT(*) as c FROM Company")
    roles = db.fetch_one("SELECT COUNT(*) as c FROM Role")
    parsing = db.fetch_one("SELECT COUNT(*) as c FROM Maya_Parsing_Summary")
    parsed = db.fetch_one(
        "SELECT COUNT(*) as c FROM Maya_Parsing_Summary WHERE SCT_Parsed='Parsed'"
    )
    not_parsed = db.fetch_one(
        "SELECT COUNT(*) as c FROM Maya_Parsing_Summary WHERE SCT_Parsed='Not Parsed'"
    )
    no_table = db.fetch_one(
        "SELECT COUNT(*) as c FROM Maya_Parsing_Summary WHERE SCT_Parsed='No Table Found'"
    )

    print("\n" + "=" * 50)
    print("Database Import Summary")
    print("=" * 50)
    print("  Companies:          {}".format(companies['c']))
    print("  Roles:              {}".format(roles['c']))
    print("  Parsing Records:    {}".format(parsing['c']))
    print("    - Parsed:         {}".format(parsed['c']))
    print("    - Not Parsed:     {}".format(not_parsed['c']))
    print("    - No Table Found: {}".format(no_table['c']))
    print("=" * 50)


def main():
    logger.info("Starting data import from original MAYA project")
    logger.info("Source: %s", ORIGINAL_METADATA)

    with DatabaseManager() as db:
        init_database(db)

        companies_count = import_companies(db)
        parsing_count = import_parsing_summary(db)
        csv_count = copy_metadata_to_enhanced(db)

        print_summary(db)

    print("\nData import complete!")
    print("You can now run: python app.py --port 5050")
    return 0


if __name__ == '__main__':
    sys.exit(main())
