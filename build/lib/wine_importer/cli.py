import typer

from .export import export_reviewed_matches
from .io import read_json, write_json
from .models import MatchResult, MappedWineRow, NormalizedWineRow
from .normalize import normalize_mapped_rows
from .pipeline import run_pipeline
from .review import review_matches
from .score import rank_candidates
from .search import find_candidate_records, load_canonical_wines
from .parse import inspect_input

app = typer.Typer(help="wine-importer CLI for canonicalizing wine spreadsheets")


@app.command()
def inspect(input_path: str) -> None:
    """Read CSV/XLSX and print detected columns, row count, and sample rows."""
    inspect_input(input_path)


@app.command()
def run(
    input_path: str,
    canonical: str = typer.Option(..., help="Canonical wine CSV file"),
    out_dir: str = typer.Option("runs/example", help="Output run directory"),
) -> None:
    """Run the full import pipeline and emit staged artifacts."""
    run_pipeline(input_path, canonical, out_dir)


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
        candidates = find_candidate_records(row, canonical_wines)
        ranked = rank_candidates(row, candidates)
        match_results.append(MatchResult(row_number=row.row_number, user_row=row.original, candidates=ranked))
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
def export(reviewed_json: str, out: str) -> None:
    """Export reviewed matches to a CellarTracker-ready CSV."""
    reviewed = read_json(reviewed_json)
    export_reviewed_matches(reviewed, out)
    typer.echo(f"Exported CellarTracker file to {out}")
