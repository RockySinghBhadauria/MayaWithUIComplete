#!/usr/bin/env python
"""MAYA Enhanced Project — Single CLI Entry Point.

Usage:
    python main.py                    # Run full pipeline
    python main.py --init-db          # Initialize database (create tables + seed roles)
    python main.py --step rss_feed    # Run a single step
    python main.py --from sct_parse   # Run from a specific step onwards
    python main.py --list-steps       # List available pipeline steps

Available steps:
    rss_feed, sct_parse, data_entry, sql_parse,
    equity_parse, exercise_parse, pba_parse, dct_parse
"""
import sys
import os
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from core.logging_config import setup_logging, get_logger
from core.database import DatabaseManager
from core.schema import init_database
from pipeline.runner import PipelineRunner, DEFAULT_ORDER


def parse_args():
    parser = argparse.ArgumentParser(
        description='MAYA Enhanced Pipeline — SEC Filing Parser',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--init-db', action='store_true',
                        help='Initialize database (create tables and seed data)')
    parser.add_argument('--step', type=str, metavar='STEP_NAME',
                        help='Run a single pipeline step')
    parser.add_argument('--from', dest='from_step', type=str, metavar='STEP_NAME',
                        help='Run pipeline from this step onwards')
    parser.add_argument('--list-steps', action='store_true',
                        help='List available pipeline steps')
    parser.add_argument('--log-level', type=str, default=None,
                        help='Set log level (DEBUG, INFO, WARNING, ERROR)')
    return parser.parse_args()


def main():
    args = parse_args()

    # Setup logging
    setup_logging(level=args.log_level)
    logger = get_logger('main')

    # List steps
    if args.list_steps:
        print("\nAvailable pipeline steps (in execution order):")
        for i, step in enumerate(DEFAULT_ORDER, 1):
            print("  {}. {}".format(i, step))
        print()
        return 0

    # Initialize database (UI-specific tables only — production tables are server-managed)
    if args.init_db:
        logger.info("Initializing UI-specific tables on SQL Server")
        with DatabaseManager() as db:
            init_database(db)
        logger.info("Database initialized successfully!")
        print("\nPipeline_Runs table ensured on SQL Server.")
        print("Production tables (Company, Officer, wk_SummaryComp, Officer_Outstanding_Equity,")
        print("Officer_Awards, Director, BOD_*) are server-managed — not touched.")
        return 0

    # Run pipeline
    with DatabaseManager() as db:
        # Ensure tables exist
        init_database(db)

        runner = PipelineRunner(db)

        if args.step:
            if args.step not in DEFAULT_ORDER:
                print("Error: Unknown step '{}'. Use --list-steps to see available steps.".format(args.step))
                return 1
            logger.info("Running single step: %s", args.step)
            runner.run_step(args.step)

        elif args.from_step:
            if args.from_step not in DEFAULT_ORDER:
                print("Error: Unknown step '{}'. Use --list-steps to see available steps.".format(args.from_step))
                return 1
            logger.info("Running pipeline from: %s", args.from_step)
            runner.run_from(args.from_step)

        else:
            logger.info("Running full pipeline")
            runner.run_all()

        # Print summary
        print("\n" + "=" * 50)
        print("Pipeline Run Summary")
        print("=" * 50)
        for step_name, result in runner.results.items():
            status = "FAILED" if 'error' in result else "OK"
            print("  {}: {} - {}".format(step_name, status, result))
        print("=" * 50)

    return 0


if __name__ == '__main__':
    sys.exit(main())
