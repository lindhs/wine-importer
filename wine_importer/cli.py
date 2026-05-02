from pathlib import Path

import typer

from .export import export_reviewed_matches
from .io import read_json, write_json
from .models import MatchResult, MappedWineRow, NormalizedWineRow
from .normalize import normalize_mapped_rows
from .pipeline import run_pipeline
from .report import export_review_report, print_review_report
from .review import review_matches
from .score import rank_candidates
from .search import find_candidate_records_with_diagnostics, load_canonical_wines
from .parse import inspect_input

app = typer.Typer(help="wine-importer CLI for canonicalizing wine spreadsheets")


def _serialize_match_row(row: NormalizedWineRow) -> dict:
    return {
        key: value
        for key, value in row.model_dump().items()
        if not key.startswith("normalized_")
    }


def _match_metrics(candidates) -> dict:
    top_1_score = candidates[0].score if candidates else None
    top_2_score = candidates[1].score if len(candidates) > 1 else None
    return {
        "top_1_score": top_1_score,
        "top_2_score": top_2_score,
        "score_margin": (
            top_1_score - top_2_score
            if top_1_score is not None and top_2_score is not None
            else None
        ),
        "num_candidates": len(candidates),
    }


@app.command()
def inspect(
    input_path: str,
    delimiter: str | None = typer.Option(
        None, "--delimiter", "-d", help="Delimiter for CSV/TSV input"
    ),
    sheet_name: str | None = typer.Option(
        None, "--sheet-name", help="Excel sheet name or index"
    ),
    use_ai: bool = typer.Option(
        False,
        "--use-ai",
        help="Enable AI features: semantic schema mapping, AI file parsing, semantic scoring.",
    ),
    all_sheets: bool = typer.Option(
        False,
        "--all-sheets",
        help="Scan all Excel sheets and combine detected wine tables.",
    ),
    ocr: bool = typer.Option(
        False,
        "--ocr",
        help="Enable optional OCR for image inputs when OCR dependencies are installed.",
    ),
) -> None:
    """Read CSV/TSV/XLSX and print detected columns, row count, and sample rows."""
    inspect_input(
        input_path,
        delimiter=delimiter,
        sheet_name=sheet_name,
        use_ai=use_ai,
        all_sheets=all_sheets,
        ocr=ocr,
    )


@app.command()
def run(
    input_path: str,
    canonical: str = typer.Option(..., help="Canonical wine CSV file"),
    out_dir: str = typer.Option("runs/example", help="Output run directory"),
    delimiter: str | None = typer.Option(
        None, "--delimiter", "-d", help="Delimiter for CSV/TSV input"
    ),
    sheet_name: str | None = typer.Option(
        None, "--sheet-name", help="Excel sheet name or index"
    ),
    use_ai: bool = typer.Option(
        False,
        "--use-ai",
        help="Enable AI features: semantic schema mapping, AI file parsing, semantic scoring.",
    ),
    export_review_needed: bool = typer.Option(
        False,
        "--export-review-needed",
        help="Export review_needed rows using the current best canonical candidate.",
    ),
    export_rejected_as_unmatched: bool = typer.Option(
        False,
        "--export-rejected-as-unmatched",
        help="Export rejected rows as unmatched user-entered wines.",
    ),
    all_sheets: bool = typer.Option(
        False,
        "--all-sheets",
        help="Scan all Excel sheets and combine detected wine tables.",
    ),
    include_quarantine: bool = typer.Option(
        False,
        "--include-quarantine",
        help="Include quarantined ingestion rows in review/report artifacts.",
    ),
    ocr: bool = typer.Option(
        False,
        "--ocr",
        help="Enable optional OCR for image inputs when OCR dependencies are installed.",
    ),
) -> None:
    """Run the full import pipeline and emit staged artifacts."""
    run_pipeline(
        input_path,
        canonical,
        out_dir,
        delimiter=delimiter,
        sheet_name=sheet_name,
        use_ai=use_ai,
        export_review_needed=export_review_needed,
        export_rejected_as_unmatched=export_rejected_as_unmatched,
        all_sheets=all_sheets,
        include_quarantine=include_quarantine,
        ocr=ocr,
    )


