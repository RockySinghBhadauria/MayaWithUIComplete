"""Structured per-run logging — ported from the production maya_logging.py.

Layout (matches production exactly):

    backend/logs/
    └── <year>/
        ├── runs/
        │   └── <run_id>/                 ← one folder per pipeline execution
        │       ├── _errors.log           ← every WARNING/ERROR across all modules
        │       ├── rss_parser.log
        │       ├── sct_parser.log
        │       ├── sql_parser.log
        │       ├── equity_parser.log
        │       ├── exercise_parser.log
        │       ├── pba_parser.log
        │       ├── dct_parser.log
        │       ├── api.log
        │       └── ...
        ├── filing_dump/                  ← shared across all runs in this year
        └── sct_metadata_dump/

Run ID is the current ISO timestamp (YYYY-MM-DD_HH-MM-SS). Stored in
MAYA_RUN_ID env var so a single pipeline run with multiple parser steps
writes to the same folder.

Log format (matches production):
  YYYY-MM-DD HH:MM:SS.mmm | LEVEL   | module             | ctx              | message

In-memory buffer (BufferHandler) still attached so the /api/logs endpoint
keeps working for the React Logs page.
"""
from __future__ import annotations

import logging
import os
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

import config

# ---------------------------------------------------------------------------
# Buffer for React /api/logs
# ---------------------------------------------------------------------------

_log_buffer: deque = deque(maxlen=1000)


class BufferHandler(logging.Handler):
    def emit(self, record):
        try:
            _log_buffer.append(self.format(record))
        except Exception:
            self.handleError(record)


def get_log_buffer():
    return list(_log_buffer)


# ---------------------------------------------------------------------------
# Production-style format
# ---------------------------------------------------------------------------

_FORMAT = (
    "%(asctime)s.%(msecs)03d | %(levelname)-7s | "
    "%(mod)-18s | %(ctx)-32s | %(message)s"
)
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # backend/
_LOGS_ROOT = _PROJECT_ROOT / "logs"

_configured: set[str] = set()
_current_ctx: list[str] = []


class _DefaultsFilter(logging.Filter):
    """Guarantee every record has 'mod' and 'ctx' fields."""

    def filter(self, record):
        if not hasattr(record, "mod"):
            record.mod = record.name.split(".")[-1][:18]
        if not hasattr(record, "ctx"):
            record.ctx = (_current_ctx[-1] if _current_ctx else "-")
        return True


class _ContextAdapter(logging.LoggerAdapter):
    """Attaches mod + ctx to every log record."""

    def __init__(self, logger, *, default_mod, default_ctx="-"):
        super().__init__(logger, {})
        self._default_mod = default_mod
        self._default_ctx = default_ctx

    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("mod", self._default_mod)
        if "ctx" not in extra:
            if self._default_ctx and self._default_ctx != "-":
                extra["ctx"] = self._default_ctx
            elif _current_ctx:
                extra["ctx"] = _current_ctx[-1]
            else:
                extra["ctx"] = "-"
        return msg, kwargs


# ---------------------------------------------------------------------------
# Run-id resolution
# ---------------------------------------------------------------------------

def _current_run_dir() -> Path:
    run_id = os.environ.get("MAYA_RUN_ID")
    if not run_id:
        run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        os.environ["MAYA_RUN_ID"] = run_id
    year = run_id[:4]
    p = _LOGS_ROOT / year / "runs" / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _short_name(module_name: str) -> str:
    """Turn 'maya.equity_parser' or 'parsers.equity_parser' into 'equity_parser'."""
    return module_name.rsplit(".", 1)[-1] or "module"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(level=None):
    """Initialize the root 'maya' logger and a default fallback handler.

    Per-module handlers are attached lazily inside get_logger(). This function
    is safe to call repeatedly.
    """
    level_name = (level or config.LOG_LEVEL or "INFO").upper()
    root = logging.getLogger("maya")
    root.setLevel(getattr(logging, level_name, logging.INFO))

    if "maya" in _configured:
        return root

    run_dir = _current_run_dir()
    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FMT)

    # Errors aggregator — every WARNING+ from any maya child logger
    errors_handler = logging.FileHandler(run_dir / "_errors.log", encoding="utf-8")
    errors_handler.setLevel(logging.WARNING)
    errors_handler.setFormatter(formatter)
    errors_handler.addFilter(_DefaultsFilter())
    root.addHandler(errors_handler)

    # Console — always on so devs see live activity
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(_DefaultsFilter())
    root.addHandler(console)

    # React UI tail
    buf = BufferHandler()
    buf.setFormatter(formatter)
    buf.addFilter(_DefaultsFilter())
    root.addHandler(buf)

    _configured.add("maya")
    return root


