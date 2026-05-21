# CHANGES — UI Maya Project (MayaWithUIComplete)

This document tracks every change made to convert the UI fork from a standalone SQLite demo into a production-DB-connected pipeline that calls stored procedures.

> **TL;DR:** Removed SQLite, made SQL Server the only backend, replaced raw INSERT/UPDATE with stored-procedure calls gated by the no-UPDATE rule (`core/sp_gate.py`), wired DCT, fixed status-string casing, hardened FastAPI hygiene, reorganized into `backend/` + `frontend/` with production-style `logs/<year>/` layout.

---

## Phase 0 — Repository reorganization (backend/ + frontend/)

All Python code moved into `backend/`. Layout now mirrors a standard monorepo:

```
<repo>/
├── backend/         # all Python (app.py, config.py, core/, parsers/, pipeline/, mailer/, utils/, docs/, data/)
│   └── logs/<year>/{filing_dump, sct_metadata_dump, runs}    # production-style runtime artifacts
├── frontend/        # React 19 (unchanged)
├── CLAUDE.md, README.md, .gitignore
```

### Path changes
| Old | New |
|-----|-----|
| `<repo>/app.py` etc. | `<repo>/backend/app.py` etc. |
| `<repo>/data/metadata_dump/<month>/` | `<repo>/backend/logs/<year>/sct_metadata_dump/<month>/` |
| `<repo>/data/filing_dump/SCT_filings_dump/<month>/<day>/` | `<repo>/backend/logs/<year>/filing_dump/SCT_filings_dump/<month>/<day>/` |
| `<repo>/logs/maya_YYYYMMDD.log` | `<repo>/backend/logs/<year>/runs/maya_YYYYMMDD.log` |
| `<repo>/data/mssql_*_export.csv` | `<repo>/backend/data/mssql_*_export.csv` (one-off seed CSVs only) |

### Why this layout
- Matches the production Maya project's `logs/<year>/{filing_dump, sct_metadata_dump, runs}` structure exactly.
- Same verification queries / `deletecompany.py` patterns / log inspection habits transfer.
- Clean monorepo boundary — frontend devs don't need to navigate Python folders, backend devs don't trip over React build artifacts.

### Code changes for the new layout
- `backend/config.py` — replaced flat `METADATA_DUMP_DIR` / `FILING_DUMP_DIR` constants with year-aware `metadata_dump_dir(year)`, `filing_dump_dir(year)`, `runs_dir(year)` functions. Back-compat aliases kept for callers that still import the constants.
- `backend/core/logging_config.py` — log files now land in `logs/<year>/runs/`.
- `backend/utils/csv_manager.py` — `get_metadata_dir()` and `get_filing_dir()` use the new year-partitioned helpers.
- `backend/app.py` — frontend build path now resolves to `../frontend/build` (one level up from `backend/`).
- `backend/.gitignore` — `logs/` and `data/*.csv` rules updated for the new layout.

---

## Phase 1 — SQL Server only

### Removed
- `maya.db` (legacy SQLite file) — deleted from repo
- All `sqlite3` imports — removed
- `config.DB_TYPE` / `config.SQLITE_DB_PATH` / `config.MSSQL_*` env-dependent settings — removed
- All `date('now')`, `PRAGMA foreign_keys`, `LIMIT ? OFFSET ?`, `AUTOINCREMENT` SQLite dialect — replaced
- `core/database.py` dual-mode dispatch — removed; pyodbc-only now

### Added
- `core/dbDetails.py` — loads connection string from `.env` (matches production Maya pattern)
- `.env.example` — template for `DB_DRIVER` / `DB_SERVER` / `DB_NAME` / `DB_USER` / `DB_PASSWORD`
- `core/database.py::today_date_sql()` + `cast_date_sql()` helpers (SQL Server `GETDATE()` / `CAST(... AS DATE)`)

### Changed
| File | Change |
|---|---|
| `config.py` | Removed all DB-config; database lives in `core/dbDetails.py` |
| `core/database.py` | pyodbc-only; `call_procedure()` uses `{call NAME(?,?,...)}` syntax |
| `core/schema.py` | `init_database()` only creates `Pipeline_Runs` (UI-specific); production tables are server-managed |
| `app.py` | All queries: `LIMIT 500` → `TOP 500`; `LIMIT ? OFFSET ?` → `OFFSET ... FETCH NEXT`; `date(...)` → `CAST(... AS DATE)`; `CIK LIKE ?` → `CAST(CIK AS NVARCHAR(50)) LIKE ?` |
| `mailer/notifier.py` | `date('now')` → SQL Server equivalent |
| `import_data.py` | Docstring + status-string updates |
| `main.py` | `--init-db` description updated to reflect SQL Server |

