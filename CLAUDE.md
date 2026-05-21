# CLAUDE.md — Project guide for AI assistants

> If you're an AI assistant (Claude Code, Cursor, etc.) reading this — start here. This file explains what the project does, the rules you MUST follow, and what to verify before making changes.

## What this project is

**MayaWithUIComplete** is a React + FastAPI front-end for the Maya pipeline (parses SEC DEF 14A proxy filings into a SQL Server database). It is a sibling project to the headless Maya production pipeline (`OfficeProjects/NewProductionMaya/Maya`). Both projects write to the **same** SQL Server.

- **Backend:** Python 3.10+, FastAPI on port 5000
- **Frontend:** React 19 (CRA) — proxied to backend in dev, served as static from `frontend/build/` in prod
- **Database:** SQL Server (Microsoft), via pyodbc. No SQLite. No SQLAlchemy.
- **Production tables:** `Company`, `Officer`, `wk_SummaryComp`, `Officer_Outstanding_Equity`, `Officer_Awards`, `Director`, `BOD_DirectorComp`, `BOD_Director_FiscalYear`, `BOD_OtherBoards`, `BOD_Director_Committees`, `Maya_Parsing_Summary`, `Maya_BOD_Parsing_Summary`. These are **DBA-managed** — never `CREATE TABLE` on them.
- **UI-owned table:** `Pipeline_Runs` (only one in this project's `core/schema.py`)

## The five modules

The pipeline has 5 parsing modules, run in this order:

1. **SCT** (Summary Compensation Table) — `parsers/sct_parser.py` + `parsers/sql_parser.py`
2. **Equity** (Outstanding Equity Awards) — `parsers/equity_parser.py`
3. **Exercise** (Option Exercises & Stock Vested) — `parsers/exercise_parser.py`
4. **PBA** (Plan-Based Awards) — `parsers/pba_parser.py`
5. **DCT** (Director Compensation Table) — `parsers/dct_parser.py`

Each module reads SEC HTML, extracts a table, then calls a SQL Server stored procedure to insert rows. **No module updates existing rows.**

## The non-negotiable rules

These rules are enforced by code (`core/sp_gate.py`) AND by convention. **Read them before you change anything.**

### Rule 1: No UPDATE ever

The pipeline only INSERTs new rows. **Humans edit data through the click app** (the .NET MDG_Entry web app); if Maya overwrites their edits, that's data loss.

Every Maya stored procedure (`sp_*_MAYA`) has BOTH `INSERT` and `UPDATE` branches inside (this is because the SPs were originally written for the click app's data-entry form). The pipeline MUST gate every SP call with a Python-side existence check; if the row already exists, **skip the SP entirely** and mark status `Already Exist`.

This rule is enforced by `core.sp_gate.SPGate.call_if_absent()` — always use it, never call `db.call_procedure(...)` directly.

### Rule 2: DELETE is allowed (for re-runs)

If you need to re-run the pipeline against a company (e.g. to test a parser fix), you can DELETE rows for that `Company_ID + FiscalYear`. The production project has a `deletecompany.py` script as reference; this project's `/api/data/today` and `/api/data/all` endpoints expose the same capability.

After delete → re-run → SPGate sees the rows are absent → SPs are called → rows are re-inserted.

### Rule 3: Production tables are server-managed

Never write `CREATE TABLE Company (...)` or similar in this project. The DBAs own those schemas. The only DDL in this project is `core/schema.py::PIPELINE_RUNS_DDL` (and even that uses `IF NOT EXISTS`).

### Rule 4: Status strings are case-sensitive

Use these EXACT strings (defined in `core/sp_gate.py`):
- `"Parsed"` — SP succeeded
- `"Already Exist"` — gate found existing row, SP skipped
- `"Not Parsed"` — SP raised an exception
- `"No Table found"` — module ran but couldn't find the target table in HTML (NOTE: lowercase `f` in `found`)

`"No Table Found"` (capital F) is a bug — there was a case-mismatch between parser writes and query reads that has been fixed throughout. Do not re-introduce it.

## How to use Claude (or any AI) on this project

### Before you edit anything

1. **Read `docs/SP_Behavior_Analysis.md`** — explains which SPs UPDATE which tables and what existence check each one needs.
2. **Read `docs/CHANGES.md`** — recent changes + why.
3. **Confirm `.env` exists** — copy from `.env.example` and fill in SQL Server credentials.

### When asking Claude to modify the pipeline

Always say: *"This project has a no-UPDATE rule. Use `core.sp_gate.SPGate.call_if_absent()` for every database write. Don't add raw `INSERT INTO ...` or `UPDATE ... SET` statements."*

If Claude suggests writing raw SQL writes, reject the suggestion and remind it of the rule.

### Pattern Claude should follow for any new SP call

```python
from core.sp_gate import SPGate, STATUS_PARSED

if not hasattr(self, '_sp_gate'):
    self._sp_gate = SPGate(self.db, self.logger)

status = self._sp_gate.call_if_absent(
    exists_sql="SELECT 1 FROM <target_table> WHERE <unique_key>",
    exists_params=[<key_values>],
    sp_name="sp_<Name>_MAYA",
    sp_params=[<param_list_in_exact_SP_order>],
    scope_label="<module>:<company> FY<year> <officer/director>",
)
if status == STATUS_PARSED:
    inserted_count += 1
```

Look up the SP's parameter order in `docs/SP_Definitions_raw.md`.

### When asking Claude to add a new parser

Tell Claude:
1. Subclass `parsers.base_parser.BaseParser`
2. Use `core.sp_gate.SPGate` for all DB writes
3. Look up the target SP in `docs/SP_Behavior_Analysis.md`
4. Register the new parser in `pipeline/runner.py::STEP_REGISTRY` AND add to `DEFAULT_ORDER`
5. Add UI route in `app.py::/api/module-output/{module}` so the frontend can show the rows

### What Claude should NOT do

- Don't generate `CREATE TABLE` for production tables
- Don't add SQLite fallback or any second DB backend
- Don't use `LIMIT N` (SQLite syntax) — use `TOP N` or `OFFSET ... FETCH NEXT` (SQL Server)
- Don't use `date('now')` (SQLite) — use `CAST(GETDATE() AS DATE)` (SQL Server)
- Don't bypass `SPGate` for writes
- Don't force-kill threads with `ctypes.PyThreadState_SetAsyncExc` (data corruption risk)
- Don't commit `.env` (use `.env.example` template)

## Project layout

```
.
├── .env.example              # template — copy to .env
├── CLAUDE.md                 # this file
├── app.py                    # FastAPI backend (port 5000)
├── config.py                 # paths + SMTP + parsing thresholds (no DB config — that's in core/dbDetails.py)
├── main.py                   # CLI entry: --init-db, --step, --from, --list-steps
├── import_data.py            # one-off: seed Company table from production-project CSVs
├── core/
│   ├── dbDetails.py          # connection string from .env
│   ├── database.py           # pyodbc wrapper
│   ├── schema.py             # ONLY Pipeline_Runs DDL (UI-specific)
│   ├── sp_gate.py            # SPGate.call_if_absent — the no-UPDATE rule enforcer
│   ├── logging_config.py
│   └── exceptions.py
├── parsers/
│   ├── base_parser.py        # ABC with lookup helpers
│   ├── rss_parser.py         # step 1: EDGAR RSS → edgar_feed CSV
│   ├── sct_parser.py         # step 2: HTML → L3 CSV
│   ├── data_entry.py         # step 3: CSV → Maya_Parsing_Summary
│   ├── sql_parser.py         # step 4: L3 CSV → wk_SummaryComp + Officer (SCT body)
│   ├── equity_parser.py      # step 5
│   ├── exercise_parser.py    # step 6
│   ├── pba_parser.py         # step 7
│   └── dct_parser.py         # step 8
├── pipeline/
│   ├── runner.py             # STEP_REGISTRY + DEFAULT_ORDER (see for the canonical step list)
│   └── state.py              # Pipeline_Runs table writes
├── mailer/
│   ├── notifier.py           # daily HTML email of today's parsing summary
│   └── templates.py
├── ui/                       # (empty stubs — actual UI is in frontend/)
├── frontend/                 # React 19 SPA (CRA)
│   ├── package.json
│   └── src/
│       ├── App.js            # sidebar layout, 6 routes
│       ├── api.js            # axios client
│       └── pages/{Dashboard,Pipeline,Companies,Officers,ParsingSummary,Logs}.js
├── utils/                    # csv_manager, html_fetcher, officer_matcher, table_extractor, etc.
├── data/                     # metadata_dump/ + filing_dump/ (CSVs per company)
├── logs/                     # one file per day
└── docs/
    ├── CHANGES.md            # every recent change explained
    ├── SP_Behavior_Analysis.md   # per-SP analysis + gate rationale
    └── SP_Definitions_raw.md     # sp_helptext dumps
```

## Running the project locally

```bash
# 1. Setup
cp .env.example .env
# Edit .env — fill in DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD

pip install -r requirements.txt

# 2. Initialize UI-specific tables (Pipeline_Runs)
python main.py --init-db

# 3. Start backend
python app.py
# → http://localhost:5000

# 4. (in another shell) start frontend dev server
cd frontend
npm install
npm start
# → http://localhost:3000 (proxies API calls to :5000)
```

## Running the pipeline

Via UI: open http://localhost:3000 → Pipeline page → Run All.

Via CLI:
```bash
python main.py --list-steps          # see all 9 steps
python main.py                       # run all
python main.py --step sct_parse      # run one step
python main.py --from equity_parse   # run from step onwards
```

## Reference projects

When in doubt about SP parameters or parser logic, consult these reference projects (same team, working code):

- **`OfficeProjects/zipandothers/Maya_11032026/Maya_11032026`** — original Maya pipeline. Canonical SP-call patterns for SCT, Equity, Exercise, PBA.
- **`OfficeProjects/NewProductionMaya/Maya`** — current production pipeline. Latest bug fixes.
  - `docs/Maya_Modules_Deep_Dive.md` — end-to-end module reference
  - `docs/Maya_Pipeline_SP_Reference.md` — full SP parameter tables
- **`Maya/MDG-MAYA-main`** — DCT module reference. `DCT_module/DCT_parser_server.py:919` has the canonical `sp_GenerateDirector_MAYA` call.

## Git workflow

- **`main`** — production. Tag releases here.
- **`test`** — staging.
- **`dev`** — active development. Push here first.

Branches were initialized at the same first commit. The flow is `dev` → PR → `test` → QA → PR → `main`.

## Known limitations (handover notes)

1. **SP param order is fragile.** If a production DBA modifies an SP's parameter list, the parsers will break with cryptic errors. Always re-check `docs/SP_Definitions_raw.md` after any DB migration.
2. **Officer auto-insert is gone.** Older parser code auto-inserted into `Officer` when the SP couldn't find a match. The production `Officer` table is now treated as read-only outside of the SCT SPs that own it. If `Equity`/`Exercise`/`PBA` can't find an officer, they skip (instead of creating phantom rows).
3. **No FY-overwrite-from-SCT-table logic** yet. RSS-derived `FiscalYear` (filing_year - 1) wins. If the SCT table itself has a different year (e.g. MongoDB filed May 2026 with FY2026 columns), the DB ends up with `FiscalYear=2025`. Port from `OfficeProjects/zipandothers/Maya_11032026/Maya_11032026/SCT_module/SCT_table_parser_server_v1.py:944-989` if needed.
4. **Logging is single-process flat-file.** No per-module/per-company structured logs like the production project's `maya_logging.py`. Port if observability matters.
