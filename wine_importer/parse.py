import csv
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from .ai_parser import ai_parse_file
from .models import RawRow

console = Console()

DELIMITER_CANDIDATES = ",;\t|"


def _detect_delimiter(path: Path, default: str) -> str:
    try:
        sample = path.read_text(encoding="utf-8", errors="ignore")[:8192]
    except OSError:
        return default

    if not sample.strip():
        return default

    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITER_CANDIDATES).delimiter
    except csv.Error:
        return default


def read_input_file(
    path: str | Path,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    use_ai: bool = False,
) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        if sheet_name is None:
            return pd.read_excel(path, dtype=str, engine="openpyxl")
        return pd.read_excel(path, dtype=str, engine="openpyxl", sheet_name=sheet_name)
    if suffix == ".json":
        return pd.read_json(path)
    if use_ai and suffix not in {".csv", ".tsv", ".txt", ".json", ""}:
        return ai_parse_file(path)

    if delimiter is None and suffix in {".csv", ".tsv", ".txt", ""}:
        default_delimiter = "\t" if suffix == ".tsv" else ","
        delimiter = _detect_delimiter(path, default_delimiter)

    try:
        return pd.read_csv(path, dtype=str, sep=delimiter or ",")
    except Exception:
        if use_ai:
            return ai_parse_file(path)
        raise


def inspect_input(
    path: str | Path,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    use_ai: bool = False,
) -> pd.DataFrame:
    df = read_input_file(
        path,
        delimiter=delimiter,
        sheet_name=sheet_name,
        use_ai=use_ai,
    ).fillna("")
    table = Table(title=f"Preview: {path}")
    for column in df.columns:
        table.add_column(column, overflow="fold")
    sample = df.head(5).fillna("")
    for _, row in sample.iterrows():
        table.add_row(*[str(value) for value in row.tolist()])

    console.print(table)
    console.print(f"[bold]Columns:[/bold] {len(df.columns)}")
    console.print(f"[bold]Rows:[/bold] {len(df)}")
    return df


def load_raw_rows(
    path: str | Path,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    use_ai: bool = False,
) -> list[RawRow]:
    df = read_input_file(
        path,
        delimiter=delimiter,
        sheet_name=sheet_name,
        use_ai=use_ai,
    ).fillna("")
    source_file = str(Path(path).name)
    rows: list[RawRow] = []
    for index, record in enumerate(df.to_dict(orient="records"), start=1):
        record_str = {str(key): str(value).strip() for key, value in record.items()}
        rows.append(RawRow(source_file=source_file, row_number=index, data=record_str))
    return rows


def save_raw_copy(
    path: str | Path,
    output_path: str | Path,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    use_ai: bool = False,
) -> None:
    df = read_input_file(
        path,
        delimiter=delimiter,
        sheet_name=sheet_name,
        use_ai=use_ai,
    ).fillna("")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
