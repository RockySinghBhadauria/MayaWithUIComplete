"""
Header separation and column mapping utilities.

Centralizes the duplicated header-splitting logic from Equity, Exercise,
and PBA modules, plus fuzzy column-name mapping for DataFrame standardization.
"""

from boltons.setutils import IndexedSet
from fuzzywuzzy import fuzz


def separate_stuck_headers(columns, keywords):
    """Split concatenated header words using keyword list matching.

    Scans each column name for occurrences of known keywords and rebuilds
    the header as a space-separated string of matched keywords (preserving
    insertion order via IndexedSet).

    Args:
        columns: Iterable of raw column name strings.
        keywords: List of keyword strings to look for inside each column.

    Returns:
        List of cleaned column names (same length as *columns*).

    Example::

        >>> separate_stuck_headers(['equityincentiveplan'], ['equity', 'incentive', 'plan'])
        ['equity incentive plan']
    """
    result = []
    for col in columns:
        col_lower = str(col).lower().strip()
        found = IndexedSet()
        for kw in keywords:
            if kw.lower() in col_lower:
                found.add(kw)
        if found:
            result.append(' '.join(found))
        else:
            result.append(col)
    return result


def map_columns(df, mapping_rules, threshold=80):
    """Fuzzy-match DataFrame column names to standardized DB column names.

    Args:
        df: pandas DataFrame whose columns should be renamed.
        mapping_rules: Dict mapping a canonical name to a list of possible
            raw variants, e.g.::

                {
                    'Salary': ['salary', 'base salary', 'base pay'],
                    'Bonus':  ['bonus', 'annual bonus'],
                }

        threshold: Minimum ``fuzz.ratio`` score (0-100) to accept a match.
            Defaults to 80.

    Returns:
        A copy of *df* with columns renamed where a match was found.
        Columns that do not match any rule are left unchanged.
    """
    rename_map = {}
    for col in df.columns:
        col_lower = str(col).lower().strip()
        best_canonical = None
        best_score = 0
        for canonical_name, variants in mapping_rules.items():
            for variant in variants:
                score = fuzz.ratio(col_lower, variant.lower())
                if score > best_score:
                    best_score = score
                    best_canonical = canonical_name
        if best_score >= threshold and best_canonical is not None:
            rename_map[col] = best_canonical
    return df.rename(columns=rename_map)
