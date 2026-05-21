"""Generic table scoring using fuzzy keyword matching.

Implements the pattern shared by the SCT, Equity, Exercise, and PBA parsers:
extract header text from a table, build a bag of words, and score against a
list of expected keywords using ``fuzzywuzzy.fuzz.ratio``.
"""
import copy

from fuzzywuzzy import fuzz


def classify_table(table_tag):
    """Classify a table as SCT, EQUITY, EXERCISE, PBA, or UNKNOWN."""
    text = table_tag.get_text(separator=' ', strip=True).lower()
    text = text.replace('\xa0', ' ').replace('\u200b', '').replace('\n', ' ')

    has_salary = 'salary' in text
    has_name_principal = 'name' in text and ('principal' in text or 'position' in text)
    has_total = 'total' in text
    has_exercisable = 'exercisable' in text
    has_unexercisable = 'unexercisable' in text
    has_unvested = 'unvested' in text
    has_acquired_vesting = 'acquired' in text and ('vesting' in text or 'vested' in text)
    has_realized = 'realized' in text
    has_threshold = 'threshold' in text
    has_target = 'target' in text
    has_maximum = 'maximum' in text
    has_grant_plan = 'grant' in text and 'plan' in text
    has_exercise_price = 'exercise' in text and 'price' in text
    has_expiration = 'expiration' in text

    if has_salary and has_name_principal and has_total and not has_exercisable and not has_acquired_vesting:
        return 'SCT'
    if has_exercisable and (has_unexercisable or has_unvested or has_exercise_price or has_expiration):
        return 'EQUITY'

    # EQUITY alternate: "outstanding" + "stock awards" + ("option" or "shares" or "units")
    has_outstanding = 'outstanding' in text
    has_stock_awards = 'stock award' in text or 'stock awards' in text
    has_option_awards = 'option award' in text or 'option awards' in text
    has_units = 'unit' in text or 'shares' in text
    has_restricted = 'restricted' in text or 'rsu' in text or 'psu' in text
    has_vested_not = 'not vested' in text or 'have not vested' in text

    if has_outstanding and (has_stock_awards or has_option_awards) and not has_salary:
        return 'EQUITY'
    if has_unvested and (has_units or has_restricted) and not has_salary and not has_acquired_vesting:
        return 'EQUITY'
    if has_vested_not and has_units and not has_salary:
        return 'EQUITY'

    if has_acquired_vesting and has_realized and not has_exercisable:
        return 'EXERCISE'

    # EXERCISE alternate: "shares acquired" + "value realized"
    if 'shares acquired' in text and 'value realized' in text:
        return 'EXERCISE'
    if 'number of shares' in text and 'value realized' in text and not has_salary:
        return 'EXERCISE'
    if has_threshold and has_target and has_maximum:
        return 'PBA'

    # PBA alternate: estimated payouts + incentive plan
    has_estimated = 'estimated' in text
    has_payouts = 'payout' in text
    has_incentive_plan = 'incentive plan' in text
    if has_estimated and has_payouts and has_incentive_plan:
        return 'PBA'

    # PBA alternate: grant date + fair value + (stock or option)
    if 'grant date' in text and 'fair value' in text and ('stock' in text or 'option' in text):
        if not has_salary and not has_exercisable:
            return 'PBA'

    # PBA alternate: grant + plan + award + target
    if has_grant_plan and has_target and not has_salary and not has_exercisable:
        return 'PBA'

    return 'UNKNOWN'

import config
from core.logging_config import get_logger

logger = get_logger('table_scorer')


def score_table(table_tag, search_keywords, threshold=None):
    """Score a table against a list of search keywords.

    The function works on a **deep copy** of *table_tag* so the caller's
    tree is not mutated (superscript tags are removed during scoring).

    Parameters
    ----------
    table_tag : bs4.element.Tag
        A ``<table>`` element from BeautifulSoup.
    search_keywords : list[str]
        Keywords expected in the table headers (e.g. ``['salary', 'bonus']``).
    threshold : int, optional
        Minimum ``fuzz.ratio`` to consider a match.  Defaults to
        ``config.FUZZY_TABLE_THRESHOLD`` (80).

    Returns
    -------
    tuple(int, list[str])
        ``(score, matched_keywords)`` where *score* is the number of
        keywords matched and *matched_keywords* lists them.
    """
    if threshold is None:
        threshold = config.FUZZY_TABLE_THRESHOLD

    # Work on a copy so we don't destroy the caller's soup tree
    table_copy = copy.copy(table_tag)

    # Remove superscript text (footnote markers)
    for sup in table_copy.find_all('sup'):
        sup.decompose()

    # Build bag of words from the table text
    text = table_copy.get_text(separator=' ', strip=True).lower()
    words = text.split()

    score = 0
    matched = []

    for keyword in search_keywords:
        kw_lower = keyword.lower()
        for word in words:
            if fuzz.ratio(kw_lower, word) >= threshold:
                score += 1
                matched.append(keyword)
                break

    logger.debug(
        'Table scored %d/%d keywords matched (threshold=%d)',
        score, len(search_keywords), threshold,
    )
    return score, matched
