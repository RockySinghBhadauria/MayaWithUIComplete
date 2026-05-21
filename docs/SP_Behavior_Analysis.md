# Stored Procedure Behavior Analysis

**Purpose:** Document every SP the UI pipeline calls, the SP's internal behavior (insert vs update branches), and the Python-side existence gate required to comply with the project's **no-UPDATE rule**.

> **Project rule:** This pipeline only INSERTs new rows. Human users edit data through the click app — if Maya overwrites their edits, that's data loss. So **before calling any SP**, Python must `SELECT` to check whether the row already exists; if it does, set status to `Already Exist` and **skip the SP call entirely**.

> Companion file: [SP_Definitions_raw.md](SP_Definitions_raw.md) — full `sp_helptext` dumps.

## Quick reference table

| SP | Tables written | Internal behavior | Python gate (check before SP call) |
|---|---|---|---|
| `sp_Company_Finaicials_FiscalYear_End_IU_MAYA` | `Financials`, `Company_FiscalYear`, `Tracking_Data_Entry` | IF-NOT-EXISTS → INSERT; IF-EXISTS → UPDATE | `SELECT 1 FROM Financials WHERE Company_ID=? AND FiscalYear=?` |
| `sp_wk_SummaryComp_IU_MAYA` | `wk_SummaryComp` (+ Last_Officer_ID rollup) | IF NOT EXISTS → INSERT; ELSE → UPDATE | `SELECT 1 FROM wk_SummaryComp WHERE Company_ID=? AND FiscalYear=? AND OfficerName=?` |
| `sp_wk_SummaryComp_U_MAYA` | `Officer`, `Officer_Roles`, `Tracking_Data_Entry` | Cascading update of Officer rows | `SELECT 1 FROM Officer WHERE Company_ID=? AND FiscalYear=? AND OfficerName=?` |
| `sp_Officer_FirstLastName_U_MAYA` | `Officer` (name fields) | UPDATE only | Only call when Officer row was just inserted (no row → noop) |
| `sp_Officer_Roles_U_MAYA` | `Officer_Roles` | UPDATE only | `SELECT 1 FROM Officer_Roles WHERE Officer_ID=? AND FiscalYear=?` |
| `sp_Officer_PerfPeriod_Roles_U_MAYA` | `Officer_Roles` (perf period) | UPDATE only | Same as above |
| `sp_Tracking_Data_Entry_U_MAYA` | `Tracking_Data_Entry` | UPDATE only | Skip if `BoardPay_entered_Name` / `Perquisites_entered_Name` already set |
| `sp_Outstanding_Equity_Awards_IU_MAYA` | `Officer_Outstanding_Equity`, `Company_FiscalYear` | If `@OE_ID IS NULL` → INSERT; else → UPDATE | `SELECT 1 FROM Officer_Outstanding_Equity oe JOIN Officer o ON o.Officer_ID=oe.Officer_ID WHERE o.Company_ID=? AND o.FiscalYear=?` |
| `sp_ExerciseandVested_U_MAYA` | `Officer` (4 cols), `Notes_Comments`, `Company_FiscalYear` | UPDATE Officer unconditionally + INSERT note if new + UPDATE note if existing | `SELECT 1 FROM Officer WHERE Company_ID=? AND FiscalYear=? AND (Option_Shares_Acquired IS NOT NULL OR Stock_Shares_Acquired IS NOT NULL)` |
| `sp_wk_PlanBasedAward_U_MAYA` | `wk_PlanBasedAward`, `Officer_Awards` | UPDATE wk_ + (Officer_Awards_ID=0 → INSERT) or UPDATE | `SELECT 1 FROM Officer_Awards oa JOIN Officer o ON o.Officer_ID=oa.Officer_ID WHERE o.Company_ID=? AND o.FiscalYear=?` |
| `sp_GenerateDirector_MAYA` | `BOD_Director_FiscalYear`, `BOD_OtherBoards`, `BOD_Director_Committees`, `BOD_DirectorComp`, `Financials`, `Company_FiscalYear`, `Tracking_Data_Entry` | All INSERTs in a TRANSACTION; also has IF-NOT-EXISTS + IF-EXISTS UPDATE for Tracking | `SELECT 1 FROM BOD_Director_FiscalYear WHERE Company_ID=? AND FiscalYear=?` |
| `SP_Maya_Parsing_Company_Status` | _(read-only)_ | SELECT only — returns today's parsing summary | Safe to call any time |
| `sp_Set_True_Tracker_Feed_Def14` | `Tracker_Feed_Def14a` (sets `IsProcessed=1`) | UPDATE only | Only called after pipeline run completes |

