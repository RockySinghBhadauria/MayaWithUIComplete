"""
Fuzzy officer name matching utilities.

Replaces the 10+ duplicate implementations of officer fuzzy-matching
scattered across parser modules.
"""

from fuzzywuzzy import fuzz


def match_officer(parsed_name, officer_list, threshold=55):
    """Find best matching officer name from list using fuzz.partial_ratio.

    Args:
        parsed_name: The officer name string extracted from a filing.
        officer_list: Iterable of known officer name strings to match against.
        threshold: Minimum partial_ratio score to accept. Defaults to 55.

    Returns:
        Tuple of (matched_name, score) if a match meets the threshold,
        otherwise (None, 0).
    """
    best_match = None
    best_score = 0
    parsed_clean = str(parsed_name).lower().strip().replace("'", "")
    for officer_name in officer_list:
        officer_clean = str(officer_name).lower().strip().replace("'", "")
        score = fuzz.partial_ratio(parsed_clean, officer_clean)
        if score > best_score:
            best_score = score
            best_match = officer_name
    if best_score >= threshold:
        return best_match, best_score
    return None, 0


def get_officer_id(db, officer_name, company_id, fiscal_year):
    """Look up Officer_ID from database for a matched name.

    Args:
        db: Database connection object exposing a ``fetch_one`` method that
            accepts a parameterized query and returns a dict-like row.
        officer_name: Exact officer name to look up.
        company_id: Company_ID value.
        fiscal_year: FiscalYear value.

    Returns:
        The Officer_ID integer if found, otherwise None.
    """
    result = db.fetch_one(
        "SELECT Officer_ID, Company_ID, FiscalYear FROM Officer "
        "WHERE Company_ID=? AND FiscalYear=? AND OfficerName=?",
        [company_id, fiscal_year, officer_name]
    )
    if result:
        return result['Officer_ID']
    return None


def get_company_officers(db, company_id, fiscal_year):
    """Get list of officer names for a company/fiscal year.

    Args:
        db: Database connection object exposing a ``fetch_all`` method.
        company_id: Company_ID value.
        fiscal_year: FiscalYear value.

    Returns:
        List of OfficerName strings.
    """
    rows = db.fetch_all(
        "SELECT OfficerName FROM Officer WHERE Company_ID=? AND FiscalYear=?",
        [company_id, fiscal_year]
    )
    return [r['OfficerName'] for r in rows]
