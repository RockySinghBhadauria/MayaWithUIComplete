"""
Role dictionary and matching logic.

Extracted from SQL_parser_server_v3.py lines 48-165. Provides the canonical
72-role dictionary, priority ordering, and fuzzy matching against officer
designation strings.
"""

from collections import defaultdict

from fuzzywuzzy import fuzz

# ---------------------------------------------------------------------------
# Role dictionary: Role_ID -> list of matching titles
# ---------------------------------------------------------------------------
ROLE_DICT = defaultdict(list)
ROLE_DICT[0] = ['All Roles']
ROLE_DICT[1] = [
    'Chairman', 'Chairman of the board', 'Board Vice Chair',
    'Executive Chairman', 'of the Board',
]
ROLE_DICT[2] = ['CEO', 'Executive Officer', 'Chief Executive Officer']
ROLE_DICT[3] = ['President']
ROLE_DICT[4] = ['CFO', 'Financial Officer', 'Chief Financial Officer']
ROLE_DICT[5] = ['Top Division Executive']
ROLE_DICT[6] = ['Treasurer']
ROLE_DICT[7] = [
    'Chief Accounting Officer', 'Chief Controller Officer',
    'Chief Finance Officer',
]
ROLE_DICT[8] = ['COO', 'Operating Officer', 'Chief Operating Officer']
ROLE_DICT[9] = [
    'Human Resources Officer', 'H & R Officer',
    'Chief Human Resources Officer', 'HR',
]
ROLE_DICT[10] = ['Marketing', 'Sales Director', 'Sales Lead']
ROLE_DICT[11] = [
    'General Counsel', 'General Counsel (Chief Legal/Compliance)',
    'Chief Legal Officer', 'Chief Compliance Officer',
]
ROLE_DICT[12] = [
    'CLO/CCO (Lending/Credit)', 'Chief Lending Officer',
    'Chief Credit Officer',
]
ROLE_DICT[13] = ['Technology']
ROLE_DICT[14] = ['Unspecified']
ROLE_DICT[15] = [
    'Other', 'Client Officer', 'President of Technology',
    'Risk Management Services', "Federal Gov't Affairs", 'Project Manager',
    'Global Specialty Products', 'Global Co Head of Corporate Finance', '0',
]
ROLE_DICT[41] = ['Secretary']
ROLE_DICT[42] = ['Employee Director']
ROLE_DICT[43] = ['Sample Executive']
ROLE_DICT[44] = [
    'EVP', 'Executive Vice President', 'Executive VP', 'E.V.P.', 'Ex. VP',
]
ROLE_DICT[45] = [
    'SVP', 'Senior Vice President', 'Senior VP', 'S.V.P.', 'Sr. VP',
]
ROLE_DICT[46] = ['CTO', 'Technology Officer', 'Chief Technology Officer']
ROLE_DICT[47] = ['CMO', 'Medical Officer', 'Chief Medical Officer']
ROLE_DICT[48] = [
    'CAO', 'Administrative Officer', 'Chief Administrative Officer',
]
ROLE_DICT[49] = ['CIO', 'Chief Information Officer']
ROLE_DICT[50] = ['Chief Strategy Officer']
ROLE_DICT[51] = ['Chief Science Officer']
ROLE_DICT[52] = ['Business Dev Lead']
ROLE_DICT[53] = [
    'R VP', 'Ping Vice President', 'V.P.',
    'Vice President Secretary', 'Vice President Sales',
    'Vice President Engineering', 'VP Finance', 'Corporate VP',
    'Vice President Finance', 'Vice President of Sales',
    'Former Vice President', 'Former VP', 'Vice President General',
    'Vice President Water Treatment', 'Vice President Health and Nutrition',
    'Vice President Real Estate', 'Vice President Human Resources',
    'Vice President Sales', 'Vice President Engineering',
    'Vice President Mergers', 'Vice President Marketing',
    'Vice President Distribution', 'Vice President Customer',
]
ROLE_DICT[54] = ['All']
ROLE_DICT[55] = ['All Other Named Executive Officers']
ROLE_DICT[56] = ['None']
ROLE_DICT[57] = ['CIO', 'Investment Officer', 'Chief Investment Officer']
ROLE_DICT[58] = ['Board Vice Chairman']
ROLE_DICT[59] = ['Operations']
ROLE_DICT[60] = ['Chief Risk Officer']
ROLE_DICT[61] = [
    'Role Vice Chairman', 'Former Vice Chairman',
    'Vice Chairman Technology', 'Vice Chairman Operating',
    'Vice Chairman Wealth',
]
ROLE_DICT[62] = ['Subsidiary']
ROLE_DICT[63] = ['of bank Subsidiary']
ROLE_DICT[64] = [
    'Other Chief', 'Chief Commercial Officer',
    'Chief Agricultural Officer', 'Chief Acquisitions Officer',
    'Chief Product Officer', 'Chief Merchandising Officer',
    'Chief Digital Officer', 'Chief Supply Chain', 'GBS Officer',
    'Chief Privacy Officer', 'Chief Consumer Officer',
    'Chief Sales Officer', 'Chief Operations Officer',
    'Chief Revenue Officer', 'Consumer Segment Executive',
    'Wholesale Segment Executive', 'Chief Innovation Officer',
    'Chief Banking Officer', 'Chief Business Officer',
    'Chief Growth Officer',
]
ROLE_DICT[65] = ['Research & Development']
ROLE_DICT[66] = ['Managing Director']
ROLE_DICT[67] = ['Partner']
ROLE_DICT[68] = ['Professor']
ROLE_DICT[69] = ['Principal']
ROLE_DICT[70] = ['Managing Member']
ROLE_DICT[71] = ['Selected']

