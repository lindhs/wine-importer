from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from .ingest import IngestionResult, ingest_file, raw_rows_from_ingestion
from .models import RawRow
from .table_detect import StructuredInput

console = Console()


def read_ingested_input_file(
    path: str | Path,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    use_ai: bool = False,
    all_sheets: bool = False,
    ocr: bool = False,
) -> IngestionResult:
    return ingest_file(
        path,
        delimiter=delimiter,
        sheet_name=sheet_name,
        use_ai=use_ai,
        all_sheets=all_sheets,
        ocr=ocr,
    )


def read_structured_input_file(
    path: str | Path,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    use_ai: bool = False,
) -> StructuredInput:
    return read_ingested_input_file(
        path,
        delimiter=delimiter,
        sheet_name=sheet_name,
        use_ai=use_ai,
    ).to_structured_input()


def read_input_file(
    path: str | Path,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    use_ai: bool = False,
) -> pd.DataFrame:
    return read_structured_input_file(
        path,
        delimiter=delimiter,
        sheet_name=sheet_name,
        use_ai=use_ai,
    ).dataframe


def inspect_input(
    path: str | Path,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    use_ai: bool = False,
    all_sheets: bool = False,
    ocr: bool = False,
) -> pd.DataFrame:
    ingested = read_ingested_input_file(
        path,
        delimiter=delimiter,
        sheet_name=sheet_name,
        use_ai=use_ai,
        all_sheets=all_sheets,
        ocr=ocr,
    )
    df = ingested.dataframe.fillna("")
    table = Table(title=f"Preview: {path}")
    for column in df.columns:
        table.add_column(column, overflow="fold")
    sample = df.head(5).fillna("")
    for _, row in sample.iterrows():
        table.add_row(*[str(value) for value in row.tolist()])

    console.print(table)
    console.print(f"[bold]Columns:[/bold] {len(df.columns)}")
    console.print(f"[bold]Rows:[/bold] {len(df)}")
    console.print(
        "[bold]Detected tables:[/bold] "
        f"selected={len(ingested.selected_regions)} "
        f"skipped={len(ingested.skipped_regions)} "
        f"quarantine={len(ingested.quarantine_items)}"
    )
    if ingested.selected_regions:
        confidences = ", ".join(
            f"{region.confidence:.2f}" for region in ingested.selected_regions
        )
        console.print(f"[bold]Structure confidence:[/bold] {confidences}")
    for warning in ingested.warnings:
        console.print(f"[yellow]{warning}[/yellow]")
    return df


def raw_rows_from_structured_input(
    structured: StructuredInput | IngestionResult,
    source_file: str,
) -> list[RawRow]:
    if isinstance(structured, IngestionResult):
        return raw_rows_from_ingestion(structured, source_file)
    return raw_rows_from_ingestion(
        IngestionResult(
            dataframe=structured.dataframe,
            detected_regions=[],
            quarantine_items=[],
            warnings=structured.warnings,
            source_row_numbers=structured.source_row_numbers,
            table_indices=structured.table_indices,
            field_evidence={},
            sheet_name=structured.sheet_name,
        ),
        source_file,
    )


def load_raw_rows(
    path: str | Path,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    use_ai: bool = False,
) -> list[RawRow]:
    structured = read_structured_input_file(
        path,
        delimiter=delimiter,
        sheet_name=sheet_name,
        use_ai=use_ai,
    )
    return raw_rows_from_structured_input(structured, str(Path(path).name))


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
