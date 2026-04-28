from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from .models import RawRow

console = Console()


def read_input_file(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=str)
    return pd.read_csv(path, dtype=str)


def inspect_input(path: str | Path) -> pd.DataFrame:
    df = read_input_file(path).fillna("")
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


def load_raw_rows(path: str | Path) -> list[RawRow]:
    df = read_input_file(path).fillna("")
    rows: list[RawRow] = []
    for index, record in enumerate(df.to_dict(orient="records"), start=1):
        record_str = {str(key): str(value).strip() for key, value in record.items()}
        rows.append(RawRow(row_number=index, data=record_str))
    return rows


def save_raw_copy(path: str | Path, output_path: str | Path) -> None:
    df = read_input_file(path).fillna("")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
