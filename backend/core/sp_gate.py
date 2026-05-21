"""SP Gate — enforces the project's no-UPDATE rule.

Project rule (from MEMORY.md): the pipeline only INSERTs new rows. Humans edit data
via the click app; if Maya overwrites their edits, that's data loss.

Every Maya stored procedure (`sp_*_MAYA`) has BOTH insert and update branches inside.
This helper requires you to provide an "exists" check; if the row already exists,
the SP is SKIPPED and we record 'Already Exist' status. The SP is only called when
the gate confirms the target row is absent.

Usage:
    from core.sp_gate import SPGate
    gate = SPGate(db, logger)
    status = gate.call_if_absent(
        exists_sql="SELECT 1 FROM wk_SummaryComp WHERE Company_ID=? AND FiscalYear=? AND OfficerName=?",
        exists_params=[company_id, fiscal_year, officer_name],
        sp_name="sp_wk_SummaryComp_IU_MAYA",
        sp_params=[officer_id, parsed_name, ..., role_id1],   # 18 params
        scope_label=f"SCT {company_name} {fiscal_year} {officer_name}",
    )
    # status is one of: 'Parsed' | 'Already Exist' | 'Not Parsed'
"""
from core.logging_config import get_logger

DEFAULT_LOGGER = get_logger('sp_gate')

STATUS_PARSED = "Parsed"
STATUS_ALREADY_EXIST = "Already Exist"
STATUS_NOT_PARSED = "Not Parsed"
STATUS_NO_TABLE = "No Table found"


class SPGate(object):
    """Calls a SQL Server stored procedure only when target row is absent.

    Compliant with the no-UPDATE rule: existence check is mandatory; SP is skipped
    when the row already exists.
    """

    def __init__(self, db, logger=None):
        self.db = db
        self.logger = logger or DEFAULT_LOGGER
        self.counters = {
            "inserted": 0,
            "already_exist": 0,
            "failed": 0,
        }

    def exists(self, exists_sql, exists_params):
        """Run the existence-check SELECT. Returns True if at least one row matched."""
        try:
            row = self.db.fetch_one(exists_sql, exists_params)
            return row is not None
        except Exception as e:
            self.logger.error(
                "Existence check failed (treating as not-exists is unsafe; raising). "
                "SQL=%s params=%s err=%s", exists_sql[:120], exists_params, e
            )
            raise

    def call_if_absent(self, exists_sql, exists_params, sp_name, sp_params, scope_label=""):
        """Check existence; if absent, call the SP and commit. Returns status string.

        Returns:
            "Parsed"         — gate passed, SP called, commit succeeded
            "Already Exist"  — gate found existing row, SP NOT called
            "Not Parsed"     — SP raised an exception (logged + counted, not re-raised
                               so the pipeline can continue on the next item)
        """
        try:
            if self.exists(exists_sql, exists_params):
                self.counters["already_exist"] += 1
                self.logger.info(
                    "[GATE-SKIP] %s | row exists for %s — skipping SP %s",
                    scope_label, exists_params, sp_name
                )
                return STATUS_ALREADY_EXIST
        except Exception:
            self.counters["failed"] += 1
            return STATUS_NOT_PARSED

        try:
            self.logger.info(
                "[GATE-INSERT] %s | calling SP %s with %d params",
                scope_label, sp_name, len(sp_params)
            )
            self.db.call_procedure(sp_name, sp_params)
            self.db.commit()
            self.counters["inserted"] += 1
            return STATUS_PARSED
        except Exception as e:
            self.counters["failed"] += 1
            self.logger.error(
                "[GATE-FAIL] %s | SP %s raised: %s | params=%s",
                scope_label, sp_name, e, sp_params, exc_info=True
            )
            try:
                self.db.rollback()
            except Exception:
                pass
            return STATUS_NOT_PARSED

    def summary(self):
        """Return human-readable summary of gate counters."""
        return "inserted={inserted}, already_exist={already_exist}, failed={failed}".format(
            **self.counters
        )

    def reset(self):
        for k in self.counters:
            self.counters[k] = 0