def get_logger(name: str) -> _ContextAdapter:
    """Per-module logger that writes to logs/<year>/runs/<run_id>/<module>.log
    plus the shared errors log + console + buffer.
    """
    short = _short_name(name)
    key = f"maya.{short}"

    # Ensure root is configured (errors log + console + buffer)
    setup_logging()

    raw = logging.getLogger(key)
    if key not in _configured:
        raw.setLevel(logging.getLogger("maya").level)
        # Don't propagate — we'll explicitly attach handlers (otherwise
        # console + buffer fire twice because root also has them).
        # Errors handler stays on root and we manually re-route below.
        raw.propagate = False

        run_dir = _current_run_dir()
        formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FMT)

        # Per-module file: everything at the configured level and up
        mod_handler = logging.FileHandler(run_dir / f"{short}.log", encoding="utf-8")
        mod_handler.setFormatter(formatter)
        mod_handler.addFilter(_DefaultsFilter())
        raw.addHandler(mod_handler)

        # Bubble up to root for the shared _errors.log + console + buffer.
        # Setting propagate=True after we already explicitly attached zero
        # handlers above (only the per-module one was attached locally) is
        # cleaner — but we set False because Python will double-emit
        # via root's console + buffer. Instead, attach console + buffer
        # directly:
        for h in logging.getLogger("maya").handlers:
            raw.addHandler(h)

        _configured.add(key)

    return _ContextAdapter(raw, default_mod=short)


def get_company_logger(name: str, *, cik=None, company_name=None, company_id=None) -> _ContextAdapter:
    """Logger tagged with a company's identifiers in the ctx column.

    Side effect: pushes the company onto the global current-ctx stack so any
    plain get_logger().info(...) made while processing this company is
    auto-tagged.
    """
    short = _short_name(name)
    get_logger(name)  # ensure handlers attached

    raw = logging.getLogger(f"maya.{short}")
    parts = []
    if company_id is not None and str(company_id).strip():
        parts.append(f"ID={company_id}")
    if cik is not None and str(cik).strip():
        try:
            parts.append(f"CIK={int(str(cik).strip()):010d}")
        except (ValueError, TypeError):
            parts.append(f"CIK={cik}")
    if company_name:
        parts.append(str(company_name)[:24])
    ctx = " ".join(parts) if parts else "-"
    set_current_company(ctx)
    return _ContextAdapter(raw, default_mod=short, default_ctx=ctx)


def set_current_company(ctx):
    _current_ctx.clear()
    if ctx and ctx != "-":
        _current_ctx.append(ctx)


def clear_current_company():
    _current_ctx.clear()


def get_run_id() -> str:
    """Get (or create) the current pipeline run ID."""
    if "MAYA_RUN_ID" not in os.environ:
        os.environ["MAYA_RUN_ID"] = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.environ["MAYA_RUN_ID"]


def start_new_run() -> str:
    """Force a new run_id (next get_logger / setup_logging will write to a new folder).

    Call this from the pipeline runner at the start of each /api/pipeline/run.
    """
    new_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    os.environ["MAYA_RUN_ID"] = new_id
    # Wipe configured set so handlers re-attach to the new folder
    _configured.clear()
    # Clean any existing handlers on the maya root + per-module loggers
    root = logging.getLogger("maya")
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    for name in list(logging.root.manager.loggerDict.keys()):
        if name.startswith("maya."):
            lg = logging.getLogger(name)
            for h in list(lg.handlers):
                lg.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass
    return new_id
