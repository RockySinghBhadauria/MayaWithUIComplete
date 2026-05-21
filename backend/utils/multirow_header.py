"""
multirow_header.py — Handle SEC filing tables with multi-row headers.

SEC compensation tables often have headers split across 3-6 rows:
  Row 0: empty
  Row 1: "Option Awards" | "Stock Awards"
  Row 2: "Number of" | "Number of" | "Market Value"
  Row 3: "Securities" | "Securities" | "of Shares"
  Row 4: "Exercisable" | "Unexercisable" | "Unvested"

This module merges them into single composite column names like:
  "Option Awards Number of Securities Exercisable"
"""
import re
import pandas as pd
import numpy as np


def merge_multirow_headers(df, max_header_rows=8):
    """Detect and merge multi-row headers into single column names.

    Returns (new_df, header_names) where new_df has the header rows removed
    and proper column names.
    """
    if df.empty or len(df) < 3:
        return df, list(df.columns)

    # Find where data starts — look for rows with actual names (not header text)
    # A data row has a person's name (short text, no keywords like "award", "option", "stock")
    header_keywords = {'name', 'principal', 'position', 'award', 'option', 'stock', 'equity',
                       'exercise', 'price', 'securities', 'shares', 'grant', 'date', 'expiration',
                       'threshold', 'target', 'maximum', 'payout', 'incentive', 'plan', 'vested',
                       'compensation', 'salary', 'bonus', 'total', 'year', 'fiscal', 'number',
                       'market', 'value', 'estimated', 'future', 'non-equity', 'all other', 'unvested'}

    data_start = 0
    for i in range(min(max_header_rows, len(df))):
        row = df.iloc[i]
        row_text = ' '.join(str(v).lower().strip() for v in row if pd.notna(v))

        # Count numeric cells
        numeric_count = 0
        for val in row:
            s = str(val).strip().replace(',', '').replace('$', '').replace('(', '').replace(')', '').replace('—', '').replace('-', '')
            if s and re.match(r'^\d+\.?\d*$', s) and len(s) > 1:
                numeric_count += 1

        # Count header keyword matches
        keyword_count = sum(1 for kw in header_keywords if kw in row_text)

        # Data row: has 2+ numbers AND few header keywords
        if numeric_count >= 2 and keyword_count <= 2:
            data_start = i
            break
        # Also: if row has a date-like pattern (mm/dd/yy or name-like text with numbers)
        if numeric_count >= 3:
            data_start = i
            break
    else:
        data_start = min(max_header_rows, len(df) - 1)

    if data_start < 1:
        return df, list(df.columns)

    # Merge header rows top-down
    num_cols = len(df.columns)
    merged = ['' for _ in range(num_cols)]

    for row_idx in range(data_start):
        row = df.iloc[row_idx]
        for col_idx in range(min(len(row), num_cols)):
            val = str(row.iloc[col_idx]).strip()
            # Skip empty, NaN, index markers like (a)(b)(c)
            if not val or val == 'nan' or re.match(r'^\([a-z0-9]\)$', val):
                continue
            # Append to existing header
            if merged[col_idx]:
                merged[col_idx] += ' ' + val
            else:
                merged[col_idx] = val

    # Clean merged headers
    cleaned = []
    for h in merged:
        h = re.sub(r'\s+', ' ', h).strip()
        h = re.sub(r'[\(\)\$\d]+$', '', h).strip()  # Remove trailing ($) or numbers
        if not h:
            h = 'col_{}'.format(len(cleaned))
        cleaned.append(h)

    # Make unique
    seen = {}
    unique = []
    for h in cleaned:
        if h in seen:
            seen[h] += 1
            unique.append('{}_{}'.format(h, seen[h]))
        else:
            seen[h] = 0
            unique.append(h)

    # Create new DataFrame with data rows only
    new_df = df.iloc[data_start:].reset_index(drop=True)
    if len(unique) == len(new_df.columns):
        new_df.columns = unique

    return new_df, unique


def find_column_by_keywords(columns, keyword_groups):
    """Find columns matching keyword groups.

    keyword_groups: dict of {field_name: [list of keywords]}
    Returns: dict of {field_name: column_name}
    """
    result = {}
    used_cols = set()

    for field, keywords in keyword_groups.items():
        best_col = None
        best_score = 0
        for col in columns:
            if col in used_cols:
                continue
            col_lower = str(col).lower()
            score = 0
            for kw in keywords:
                if kw.lower() in col_lower:
                    score += 1
            if score > best_score:
                best_score = score
                best_col = col
        if best_col and best_score > 0:
            result[field] = best_col
            used_cols.add(best_col)

    return result