---

## Phase 2 — Stored Procedures Only (no-UPDATE rule)

### Added — `core/sp_gate.py`

Universal helper that enforces the project rule **"never UPDATE existing rows"**:

```python
gate = SPGate(db, logger)
status = gate.call_if_absent(
    exists_sql="SELECT 1 FROM wk_SummaryComp WHERE Company_ID=? AND FiscalYear=? AND OfficerName=?",
    exists_params=[cid, fy, name],
    sp_name="sp_wk_SummaryComp_IU_MAYA",
    sp_params=[...],  # 18 params
    scope_label="SCT MongoDB FY2026 Chirantan Desai",
)
# status ∈ {'Parsed', 'Already Exist', 'Not Parsed'}
```

If the existence check returns a row, **the SP is NOT called** — even though the SP's internal `IF NOT EXISTS / ELSE` would have done the same thing, doing the check Python-side guarantees the UPDATE branch can never fire under any race condition or future SP modification.

### Changed — 5 parsers now call production SPs

| Parser | SPs called via gate | Existence check |
|---|---|---|
| `parsers/sql_parser.py` (SCT) | `sp_wk_SummaryComp_IU_MAYA` (18 params), `sp_wk_SummaryComp_U_MAYA` (16), `sp_Officer_FirstLastName_U_MAYA` (10), `sp_Tracking_Data_Entry_U_MAYA` (9) | per officer + per company |
| `parsers/equity_parser.py` | `sp_Outstanding_Equity_Awards_IU_MAYA` (13) | per (Company_ID + FiscalYear + Officer_ID) |
| `parsers/exercise_parser.py` | `sp_ExerciseandVested_U_MAYA` (13) | per (Officer_ID + FY) with all-4-cols-null check |
| `parsers/pba_parser.py` | `sp_wk_PlanBasedAward_U_MAYA` (23) | per (Company_ID + FiscalYear + Officer_ID) |
| `parsers/dct_parser.py` | `sp_GenerateDirector_MAYA` (18) | per (Company_ID + FiscalYear + Director_Name) |

### Removed
- All raw `INSERT INTO ...` / `UPDATE ... SET` calls inside parsers — replaced with `gate.call_if_absent(...)` to the corresponding SP

---

## Phase 3 — DCT wiring (was unrunnable)

Before this change, `dct_parse` was listed in `config.PIPELINE_STEPS` and shown to users in the React `Pipeline.js`, but was missing from `pipeline.runner.STEP_REGISTRY` — clicking "Run dct_parse" raised `PipelineError("Unknown step: dct_parse")`.

### Changed
- `pipeline/runner.py` — added `'dct_parse': ('parsers.dct_parser', 'DCTParser')` to `STEP_REGISTRY` and inserted `'dct_parse'` between `'pba_parse'` and `'send_mail'` in `DEFAULT_ORDER`
- `app.py::/api/module-output/dct` — added DCT branch returning `BOD_DirectorComp` rows joined to `Company` + `Maya_Parsing_Summary`

---

## Phase 4 — Status concept fixes

### Bug — `'No Table Found'` (capital F) vs `'No Table found'` (lowercase)

The parser writes `'No Table found'`. Queries in `app.py`, `mailer/notifier.py`, `import_data.py`, and `frontend/.../Dashboard.js` filtered for the capital-F version → dashboard always showed 0 for that bucket.

**Fixed:** unified to `'No Table found'` everywhere queries run.

### Bug — `'Already Exist'` never written

`parsers/data_entry.py` silently skipped duplicate Links. The React dashboard had a badge for `'Already Exist'` but no code path ever set the status.

**Fixed:** `data_entry.py` now `UPDATE Maya_Parsing_Summary SET SCT_Parsed = 'Already Exist'` when Link is found (matches production `SCT_module/maya_data_entry.py` behavior). Added `parsing_already_exist` stat to `/api/stats` + stat card to `Dashboard.js`.

### Added — canonical status strings

Defined in `core/sp_gate.py`:
- `STATUS_PARSED = "Parsed"`
- `STATUS_ALREADY_EXIST = "Already Exist"`
- `STATUS_NOT_PARSED = "Not Parsed"`
- `STATUS_NO_TABLE = "No Table found"`