@app.command()
def normalize(mapped_json: str, out: str) -> None:
    """Normalize a mapped JSON artifact into normalized JSON."""
    rows = read_json(mapped_json)
    mapped_rows = [MappedWineRow(**row) for row in rows]
    normalized = normalize_mapped_rows(mapped_rows)
    write_json([row.model_dump() for row in normalized], out)
    typer.echo(f"Normalized rows written to {out}")


@app.command()
def match(normalized_json: str, canonical: str, out: str) -> None:
    """Match normalized rows against a canonical CSV and write candidate matches."""
    rows = read_json(normalized_json)
    normalized_rows = [NormalizedWineRow(**row) for row in rows]
    canonical_wines = load_canonical_wines(canonical)
    match_results: list[MatchResult] = []
    for row in normalized_rows:
        search_results = find_candidate_records_with_diagnostics(row, canonical_wines)
        candidates = [result.wine for result in search_results]
        blocking_reasons = {
            result.wine.id: result.blocking_reason
            for result in search_results
        }
        ranked = rank_candidates(row, candidates, blocking_reasons=blocking_reasons)
        metrics = _match_metrics(ranked)
        match_results.append(
            MatchResult(
                row_number=row.row_number,
                user_row=_serialize_match_row(row),
                candidates=ranked,
                **metrics,
            )
        )
    write_json([result.model_dump() for result in match_results], out)
    typer.echo(f"Candidate matches written to {out}")


@app.command()
def review(matches_json: str, out: str) -> None:
    """Review candidate matches and write reviewed match artifacts."""
    matches = read_json(matches_json)
    reviewed = review_matches(matches)
    write_json([review.model_dump() for review in reviewed], out)
    typer.echo(f"Reviewed matches written to {out}")


@app.command()
def export(
    reviewed_json: str,
    out: str,
    export_review_needed: bool = typer.Option(
        False,
        "--export-review-needed",
        help="Export review_needed rows using the current best canonical candidate.",
    ),
    export_rejected_as_unmatched: bool = typer.Option(
        False,
        "--export-rejected-as-unmatched",
        help="Export rejected rows as unmatched user-entered wines.",
    ),
) -> None:
    """Export reviewed matches to a CellarTracker-ready CSV."""
    reviewed = read_json(reviewed_json)
    export_reviewed_matches(
        reviewed,
        out,
        export_review_needed=export_review_needed,
        export_rejected_as_unmatched=export_rejected_as_unmatched,
    )
    typer.echo(f"Exported CellarTracker file to {out}")


@app.command()
def report(
    reviewed_json: str,
    out: str | None = typer.Option(
        None,
        "--out",
        help="Comparison CSV path. Defaults to 09_match_report.csv beside reviewed_json.",
    ),
    status: str | None = typer.Option(
        None,
        "--status",
        help="Optional status filter: accepted, review_needed, or rejected.",
    ),
    limit: int = typer.Option(20, "--limit", help="Rows to print in the terminal preview."),
) -> None:
    """Write and preview a row-by-row match comparison report."""
    reviewed = read_json(reviewed_json)
    if status:
        allowed_statuses = {"accepted", "review_needed", "rejected"}
        if status not in allowed_statuses:
            raise typer.BadParameter(f"status must be one of {sorted(allowed_statuses)}")
        reviewed = [record for record in reviewed if record.get("status") == status]

    output_path = Path(out) if out else Path(reviewed_json).with_name("09_match_report.csv")
    export_review_report(reviewed, output_path)
    print_review_report(reviewed, status=None, limit=limit)
    typer.echo(f"Match comparison report written to {output_path}")
