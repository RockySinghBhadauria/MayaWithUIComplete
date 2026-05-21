"""
base_parser.py
Abstract base class for all MAYA parsers.
"""

from abc import ABC, abstractmethod
from core.logging_config import get_logger


class BaseParser(ABC):
    """Abstract base class for all MAYA parsers."""

    def __init__(self, db, logger_name=None):
        """
        Parameters
        ----------
        db : core.database.DatabaseManager
            Active database connection manager.
        logger_name : str, optional
            Name for the logger; defaults to the concrete class name.
        """
        self.db = db
        self.logger = get_logger(logger_name or self.__class__.__name__)
        self._pipeline_state = None  # Set by PipelineRunner
        self._step_name = None       # Set by PipelineRunner
        self._progress = {'processed': 0, 'parsed': 0, 'failed': 0}

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def run(self):
        """Execute this parser step. Returns dict with status info."""
        pass

    # ------------------------------------------------------------------
    # Shared helper queries
    # ------------------------------------------------------------------

    def get_company_id(self, company_name):
        """Look up Company_ID from Company table by name.

        Returns
        -------
        int or None
            The Company_ID if found, otherwise ``None``.
        """
        row = self.db.fetch_one(
            "SELECT Company_ID, CompanyName FROM Company WHERE CompanyName=?",
            [company_name],
        )
        return row["Company_ID"] if row else None

    def get_company_by_cik(self, cik):
        """Look up a company row by CIK number.

        Returns
        -------
        dict or None
            Full company row as a dict, or ``None`` when not found.
        """
        return self.db.fetch_one(
            "SELECT Company_ID, CompanyName, CIK, Symbol, Fortune_1000, "
            "Russell_3000, MDG_Client, Peer_Of_An_MDG_Client, SP_400, "
            "SP_500, SP_600, PM_Client, Peer_of_PM_Client, Priority "
            "FROM Company WHERE CIK=? ORDER BY UpdateDate DESC",
            [int(cik)],
        )

    def check_already_parsed(self, link):
        """Check if a filing link already exists in Maya_Parsing_Summary.

        Returns
        -------
        bool
            ``True`` when the link is already present.
        """
        row = self.db.fetch_one(
            "SELECT Company_ID FROM Maya_Parsing_Summary WHERE Link=?",
            [link],
        )
        return row is not None

    def should_stop(self):
        """Check if pipeline stop was requested."""
        import builtins
        return getattr(builtins, '_maya_stop_pipeline', False)

    def report_progress(self, processed=None, parsed=None, failed=None):
        """Report progress to the pipeline UI (updates counts in real-time)."""
        if processed is not None:
            self._progress['processed'] = processed
        if parsed is not None:
            self._progress['parsed'] = parsed
        if failed is not None:
            self._progress['failed'] = failed
        if self._pipeline_state and self._step_name:
            self._pipeline_state.update_progress(
                self._step_name,
                self._progress['processed'],
                self._progress['parsed'],
                self._progress['failed'],
            )

    def update_parsing_status(self, company_id, fiscal_year, field, status):
        """Update a single parsing-status field in Maya_Parsing_Summary.

        Parameters
        ----------
        company_id : int
        fiscal_year : int
        field : str
            Column name to update (caller is responsible for valid names).
        status : str
            New value for the column.
        """
        query = (
            "UPDATE Maya_Parsing_Summary SET {}=? "
            "WHERE Company_ID=? AND FiscalYear=?"
        ).format(field)
        self.db.execute(query, [status, company_id, fiscal_year])
        self.db.commit()
