# MayaWithUIComplete

UI-enabled Maya pipeline — parses SEC DEF 14A proxy filings into SQL Server. React frontend + FastAPI backend.

Sibling to the headless production Maya pipeline (`OfficeProjects/NewProductionMaya/Maya`); both write to the same SQL Server.

---

## Repository layout

```
.
├── backend/                  # Python — FastAPI + pipeline + parsers
│   ├── app.py                # FastAPI server (port 5000)
│   ├── main.py               # CLI entry point
│   ├── config.py
│   ├── requirements.txt
│   ├── .env.example          # copy to .env, fill in DB credentials
│   ├── core/                 # database, sp_gate, logging, schema, exceptions
│   ├── parsers/              # rss/sct/sql/data_entry/equity/exercise/pba/dct
│   ├── pipeline/             # runner + state
│   ├── mailer/               # daily summary email
│   ├── utils/                # csv_manager, html_fetcher, officer_matcher, ...
│   ├── docs/                 # CHANGES.md, SP_Behavior_Analysis.md, SP_Definitions_raw.md
│   ├── data/                 # one-off seed CSVs (mssql_company_export, mssql_role_export)
│   └── logs/<year>/          # production-style runtime artifacts (gitignored)
│       ├── filing_dump/      # per-company L1/L2/L3 CSVs (SCT/Equity/Exercise/PBA/DCT)
│       ├── sct_metadata_dump/<month>/   # daily edgar_feed + module *_Parsed_transactions
│       └── runs/             # maya_YYYYMMDD.log files
│
├── frontend/                 # React 19 (CRA) — port 3000 in dev
│   ├── package.json
│   ├── public/
│   └── src/
│       ├── App.js, api.js
│       └── pages/{Dashboard,Pipeline,Companies,Officers,ParsingSummary,Logs}.js
│
├── CLAUDE.md                 # AI assistant handover guide (read first)
├── README.md                 # this file
└── .gitignore
```

The `logs/<year>/` structure mirrors the production Maya project exactly, so the same `deletecompany.py` / verification queries / log-reading habits transfer.

---

## Quick start

### Backend

```bash
cd backend
cp .env.example .env             # fill in DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD
pip install -r requirements.txt
python main.py --init-db         # creates Pipeline_Runs table on SQL Server
python app.py                    # → http://localhost:5000
```

### Frontend

```bash
cd frontend
npm install
npm start                        # → http://localhost:3000 (proxies API to :5000)
```

### Run the pipeline

Via UI: open http://localhost:3000 → **Pipeline** tab → **Run All**.

Via CLI:
```bash
cd backend
python main.py --list-steps      # see all 9 steps
python main.py                   # run all
python main.py --step sct_parse  # run one step
python main.py --from equity_parse
```

---

## Project rules (non-negotiable — see CLAUDE.md)

1. **No UPDATE** — pipeline only INSERTs. Humans edit data via the click app (.NET MDG_Entry).
   Existence checks live in `backend/core/sp_gate.py::SPGate.call_if_absent()`.
2. **DELETE is allowed** for re-running/testing (`/api/data/today`, `/api/data/all`).
3. **Production tables are server-managed** — never `CREATE TABLE` on them. Only `backend/core/schema.py::PIPELINE_RUNS_DDL` runs DDL.
4. **Status strings (case-sensitive):** `Parsed`, `Already Exist`, `Not Parsed`, `No Table found` (lowercase `f` in `found`).

---

## Git branches

| Branch | Purpose |
|--------|---------|
| `main` | Production. Tag releases here. Never push directly. |
| `test` | Staging. PRs from `dev` land here for QA. |
| `dev`  | Active development. All work-in-progress lands here first. |

Flow: `dev` → PR → `test` → QA → PR → `main`.

GitHub: <https://github.com/RockySinghBhadauria/MayaWithUIComplete>

---

## Documentation

| File | Purpose |
|------|---------|
| `CLAUDE.md` | AI assistant handover — rules, layout, what NOT to do |
| `backend/docs/CHANGES.md` | Full change log |
| `backend/docs/SP_Behavior_Analysis.md` | Per-SP analysis + Python gate rationale |
| `backend/docs/SP_Definitions_raw.md` | `sp_helptext` dumps of every `*_MAYA` SP |
