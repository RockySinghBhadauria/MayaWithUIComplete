#!/usr/bin/env python
"""MAYA Enhanced Project — FastAPI Backend.

Serves REST API for the React frontend and runs pipeline steps.

Usage:
    python app.py                    # Start API server on port 5000
    python app.py --port 8000        # Custom port
"""
import sys
import os
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
from core.logging_config import setup_logging, get_logger, get_log_buffer
from core.database import DatabaseManager
from core.schema import init_database
from pipeline.runner import PipelineRunner, DEFAULT_ORDER
from pipeline.state import PipelineState

setup_logging()
logger = get_logger('api')

# Unique per-process ID — used to scope the "clear stale running rows" startup query
# so multiple FastAPI processes don't clobber each other's in-flight runs.
PROCESS_ID = "pid-{}-{}".format(os.getpid(), uuid.uuid4().hex[:8])


@asynccontextmanager
async def lifespan(app):
    """Replace deprecated @app.on_event handlers with lifespan context."""
    import builtins
    builtins._maya_stop_pipeline = False

    logger.info("Initializing database (process_id=%s)", PROCESS_ID)
    with DatabaseManager() as db:
        init_database(db)
        # Only clear OUR own stale "running" rows (not other processes')
        db.execute(
            "UPDATE Pipeline_Runs SET status='stopped' "
            "WHERE status='running' AND run_group LIKE ?",
            [PROCESS_ID + "%"]
        )
        db.commit()
    logger.info("MAYA API server ready")
    yield
    logger.info("MAYA API server shutting down")


app = FastAPI(title="MAYA Enhanced Pipeline", version="1.0.0", lifespan=lifespan)