# ---------------------------------------------------------------------------
# Priority ordering (from SQL_parser_server_v3.py lines 160-165)
# ---------------------------------------------------------------------------
ROLE_PRIORITY_IDS = [
    54, 55, 2, 1, 58, 3, 61, 62, 63, 48, 4, 49, 57, 12, 47, 8, 50, 60,
    51, 46, 64, 5, 65, 52, 41, 59, 7, 11, 9, 10, 13, 6, 44, 45, 53, 42,
    43, 0, 15, 56, 14, 66, 67, 68, 69, 70, 71,
]

ROLE_SORT_KEYS = [
    5, 7, 10, 20, 30, 40, 42, 44, 46, 50, 60, 70, 80, 90, 100, 110, 120,
    125, 130, 140, 145, 150, 155, 160, 170, 175, 180, 190, 200, 210, 220,
    230, 240, 250, 260, 270, 280, 300, 320, 330, 340, 350, 360, 370, 380,
    390, 400,
]

ROLE_PRIORITY = {
    ROLE_SORT_KEYS[i]: ROLE_PRIORITY_IDS[i]
    for i in range(len(ROLE_SORT_KEYS))
}


def match_role(designation_text, threshold=100):
    """Match a designation string to Role_ID(s) using fuzzy matching.

    Args:
        designation_text: Raw designation/title string from a filing.
        threshold: Minimum ``fuzz.partial_ratio`` score to accept a match.
            Defaults to 100 (exact substring match).

    Returns:
        List of ``(role_id, score)`` tuples sorted by role priority.
        Falls back to ``[(14, 0)]`` (Unspecified) when nothing matches.
    """
    if not designation_text:
        return [(14, 0)]  # Unspecified

    matches = []
    for role_id, role_names in ROLE_DICT.items():
        for role_name in role_names:
            score = fuzz.partial_ratio(
                designation_text.lower(), role_name.lower(),
            )
            if score >= threshold:
                matches.append((role_id, score))
                break

    if not matches:
        return [(14, 0)]  # Unspecified

    # Sort by priority order defined in ROLE_PRIORITY_IDS
    matches.sort(
        key=lambda x: (
            ROLE_PRIORITY_IDS.index(x[0])
            if x[0] in ROLE_PRIORITY_IDS
            else 999
        ),
    )
    return matches


def get_role_name(role_id):
    """Get the primary (first) role name for a Role_ID.

    Args:
        role_id: Integer role identifier.

    Returns:
        The canonical role name string, or ``'Unknown'`` if the ID is not
        in the dictionary.
    """
    names = ROLE_DICT.get(role_id, ['Unknown'])
    return names[0] if names else 'Unknown'
