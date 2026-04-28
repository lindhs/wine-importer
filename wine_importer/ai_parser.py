import csv
from io import StringIO
from pathlib import Path

import pandas as pd

DELIMITERS = ",;\t|"


def ai_parse_file(path: str | Path) -> pd.DataFrame:
    """Fallback parser for unsupported or unstructured files.

    This handles text-like table and key/value inputs without image/OCR support.
    Truly unstructured inputs fall back to a single raw_text column.
    """
    path = Path(path)
    file_text = path.read_text(encoding="utf-8", errors="ignore")
    table = _parse_delimited_text(file_text)
    if table is not None:
        return table
    key_value_rows = _parse_key_value_blocks(file_text)
    if key_value_rows:
        return pd.DataFrame(key_value_rows)
    return pd.DataFrame([{"raw_text": file_text}])


def _parse_delimited_text(file_text: str) -> pd.DataFrame | None:
    sample = file_text[:8192]
    if not sample.strip():
        return None

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=DELIMITERS)
        has_header = csv.Sniffer().has_header(sample)
    except csv.Error:
        return None

    if not has_header:
        return None

    try:
        df = pd.read_csv(StringIO(file_text), dtype=str, sep=dialect.delimiter).fillna("")
    except Exception:
        return None

    if len(df.columns) <= 1 or df.empty:
        return None
    return df


def _parse_key_value_blocks(file_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in file_text.splitlines():
        line = raw_line.strip()
        if not line:
            if len(current) >= 2:
                rows.append(current)
            current = {}
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            current[key] = value

    if len(current) >= 2:
        rows.append(current)
    return rows