---

## Why every SP has BOTH insert and update paths

The Maya SPs were originally written for the click app's **data-entry form**, where the same form may either create a new record OR edit an existing one (the `@*_ID` parameter being NULL vs not-NULL is what tells the SP which path to take). When the Maya **pipeline** also started calling these SPs, it inherited both branches even though it only ever wants the INSERT path.

This is why the no-UPDATE rule MUST be enforced from the **Python side** — the SPs themselves cannot tell whether the caller is a human user (who legitimately wants to UPDATE) or the Maya pipeline (which must never UPDATE human-edited data).

---

## Per-SP detailed analysis

### 1. `sp_Company_Finaicials_FiscalYear_End_IU_MAYA` (called from SCT parser)

**SP source:** [SP_Definitions_raw.md §sp_Company_Finaicials_FiscalYear_End_IU_MAYA](SP_Definitions_raw.md)

**Write targets:**
- `Financials` (INSERT if Company_ID+FiscalYear absent, else **UPDATE**)
- `Company_FiscalYear` (INSERT only)
- `Tracking_Data_Entry` (INSERT only)

**Risk:** If `Financials` row exists with human-edited `FiscalYearEnd`, calling this SP **WILL overwrite it**.

**Python gate required:**
```python
exists = db.fetch_one(
    "SELECT 1 FROM Financials WHERE Company_ID=? AND FiscalYear=?",
    [company_id, fiscal_year]
)
if exists:
    logger.info("Financials already exist for %s FY%s — skipping SP", company_id, fiscal_year)
    return "Already Exist"
db.call_procedure("sp_Company_Finaicials_FiscalYear_End_IU_MAYA",
                  [company_id, fiscal_year_end_date, fiscal_year, "MAYA"])
```

### 2. `sp_wk_SummaryComp_IU_MAYA` (called from SCT sql_parser, per officer)

**Internal:** `IF NOT EXISTS(... WHERE OfficerName + Company_ID + FiscalYear) → INSERT; ELSE → UPDATE`. The UPDATE branch overwrites every column.

**Risk:** Same officer parsed again → wk_SummaryComp UPDATE wipes any analyst edits to the staging row.

**Python gate (PER OFFICER):**
```python
exists = db.fetch_one(
    "SELECT 1 FROM wk_SummaryComp WHERE Company_ID=? AND FiscalYear=? AND OfficerName=?",
    [company_id, fiscal_year, officer_name]
)
if exists:
    continue  # don't call SP for this officer
db.call_procedure("sp_wk_SummaryComp_IU_MAYA", [Officer_ID, ParsedName, ...])  # 18 params
```

### 3. `sp_wk_SummaryComp_U_MAYA` (creates/updates Officer master)

**Internal:** All UPDATEs — merges wk_SummaryComp row into live `Officer` record.

**Python gate:**
```python
exists = db.fetch_one(
    "SELECT 1 FROM Officer WHERE Company_ID=? AND FiscalYear=? AND OfficerName=?",
    [company_id, fiscal_year, officer_name]
)
if exists:
    continue
```

### 4-6. Officer name/role SPs