# CORS — origins from env, default to React dev server.
# Wildcard '*' with allow_credentials=True is rejected by browsers and a security risk.
_cors_origins = os.environ.get(
    "MAYA_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track running pipeline
_pipeline_thread = None
_pipeline_lock = threading.Lock()


def get_db():
    db = DatabaseManager()
    db.connect()
    return db


def _paginate_sql(order_by_clause, per_page, offset):
    """SQL Server pagination using OFFSET ... FETCH NEXT (requires ORDER BY).
    Returns (sql_fragment, params_list)."""
    return (
        "{} OFFSET {} ROWS FETCH NEXT {} ROWS ONLY".format(
            order_by_clause, int(offset), int(per_page)),
        []
    )


# ============================================================
# Request/Response models
# ============================================================

class PipelineRunRequest(BaseModel):
    step: Optional[str] = None
    from_step: Optional[str] = None
    limit: Optional[int] = None  # Process only first N companies (for testing)


# ============================================================
# API Routes
# ============================================================

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/dashboard")
def dashboard():
    db = get_db()
    try:
        from core.database import cast_date_sql, today_date_sql
        today_stats = db.fetch_all(
            "SELECT SCT_Parsed, COUNT(*) as count "
            "FROM Maya_Parsing_Summary "
            "WHERE {} = {} "
            "GROUP BY SCT_Parsed".format(cast_date_sql("Parsed_Date"), today_date_sql())
        )
        total_companies = db.fetch_one("SELECT COUNT(*) as count FROM Company") or {"count": 0}
        total_officers = db.fetch_one("SELECT COUNT(*) as count FROM Officer") or {"count": 0}
        total_parsed = db.fetch_one("SELECT COUNT(*) as count FROM Maya_Parsing_Summary") or {"count": 0}

        recent_daily = db.fetch_all(
            "SELECT TOP 30 Parsed_Date as parse_date, "
            "COUNT(*) as total, "
            "SUM(CASE WHEN SCT_Parsed='Parsed' THEN 1 ELSE 0 END) as parsed, "
            "SUM(CASE WHEN SCT_Parsed='No Table found' THEN 1 ELSE 0 END) as no_table "
            "FROM Maya_Parsing_Summary "
            "WHERE Parsed_Date IS NOT NULL AND Parsed_Date != '' "
            "GROUP BY Parsed_Date "
            "ORDER BY Parsed_Date DESC"
        )

        state = PipelineState(db)
        recent_runs = state.get_recent_runs(5)

        return {
            "today_stats": today_stats,
            "total_companies": total_companies["count"],
            "total_officers": total_officers["count"],
            "total_parsed": total_parsed["count"],
            "recent_daily": recent_daily,
            "recent_runs": recent_runs,
        }
    finally:
        db.close()


@app.get("/api/companies")
def list_companies(search: str = "", page: int = 1, per_page: int = 50):
    db = get_db()
    try:
        offset = (page - 1) * per_page
        if search:
            pat = "%{}%".format(search)
            page_sql, page_params = _paginate_sql("ORDER BY CompanyName", per_page, offset)
            companies = db.fetch_all(
                "SELECT * FROM Company "
                "WHERE CompanyName LIKE ? OR Symbol LIKE ? OR CAST(CIK AS NVARCHAR(50)) LIKE ? "
                + page_sql,
                [pat, pat, pat] + page_params
            )
            count_row = db.fetch_one(
                "SELECT COUNT(*) as count FROM Company "
                "WHERE CompanyName LIKE ? OR Symbol LIKE ? OR CAST(CIK AS NVARCHAR(50)) LIKE ?",
                [pat, pat, pat]
            )
        else:
            page_sql, page_params = _paginate_sql("ORDER BY CompanyName", per_page, offset)
            companies = db.fetch_all("SELECT * FROM Company " + page_sql, page_params)
            count_row = db.fetch_one("SELECT COUNT(*) as count FROM Company")

        return {
            "companies": companies,
            "total": count_row["count"] if count_row else 0,
            "page": page,
            "per_page": per_page,
        }
    finally:
        db.close()


@app.get("/api/companies/{company_id}")
def get_company(company_id: int):
    db = get_db()
    try:
        company = db.fetch_one("SELECT * FROM Company WHERE Company_ID=?", [company_id])
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        officers = db.fetch_all(
            "SELECT * FROM Officer WHERE Company_ID=? ORDER BY FiscalYear DESC, OfficerName",
            [company_id]
        )
        compensation = db.fetch_all(
            "SELECT * FROM wk_SummaryComp WHERE Company_ID=? ORDER BY FiscalYear DESC, OfficerName",
            [company_id]
        )
        parsing_history = db.fetch_all(
            "SELECT * FROM Maya_Parsing_Summary WHERE Company_ID=? ORDER BY FiscalYear DESC",
            [company_id]
        )
        equity = db.fetch_all(
            "SELECT * FROM Officer_Outstanding_Equity WHERE Company_ID=? ORDER BY FiscalYear DESC",
            [company_id]
        )
        awards = db.fetch_all(
            "SELECT * FROM Officer_Awards WHERE Company_ID=? ORDER BY FiscalYear DESC",
            [company_id]
        )

        return {
            "company": company,
            "officers": officers,
            "compensation": compensation,
            "equity": equity,
            "awards": awards,
            "parsing_history": parsing_history,
        }
    finally:
        db.close()


@app.get("/api/officers")
def list_officers(search: str = "", company_id: str = "", page: int = 1, per_page: int = 50):
    db = get_db()
    try:
        offset = (page - 1) * per_page
        query = "SELECT o.*, c.CompanyName FROM Officer o LEFT JOIN Company c ON o.Company_ID=c.Company_ID WHERE 1=1"
        params = []

        if search:
            query += " AND o.OfficerName LIKE ?"
            params.append("%{}%".format(search))
        if company_id:
            query += " AND o.Company_ID=?"
            params.append(int(company_id))

        page_sql, page_params = _paginate_sql(
            "ORDER BY o.FiscalYear DESC, o.OfficerName", per_page, offset)
        query += " " + page_sql
        params.extend(page_params)

        officers = db.fetch_all(query, params)
        return {"officers": officers, "page": page}
    finally:
        db.close()


@app.get("/api/parsing-summary")
def parsing_summary(status: str = "", page: int = 1, per_page: int = 50):
    db = get_db()
    try:
        offset = (page - 1) * per_page
        query = "SELECT * FROM Maya_Parsing_Summary WHERE 1=1"
        params = []
        if status:
            query += " AND SCT_Parsed=?"
            params.append(status)
        page_sql, page_params = _paginate_sql("ORDER BY Parsed_Date DESC", per_page, offset)
        query += " " + page_sql
        params.extend(page_params)

        records = db.fetch_all(query, params)
        count = db.fetch_one("SELECT COUNT(*) as count FROM Maya_Parsing_Summary")
        return {
            "records": records,
            "total": count["count"] if count else 0,
            "page": page,
        }
    finally:
        db.close()


# ============================================================
# Pipeline Control
# ============================================================

@app.get("/api/pipeline/steps")
def pipeline_steps():
    return {"steps": DEFAULT_ORDER}


@app.post("/api/pipeline/run")
def pipeline_run(body: PipelineRunRequest):
    global _pipeline_thread

    with _pipeline_lock:
        if _pipeline_thread and _pipeline_thread.is_alive():
            raise HTTPException(status_code=409, detail="Pipeline already running")

    def _run():
        # Reset stop flag
        import builtins
        builtins._maya_stop_pipeline = False
        # Re-setup logging in thread to ensure buffer handler works
        from core.logging_config import setup_logging
        setup_logging()
        tlog = get_logger('pipeline.thread')
        db = get_db()
        try:
            init_database(db)
            runner = PipelineRunner(db)
            if body.step:
                tlog.info("Starting single step: %s", body.step)
                runner.run_step(body.step)
            elif body.from_step:
                tlog.info("Starting from step: %s", body.from_step)
                runner.run_from(body.from_step)
            else:
                tlog.info("Starting full pipeline")
                runner.run_all()
            tlog.info("Pipeline thread finished successfully")
        except Exception as e:
            tlog.exception("Pipeline run failed: %s", e)
        finally:
            db.close()

    _pipeline_thread = threading.Thread(target=_run, daemon=True)
    _pipeline_thread.start()

    return {
        "status": "started",
        "mode": "step" if body.step else ("from" if body.from_step else "full"),
        "target": body.step or body.from_step or "all",
    }


@app.post("/api/pipeline/stop")
def pipeline_stop():
    """Stop the running pipeline cooperatively at the next step boundary.

    Note: previously used ctypes.PyThreadState_SetAsyncExc to force-kill the thread,
    which is unsafe — it can leave DB connections half-closed, locks held, and SP
    transactions abandoned. With production DB, that's data-corruption risk.
    Now we only set the stop flag; pipeline checks it between steps.
    """
    global _pipeline_thread

    if _pipeline_thread is None or not _pipeline_thread.is_alive():
        return {"status": "not_running", "message": "No pipeline is running"}

    import builtins
    builtins._maya_stop_pipeline = True
    logger.info("Stop flag set — pipeline will halt at next step boundary")

    # Update DB status
    db = get_db()
    try:
        db.execute(
            "UPDATE Pipeline_Runs SET status='stopped', completed_at=? WHERE status='running'",
            [datetime.now().isoformat()]
        )
        db.commit()
    finally:
        db.close()

    _pipeline_thread = None
    logger.info("Pipeline stopped")
    return {"status": "stopped", "message": "Pipeline stopped immediately."}


@app.get("/api/pipeline/status")
def pipeline_status():
    global _pipeline_thread
    db = get_db()
    try:
        state = PipelineState(db)
        latest_group = state.get_latest_run_group()
        steps = state.get_run_status(latest_group) if latest_group else []
        is_running = _pipeline_thread is not None and _pipeline_thread.is_alive()
        return {"is_running": is_running, "run_group": latest_group, "steps": steps}
    finally:
        db.close()


@app.get("/api/pipeline/history")
def pipeline_history():
    db = get_db()
    try:
        state = PipelineState(db)
        runs = state.get_recent_runs(20)
        return {"runs": runs}
    finally:
        db.close()


# ============================================================
# RSS Feed & Module Output Viewers
# ============================================================

@app.get("/api/rss-feed")
def get_rss_feed():
    """View today's RSS feed (companies fetched from SEC)."""
    import glob
    import pandas as pd
    import math

    feed_dir = os.path.join(config.METADATA_DUMP_DIR, str(datetime.now().month))
    feeds = sorted(glob.glob(os.path.join(feed_dir, "edgar_feed_live_*.csv")), reverse=True)
    if not feeds:
        return {"companies": [], "total": 0, "file": None, "message": "No RSS feed found"}

    try:
        df = pd.read_csv(feeds[0])
        # Replace NaN with None for JSON serialization
        df = df.where(df.notna(), None)
        records = []
        for _, row in df.iterrows():
            rec = {}
            for col in df.columns:
                val = row[col]
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    rec[col] = None
                else:
                    rec[col] = val
            records.append(rec)
        return {
            "companies": records,
            "total": len(records),
            "file": os.path.basename(feeds[0]),
        }
    except Exception as e:
        return {"companies": [], "total": 0, "file": None, "message": str(e)}


def _group_by_company(data, status_field):
    """Group records by company for card-style display."""
    companies = {}
    for r in data:
        name = r.get("CompanyName") or "Unknown"
        if name not in companies:
            companies[name] = {
                "CompanyName": name,
                "FilingURL": r.get("FilingURL"),
                "Parsed_Date": r.get("Parsed_Date"),
                "Status": r.get("Status") or r.get(status_field),
                "FiscalYear": r.get("FiscalYear"),
                "officers": []
            }
        companies[name]["officers"].append(r)
    return list(companies.values())


def _top_n_sql(n):
    """SQL Server TOP N prefix. Returns (prefix, empty_suffix) for compat with old call sites."""
    return ("TOP {} ".format(n), "")


@app.get("/api/module-output/{module}")
def get_module_output(module: str):
    """View parsed output for a module (sct, equity, exercise, pba, dct).

    Columns returned match the production SP writes 1:1 so the UI tables look exactly
    like the click app (Officer.aspx, OutstandingEquityAwards.aspx, PBA.aspx, etc.).
    """
    db = get_db()
    top_prefix, limit_suffix = _top_n_sql(500)
    try:
        if module == "sct":
            # Matches sp_wk_SummaryComp_IU_MAYA target columns (production sql_parser.py)
            data = db.fetch_all(
                "SELECT " + top_prefix +
                "w.Officer_ID, w.OfficerName, w.FiscalYear, w.Salary, w.Bonus, "
                "w.Stock_Award, w.Option_Awards, w.Non_Eq_Incentive_Plan_Comp, "
                "w.Chg_PensionValue_NQDC_Earnings, w.Chg_Retention_Plan_Value, "
                "w.All_Other, w.Total, w.Designation, w.TagName, "
                "c.CompanyName, m.Link as FilingURL, m.Parsed_Date, m.SCT_Parsed "
                "FROM wk_SummaryComp w "
                "LEFT JOIN Company c ON w.Company_ID = c.Company_ID "
                "LEFT JOIN Maya_Parsing_Summary m ON w.Company_ID = m.Company_ID AND w.FiscalYear = m.FiscalYear "
                "ORDER BY c.CompanyName, w.FiscalYear DESC" + limit_suffix
            )
            companies = {}
            for r in data:
                name = r.get("CompanyName") or "Unknown"
                if name not in companies:
                    companies[name] = {
                        "CompanyName": name,
                        "FilingURL": r.get("FilingURL"),
                        "Parsed_Date": r.get("Parsed_Date"),
                        "SCT_Parsed": r.get("SCT_Parsed"),
                        "FiscalYear": r.get("FiscalYear"),
                        "officers": []
                    }
                companies[name]["officers"].append(r)
            return {
                "module": "SCT — Summary Compensation Table (wk_SummaryComp)",
                "records": data,
                "grouped": list(companies.values()),
                "total": len(data),
                "companies_count": len(companies),
            }
        elif module == "equity":
            # Matches sp_Outstanding_Equity_Awards_IU_MAYA target columns
            data = db.fetch_all(
                "SELECT " + top_prefix +
                "oe.Officer_Outstanding_Equity_ID, oe.Officer_ID, oe.Company_ID, "
                "oe.FiscalYear, oe.Equity_Type, oe.Grant_Date, "
                "oe.Number_Securities_Exercisable_Options, oe.Exercise_Price, "
                "oe.Expiration_Date, oe.Tracking_Stock_Ticker, oe.No_OEA_In_Proxy, "
                "oe.Outstanding_Modification, o.OfficerName, c.CompanyName, "
                "m.Link as FilingURL, m.Parsed_Date, "
                "m.Outstanding_Equity_Parsed as Status "
                "FROM Officer_Outstanding_Equity oe "
                "LEFT JOIN Officer o ON oe.Officer_ID = o.Officer_ID "
                "LEFT JOIN Company c ON oe.Company_ID = c.Company_ID "
                "LEFT JOIN Maya_Parsing_Summary m ON oe.Company_ID = m.Company_ID AND oe.FiscalYear = m.FiscalYear "
                "ORDER BY c.CompanyName, oe.FiscalYear DESC" + limit_suffix
            )
            grouped = _group_by_company(data, "Outstanding_Equity_Parsed")
            return {"module": "Equity — Outstanding Equity Awards (Officer_Outstanding_Equity)",
                    "records": data, "grouped": grouped,
                    "total": len(data), "companies_count": len(grouped)}
        elif module == "exercise":
            # Matches sp_ExerciseandVested_U_MAYA — 4 cols on Officer
            data = db.fetch_all(
                "SELECT " + top_prefix +
                "o.Officer_ID, o.OfficerName, o.FiscalYear, "
                "o.Option_Shares_Acquired, o.Option_Value_Realized, "
                "o.Stock_Shares_Acquired, o.Stock_Value_Realized, "
                "c.CompanyName, o.Company_ID, "
                "m.Link as FilingURL, m.Parsed_Date, m.Vested_Parsed as Status "
                "FROM Officer o "
                "LEFT JOIN Company c ON o.Company_ID = c.Company_ID "
                "LEFT JOIN Maya_Parsing_Summary m ON o.Company_ID = m.Company_ID AND o.FiscalYear = m.FiscalYear "
                "WHERE o.Option_Shares_Acquired IS NOT NULL "
                "   OR o.Stock_Shares_Acquired IS NOT NULL "
                "ORDER BY c.CompanyName, o.FiscalYear DESC" + limit_suffix
            )
            grouped = _group_by_company(data, "Vested_Parsed")
            return {"module": "Exercise — Option Exercises & Stock Vested (Officer)",
                    "records": data, "grouped": grouped,
                    "total": len(data), "companies_count": len(grouped)}
        elif module == "pba":
            # Matches sp_wk_PlanBasedAward_U_MAYA target columns
            data = db.fetch_all(
                "SELECT " + top_prefix +
                "oa.Officer_Awards_ID, oa.Officer_ID, oa.Company_ID, oa.FiscalYear, "
                "oa.Award_Category, oa.GrantDate, oa.ActionDate, "
                "oa.NonEquity_Threshold, oa.NonEquity_Target, oa.NonEquity_Maximum, "
                "oa.Equity_Threshold, oa.Equity_Target, oa.Equity_Maximum, "
                "oa.Option_Threshold, oa.Option_Target, oa.Option_Maximum, "
                "oa.AllOther_Stock, oa.AllOther_Options, oa.Base_Price, "
                "oa.GrantDate_Price, oa.GDFV_Stock_Option, "
                "o.OfficerName, c.CompanyName, "
                "m.Link as FilingURL, m.Parsed_Date, m.PBA_Parsed as Status "
                "FROM Officer_Awards oa "
                "LEFT JOIN Officer o ON oa.Officer_ID = o.Officer_ID "
                "LEFT JOIN Company c ON oa.Company_ID = c.Company_ID "
                "LEFT JOIN Maya_Parsing_Summary m ON oa.Company_ID = m.Company_ID AND oa.FiscalYear = m.FiscalYear "
                "ORDER BY c.CompanyName, oa.FiscalYear DESC" + limit_suffix
            )
            grouped = _group_by_company(data, "PBA_Parsed")
            return {"module": "PBA — Grants of Plan-Based Awards (Officer_Awards)",
                    "records": data, "grouped": grouped,
                    "total": len(data), "companies_count": len(grouped)}
        elif module == "dct":
            # Matches sp_GenerateDirector_MAYA writes — Director + BOD_DirectorComp.
            try:
                data = db.fetch_all(
                    "SELECT " + top_prefix +
                    "bdc.Director_ID, bdc.Name as Director_Name, bdc.Company_Id as Company_ID, "
                    "bdc.FiscalYear, bdc.FeesEarnedorPaid, bdc.stockawards as StockAwards, "
                    "bdc.OptionAwards, bdc.allothercompensation as AllotherComp, bdc.total as Total, "
                    "c.CompanyName, mb.Link as FilingURL, mb.Parsed_Date, "
                    "mb.DCT_Parsed as Status "
                    "FROM BOD_DirectorComp bdc "
                    "LEFT JOIN Company c ON bdc.Company_Id = c.Company_ID "
                    "LEFT JOIN Maya_Parsing_Summary mb ON bdc.Company_Id = mb.Company_ID AND bdc.FiscalYear = mb.FiscalYear "
                    "ORDER BY c.CompanyName, bdc.FiscalYear DESC" + limit_suffix
                )
                grouped = _group_by_company(data, "DCT_Parsed")
                return {"module": "DCT — Director Compensation Table (BOD_DirectorComp)",
                        "records": data, "grouped": grouped,
                        "total": len(data), "companies_count": len(grouped)}
            except Exception as e:
                logger.warning("DCT module-output failed: %s", e)
                return {"module": "DCT — Director Compensation Table",
                        "records": [], "grouped": [], "total": 0, "companies_count": 0,
                        "warning": "DCT tables not yet populated: " + str(e)}
        else:
            raise HTTPException(status_code=400, detail="Unknown module: " + module)
    finally:
        db.close()


@app.get("/api/stats")
def get_stats():
    """Get counts for all modules."""
    db = get_db()
    try:
        return {
            "companies": (db.fetch_one("SELECT COUNT(*) as c FROM Company") or {}).get("c", 0),
            "officers": (db.fetch_one("SELECT COUNT(*) as c FROM Officer") or {}).get("c", 0),
            "sct_records": (db.fetch_one("SELECT COUNT(*) as c FROM wk_SummaryComp") or {}).get("c", 0),
            "equity_records": (db.fetch_one("SELECT COUNT(*) as c FROM Officer_Outstanding_Equity") or {}).get("c", 0),
            "exercise_records": (db.fetch_one("SELECT COUNT(*) as c FROM Officer WHERE Option_Shares_Acquired IS NOT NULL") or {}).get("c", 0),
            "pba_records": (db.fetch_one("SELECT COUNT(*) as c FROM Officer_Awards") or {}).get("c", 0),
            "parsing_total": (db.fetch_one("SELECT COUNT(*) as c FROM Maya_Parsing_Summary") or {}).get("c", 0),
            "parsing_parsed": (db.fetch_one("SELECT COUNT(*) as c FROM Maya_Parsing_Summary WHERE SCT_Parsed='Parsed'") or {}).get("c", 0),
            "parsing_not_parsed": (db.fetch_one("SELECT COUNT(*) as c FROM Maya_Parsing_Summary WHERE SCT_Parsed='Not Parsed'") or {}).get("c", 0),
            "parsing_no_table": (db.fetch_one("SELECT COUNT(*) as c FROM Maya_Parsing_Summary WHERE SCT_Parsed='No Table found'") or {}).get("c", 0),
            "parsing_already_exist": (db.fetch_one("SELECT COUNT(*) as c FROM Maya_Parsing_Summary WHERE SCT_Parsed='Already Exist'") or {}).get("c", 0),
        }
    finally:
        db.close()


# ============================================================
# Data Management
# ============================================================

@app.delete("/api/data/today")
def delete_today_data():
    """Delete all data parsed today — allows re-running the pipeline fresh."""
    db = get_db()
    try:
        from core.database import cast_date_sql, today_date_sql
        td = today_date_sql()
        db.execute(
            "DELETE FROM Maya_Parsing_Summary WHERE {} = {}".format(
                cast_date_sql("Parsed_Date"), td)
        )
        db.execute("DELETE FROM Pipeline_Runs WHERE run_date = {}".format(td))
        db.commit()
        remaining = db.fetch_one("SELECT COUNT(*) as c FROM Maya_Parsing_Summary")
        return {
            "status": "deleted",
            "message": "Today's data has been cleared. You can re-run the pipeline.",
            "remaining_records": remaining["c"] if remaining else 0,
        }
    finally:
        db.close()


@app.delete("/api/data/all")
def delete_all_data():
    """Delete ALL parsed data (keeps Company and Role tables)."""
    db = get_db()
    try:
        # WARNING: this deletes from PRODUCTION SQL Server tables — for re-run/testing only.
        # Order respects FK dependencies (children before parents).
        for table in ["Officer_Outstanding_Equity", "Officer_Awards", "wk_SummaryComp",
                       "Officer", "Maya_Parsing_Summary", "Maya_BOD_Parsing_Summary",
                       "Pipeline_Runs"]:
            db.execute("DELETE FROM " + table)
        db.commit()
        return {"status": "deleted", "message": "All parsed data cleared. Companies and Roles kept."}
    finally:
        db.close()


# ============================================================
# Logs
# ============================================================

@app.get("/api/logs")
def get_logs(limit: int = 100):
    logs = get_log_buffer()
    return {"logs": logs[-limit:]}


# ============================================================
# Serve React Frontend (production)
# ============================================================

# Backend lives in backend/; frontend build is at ../frontend/build relative to this file.
_frontend_build = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "build"))

# Mount static assets (JS, CSS)
if os.path.isdir(os.path.join(_frontend_build, "static")):
    app.mount("/static", StaticFiles(directory=os.path.join(_frontend_build, "static")), name="static-files")


# Catch-all: serve index.html for ALL non-API routes (React Router)
@app.get("/{full_path:path}")
def serve_react(full_path: str):
    # Try to serve the exact file first (favicon.ico, manifest.json, etc.)
    file_path = os.path.join(_frontend_build, full_path)
    if full_path and os.path.isfile(file_path):
        return FileResponse(file_path)
    # For everything else, serve index.html (React Router handles client-side routing)
    return FileResponse(os.path.join(_frontend_build, "index.html"))


if __name__ == "__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("app:app", host="0.0.0.0", port=args.port, reload=args.reload)
