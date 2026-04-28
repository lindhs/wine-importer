from pathlib import Path

from rich.console import Console

from .export import export_reviewed_matches
from .io import write_json
from .models import MatchResult
from .parse import load_raw_rows, save_raw_copy
from .review import review_matches
from .score import rank_candidates
from .schema_map import apply_schema_mapping, save_schema_mapping
from .search import find_candidate_records, load_canonical_wines
from .normalize import normalize_mapped_rows

console = Console()


def _serialize_models(items):
    serialized = []
    for item in items:
        if hasattr(item, "model_dump"):
            serialized.append(item.model_dump())
        else:
            serialized.append(item)
    return serialized


def run_pipeline(input_path: str, canonical_path: str, out_dir: str) -> dict[str, str]:
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    raw_copy_path = out_dir_path / "01_raw_copy.csv"
    parsed_path = out_dir_path / "02_parsed_rows.json"
    mapping_path = out_dir_path / "03_mapping.yaml"
    mapped_path = out_dir_path / "04_mapped_rows.json"
    normalized_path = out_dir_path / "05_normalized_rows.json"
    candidates_path = out_dir_path / "06_candidate_matches.json"
    reviewed_path = out_dir_path / "07_reviewed_matches.json"
    output_path = out_dir_path / "08_cellartracker_import.csv"

    console.print("[bold blue]Starting pipeline[/bold blue]")
    save_raw_copy(input_path, raw_copy_path)
    console.print(f"Saved raw copy to [green]{raw_copy_path}[/green]")

    raw_rows = load_raw_rows(input_path)
    write_json(_serialize_models(raw_rows), parsed_path)
    console.print(f"Saved parsed rows to [green]{parsed_path}[/green]")

    headers = list(raw_rows[0].data.keys()) if raw_rows else []
    mapping = save_schema_mapping(headers, mapping_path)
    console.print(f"Saved inferred mapping to [green]{mapping_path}[/green]")

    mapped_rows = apply_schema_mapping(raw_rows, mapping)
    write_json(_serialize_models(mapped_rows), mapped_path)
    console.print(f"Saved mapped rows to [green]{mapped_path}[/green]")

    normalized_rows = normalize_mapped_rows(mapped_rows)
    write_json(_serialize_models(normalized_rows), normalized_path)
    console.print(f"Saved normalized rows to [green]{normalized_path}[/green]")

    canonical_wines = load_canonical_wines(canonical_path)
    match_results: list[MatchResult] = []
    for row in normalized_rows:
        candidates = find_candidate_records(row, canonical_wines)
        ranked = rank_candidates(row, candidates)
        match_results.append(
            MatchResult(row_number=row.row_number, user_row=row.original, candidates=ranked)
        )
    write_json(_serialize_models(match_results), candidates_path)
    console.print(f"Saved candidate matches to [green]{candidates_path}[/green]")

    reviewed = review_matches([result.model_dump() for result in match_results])
    write_json(_serialize_models(reviewed), reviewed_path)
    console.print(f"Saved reviewed matches to [green]{reviewed_path}[/green]")

    export_reviewed_matches([record.model_dump() for record in reviewed], output_path)
    console.print(f"Exported CellarTracker import to [green]{output_path}[/green]")

    return {
        "raw_copy": str(raw_copy_path),
        "parsed": str(parsed_path),
        "mapping": str(mapping_path),
        "mapped": str(mapped_path),
        "normalized": str(normalized_path),
        "candidates": str(candidates_path),
        "reviewed": str(reviewed_path),
        "export": str(output_path),
    }