---

## Phase 5 — Maya_Parsing_Summary INSERT alignment

Production `SCT_module/maya_data_entry.py:159` writes 22 columns including `DCT_Parsed` and uses `[bracketed]` column names. The UI fork wrote 20 columns, missing `DCT_Parsed` + `FilingType`.

**Fixed:** `parsers/data_entry.py::_insert_row()` now writes the same 22 columns in production order.

---

## Phase 6 — FastAPI hygiene

### Removed
- `@app.on_event("startup")` (deprecated) → modern `@asynccontextmanager lifespan`
- `ctypes.pythonapi.PyThreadState_SetAsyncExc(SystemExit)` thread-force-kill (data corruption risk against production DB) → cooperative stop flag only
- CORS `allow_origins=["*"]` with `allow_credentials=True` (browser-rejected anti-pattern) → env-configurable list (`MAYA_CORS_ORIGINS`)
- Hardcoded MSSQL credentials in `config.py` (plaintext password committed) → `.env`

### Changed
- `Pipeline_Runs` "stale running cleanup" on startup now scoped to this process's `PROCESS_ID` so multiple FastAPI instances don't clobber each other
- `app.py` `delete_all_data` includes warning that it deletes from PRODUCTION tables

---

## Phase 7 — UI alignment to production columns

Every `/api/module-output/{module}` endpoint now returns columns whose names match what the production stored procedures write. SCT shows `wk_SummaryComp`, Equity shows `Officer_Outstanding_Equity`, Exercise shows `Officer.{Option,Stock}_{Shares,Value}_*`, PBA shows `Officer_Awards`, DCT shows `BOD_DirectorComp`.

This means the UI tables look exactly like the click-app screens (Officer.aspx, OutstandingEquityAwards.aspx, etc.).

---

## Phase 8 — Documentation added (`docs/`)

| File | Purpose |
|---|---|
| `docs/SP_Definitions_raw.md` | `sp_helptext` dump of all 13 `*_MAYA` SPs |
| `docs/SP_Behavior_Analysis.md` | Per-SP analysis of INSERT vs UPDATE branches + required Python gate for each |
| `docs/CHANGES.md` | This file |

External reference docs (in the production project): `docs/Maya_Modules_Deep_Dive.md`, `docs/Maya_Pipeline_SP_Reference.md`.

---

## Files changed — full list

```
.env.example                                  (new)
CLAUDE.md                                     (new)
config.py                                     (rewritten — DB config removed)
core/database.py                              (rewritten — pyodbc only)
core/dbDetails.py                             (new — .env loader)
core/schema.py                                (rewritten — Pipeline_Runs only)
core/sp_gate.py                               (new — SPGate helper)
docs/CHANGES.md                               (new)
docs/SP_Behavior_Analysis.md                  (new)
docs/SP_Definitions_raw.md                    (new — auto-generated)
app.py                                        (modified)
main.py                                       (modified)
import_data.py                                (modified — docstrings)
mailer/notifier.py                            (modified — date(), status states)
parsers/data_entry.py                         (modified — Already Exist, DCT_Parsed, [bracketed] cols)
parsers/sql_parser.py                         (rewritten — SP gate, 4 SPs per officer)
parsers/equity_parser.py                      (modified — INSERT → sp_Outstanding_Equity_Awards_IU_MAYA)
parsers/exercise_parser.py                    (modified — UPDATE → sp_ExerciseandVested_U_MAYA with gate)
parsers/pba_parser.py                         (modified — INSERT → sp_wk_PlanBasedAward_U_MAYA)
parsers/dct_parser.py                         (modified — INSERT → sp_GenerateDirector_MAYA)
pipeline/runner.py                            (modified — dct_parse wired into STEP_REGISTRY + DEFAULT_ORDER)
pipeline/state.py                             (modified — docstring)
frontend/src/pages/Dashboard.js               (modified — Already Exist stat card)
frontend/src/pages/ParsingSummary.js          (modified — No Table found case)
```

---

## Deleted

- `maya.db` (SQLite database file)
- All `proc_*` SQLite-equivalent functions in `core/schema.py` (production SPs are used instead via `db.call_procedure(...)`)

---

## Git branch flow

- **`main`** — production. Tagged releases only. Never push directly.
- **`test`** — staging. PRs from `dev` land here for QA.
- **`dev`** — active development. All work-in-progress lands here first.

All three branches were initialized at the same first commit. First push: `dev`.