All three (`sp_Officer_FirstLastName_U_MAYA`, `sp_Officer_Roles_U_MAYA`, `sp_Officer_PerfPeriod_Roles_U_MAYA`) are UPDATE-only against the `Officer` / `Officer_Roles` tables. They should only be called immediately after the corresponding Officer row is **newly inserted** by `sp_wk_SummaryComp_U_MAYA`. If the Officer row already existed (gate fired earlier), these are skipped.

### 7. `sp_Outstanding_Equity_Awards_IU_MAYA` (Equity)

**Internal:**
- Always UPDATEs `Company_FiscalYear.No_OEA_In_Proxy` (safe — that's a boolean we own).
- If `@Officer_Outstanding_Equity_ID IS NULL` → INSERT branch. If non-NULL → UPDATE branch.
- **The Maya pipeline always passes NULL**, so the INSERT branch is always taken — meaning this SP is INSERT-only as called from Maya. Safe.

**Python gate (per Company+FiscalYear, NOT per row):**
```python
# Check at company+FY level — if any equity rows exist for this filing, skip the whole company
exists = db.fetch_one(
    "SELECT 1 FROM Officer_Outstanding_Equity oe "
    "INNER JOIN Officer o ON o.Officer_ID = oe.Officer_ID "
    "WHERE o.Company_ID=? AND o.FiscalYear=?",
    [company_id, fiscal_year]
)
if exists:
    return "Already Exist"
# Otherwise loop over each parsed equity grant and call SP with @OE_ID=NULL
for grant in equity_grants:
    db.call_procedure("sp_Outstanding_Equity_Awards_IU_MAYA",
                      [None, company_id, fiscal_year, equity_type, officer_id, ...])  # 13 params
```

### 8. `sp_ExerciseandVested_U_MAYA` (Exercise)

**Internal:** `UPDATE Officer SET 4_cols WHERE Officer_ID + Company_ID + FiscalYear`. No insert path — needs Officer row to already exist (it always will, because SCT runs first).

**Risk:** Calling this on an Officer where a human already entered Option_Shares_Acquired etc. → overwrites.

**Python gate:**
```python
# If ALL 4 exercise cols are non-NULL, skip
existing = db.fetch_one(
    "SELECT Option_Shares_Acquired, Option_Value_Realized, "
    "       Stock_Shares_Acquired, Stock_Value_Realized "
    "FROM Officer WHERE Company_ID=? AND FiscalYear=?",
    [company_id, fiscal_year]
)
all_populated = existing and all(existing.get(c) is not None for c in [
    'Option_Shares_Acquired', 'Option_Value_Realized',
    'Stock_Shares_Acquired', 'Stock_Value_Realized'])
if all_populated:
    return "Already Exist"
db.call_procedure("sp_ExerciseandVested_U_MAYA", [...])  # 13 params
```

### 9. `sp_wk_PlanBasedAward_U_MAYA` (PBA)

**Internal:**
- UPDATE `wk_PlanBasedAward` WHERE `ID=@ID` (no-op when row doesn't exist — safe).
- If `@Officer_Awards_ID = 0 OR NULL` → INSERT into `Officer_Awards`. Else → UPDATE.
- **Maya always passes 0**, so INSERT branch always taken. Safe at the SP level.

**Python gate (per Company+FiscalYear):**
```python
exists = db.fetch_one(
    "SELECT 1 FROM Officer_Awards oa "
    "INNER JOIN Officer o ON o.Officer_ID = oa.Officer_ID "
    "WHERE o.Company_ID=? AND o.FiscalYear=?",
    [company_id, fiscal_year]
)
if exists:
    return "Already Exist"
for award in parsed_awards:
    db.call_procedure("sp_wk_PlanBasedAward_U_MAYA",
                      [None, None, 0, officer_id, company_id, fiscal_year, ...])  # 23 params
```

### 10. `sp_GenerateDirector_MAYA` (DCT)

**Internal:** All INSERTs wrapped in a `TRY`/`COMMIT/ROLLBACK TRANSACTION`. Five tables written per director (`BOD_Director_FiscalYear`, `BOD_OtherBoards`, `BOD_Director_Committees`, `BOD_DirectorComp`, plus conditional inserts to `Financials`, `Company_FiscalYear`, `Tracking_Data_Entry`). At the end, `Tracking_Data_Entry.BoardPay_entered_Name='MAYA'` UPDATE — risky if user already set it.

**Python gate (per Company+FiscalYear):**
```python
exists = db.fetch_one(
    "SELECT 1 FROM BOD_Director_FiscalYear WHERE Company_ID=? AND FiscalYear=?",
    [company_id, fiscal_year]
)
if exists:
    return "Already Exist"
for director in parsed_directors:
    db.call_procedure("sp_GenerateDirector_MAYA",
                      [director_name, 'M', company_id, fiscal_year, 0, 0, None, None, None,
                       None, None, fees, stock, options, all_other, total, None, fye])  # 18 params
```

### 11. `SP_Maya_Parsing_Company_Status` (read-only)

SELECT-only. Returns rows from `Maya_Parsing_Summary` for today. Safe to call freely (used by mailer + UI dashboard).

### 12. `sp_Set_True_Tracker_Feed_Def14` (post-run cleanup)

UPDATE-only — sets `Tracker_Feed_Def14a.IsProcessed=1` for completed runs. Called once at end of pipeline. Safe; this column is owned by Maya.

---

## Implementation pattern — `SPGate` helper

To keep the gate logic DRY across 5 parsers, the UI project will use a single helper:

```python
# core/sp_gate.py
class SPGate:
    """Enforces the no-UPDATE rule before any SP call."""
    def __init__(self, db, logger):
        self.db = db
        self.logger = logger

    def call_if_absent(self, exists_sql, exists_params, sp_name, sp_params, scope_label=""):
        """Returns 'Inserted', 'Already Exist', or raises on SP failure."""
        row = self.db.fetch_one(exists_sql, exists_params)
        if row:
            self.logger.info("%s: row already exists for %s, skipping SP %s",
                             scope_label, exists_params, sp_name)
            return "Already Exist"
        self.db.call_procedure(sp_name, sp_params)
        self.db.commit()
        return "Inserted"
```

Every parser calls `gate.call_if_absent(...)` instead of `db.call_procedure(...)` directly.

---

## Status string mapping (Maya_Parsing_Summary)

| Parser outcome | What gets written to `*_Parsed` column |
|---|---|
| Gate passed, SP succeeded | `Parsed` |
| Gate skipped SP (row already existed) | `Already Exist` |
| Module ran but target table not found in HTML | `No Table found` |
| Module ran but parse/SP raised | `Not Parsed` |
| Module not yet reached | `NULL` (initial seed) |

---

## What gets deleted by `deletecompany.py` (re-run support)

Per the project rule, **DELETE is allowed for re-testing**. The cleanup script (scoped to Company_ID + FiscalYear) clears:

| Table | Cleared by |
|---|---|
| `wk_SummaryComp` | DELETE WHERE Company_ID + FiscalYear |
| `Officer_Outstanding_Equity` | DELETE via Officer join |
| `Officer_Awards` | DELETE via Officer join |
| `Officer` (4 exercise cols only — NULLed, NOT row delete) | UPDATE Officer SET 4_cols = NULL |
| `BOD_Director_FiscalYear`, `BOD_DirectorComp`, `BOD_OtherBoards`, `BOD_Director_Committees`, `Director` | DELETE WHERE Company_ID + FiscalYear |
| `Maya_Parsing_Summary` | DELETE WHERE Company_ID + FiscalYear (so all gates reset) |
| `Financials`, `Company_FiscalYear`, `Tracking_Data_Entry` | **NOT deleted** — preserves human edits |

After cleanup, all `Already Exist` gates will return false on the next run, so the pipeline can re-INSERT cleanly.
