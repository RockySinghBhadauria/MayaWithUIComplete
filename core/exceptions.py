"""Custom exception hierarchy for MAYA."""


class MayaError(Exception):
    """Base exception for all MAYA errors."""
    pass


class DatabaseError(MayaError):
    """Database connection or query error."""
    pass


class ParsingError(MayaError):
    """Error during HTML/table parsing."""
    pass


class TableNotFoundError(ParsingError):
    """No matching compensation table found in filing."""
    pass


class OfficerMatchError(ParsingError):
    """Failed to match officer name against database."""
    pass


class SECFetchError(MayaError):
    """Error fetching data from SEC EDGAR."""
    pass


class PipelineError(MayaError):
    """Pipeline step execution error."""
    pass
