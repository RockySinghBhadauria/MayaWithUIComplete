"""HTML table extraction utilities.

Provides two extraction strategies:
* ``extract_table_data`` -- simple cell-text extraction (fast, no span handling).
* ``extract_table_with_spans`` -- full colspan / rowspan expansion using the
  defaultdict pattern from the original SCT, Equity, and PBA parsers.
"""
from collections import defaultdict

from core.logging_config import get_logger

logger = get_logger('table_extractor')


def extract_table_data(table_tag):
    """Extract a table into a list of lists (simple, no span handling).

    Parameters
    ----------
    table_tag : bs4.element.Tag
        A ``<table>`` element from BeautifulSoup.

    Returns
    -------
    list[list[str]]
        Each inner list is one row of cell text values.
    """
    rows = []
    for tr in table_tag.find_all('tr'):
        row = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
        rows.append(row)
    return rows


def extract_table_with_spans(table_tag):
    """Extract a table with full colspan / rowspan support.

    Uses a ``defaultdict(lambda: defaultdict(str))`` grid so that spanned
    cells are correctly duplicated into the positions they cover.

    Parameters
    ----------
    table_tag : bs4.element.Tag
        A ``<table>`` element from BeautifulSoup.

    Returns
    -------
    list[list[str]]
        A rectangular list-of-lists with spans expanded.
    """
    # Grid keyed by (row_index, col_index) -> cell text
    grid = defaultdict(lambda: defaultdict(str))

    all_trs = table_tag.find_all('tr')
    for row_idx, tr in enumerate(all_trs):
        col_idx = 0
        for cell in tr.find_all(['td', 'th']):
            # Advance past columns already filled by a previous rowspan
            while grid[row_idx][col_idx] != '':
                col_idx += 1

            text = cell.get_text(strip=True)

            colspan = int(cell.get('colspan', 1) or 1)
            rowspan = int(cell.get('rowspan', 1) or 1)

            for dr in range(rowspan):
                for dc in range(colspan):
                    grid[row_idx + dr][col_idx + dc] = text

            col_idx += colspan

    if not grid:
        return []

    # Determine dimensions
    max_row = max(grid.keys()) + 1
    max_col = 0
    for r in range(max_row):
        if grid[r]:
            candidate = max(grid[r].keys()) + 1
            if candidate > max_col:
                max_col = candidate

    # Build the rectangular output
    result = []
    for r in range(max_row):
        row = [grid[r][c] for c in range(max_col)]
        result.append(row)

    return result
