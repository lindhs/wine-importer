import csv
import logging
from pathlib import Path

from rich.console import Console

from .config import (
    scoring_policy_manifest,
)
from .cellartracker_lookup import build_search_query, build_search_url
from .export import export_reviewed_matches
from .ai_runtime import load_project_env
from .ingest import quarantine_to_dataframe
from .io import write_json, write_yaml
from .models import MatchResult, ReviewedMatch
from .parse import (
    raw_rows_from_structured_input,
    read_ingested_input_file,
)
from .report import export_review_report
from .resolution_cache import DEFAULT_CACHE_PATH, ResolutionCache
from .review import review_matches
from .score import rank_candidates
from .schema_map import apply_schema_mapping, save_schema_mapping
from .search import find_candidate_records_with_diagnostics
from .normalize import normalize_mapped_rows
from .validation import (
    configure_logging,
    filter_empty_rows,
    assert_mapped_records_valid,
    log_pipeline_start,
    log_stage_complete,
    log_stage_start,
    validate_input_file,
    validate_schema_mapping,
)

logger = logging.getLogger(__name__)
console = Console()


def _serialize_models(items):
    serialized = []
    for item in items:
        if hasattr(item, "model_dump"):
            serialized.append(item.model_dump())
        else:
            serialized.append(item)
    return serialized


def _serialize_match_row(row) -> dict:
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


def _assess_input_quality(raw_rows) -> dict:
    sample_data = [row.data for row in raw_rows[:5]]
    if not sample_data:
        return {"skipped": True, "reason": "No rows parsed"}

    try:
        from .ai_schema import assess_input_quality_with_ai

        return assess_input_quality_with_ai(sample_data)
    except Exception as exc:
        logger.warning("AI input quality assessment failed: %s", exc)
        return {"error": str(exc)}


def run_pipeline(
    input_path: str,
    out_dir: str,
    ct_cache: str | None = None,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    use_ai: bool = False,
    export_review_needed: bool = False,
    export_rejected_as_unmatched: bool = False,
    all_sheets: bool = False,
    include_quarantine: bool = False,
    ocr: bool = False,
) -> dict[str, str]:
    """
    Run the full wine-importer pipeline with validation and AI enhancements.

    Args:
        input_path: Path to input wine data file
        out_dir: Output directory for artifacts
        ct_cache: Path to the CellarTracker resolution cache (the candidate
            source). Defaults to ~/.wine-importer/ct_cache.db.
        delimiter: Optional delimiter for CSV parsing
        sheet_name: Optional Excel sheet name
        use_ai: Enable AI-powered schema mapping and semantic scoring

    Returns:
        Dict mapping artifact names to file paths

    Raises:
        FileNotFoundError: Input file doesn't exist
        ValueError: Invalid data or schema
    """
    # Initialize logging
    configure_logging(level="INFO")
    if use_ai:
        load_project_env()

    cache_path = Path(ct_cache) if ct_cache else DEFAULT_CACHE_PATH
    log_pipeline_start(input_path, out_dir, str(cache_path))

    # Stage 0: Validation
    try:
        validate_input_file(input_path)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Validation failed: {e}")
        console.print(f"[red bold]✗ Error: {e}[/red bold]")
        raise

    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    raw_copy_path = out_dir_path / "01_raw_copy.csv"
    structure_report_path = out_dir_path / "01_structure_report.json"
    input_quality_path = out_dir_path / "02_input_quality.json"
    parsed_path = out_dir_path / "02_parsed_rows.json"
    quarantine_json_path = out_dir_path / "02_ingestion_quarantine.json"
    quarantine_csv_path = out_dir_path / "02_ingestion_quarantine.csv"
    mapping_path = out_dir_path / "03_mapping.yaml"
    mapped_path = out_dir_path / "04_mapped_rows.json"
    normalized_path = out_dir_path / "05_normalized_rows.json"
    resolution_path = out_dir_path / "06a_resolution.json"
    lookup_urls_path = out_dir_path / "06a_lookup_urls.csv"
    candidates_path = out_dir_path / "06_candidate_matches.json"
    reviewed_path = out_dir_path / "07_reviewed_matches.json"
    output_path = out_dir_path / "08_cellartracker_import.csv"
    report_path = out_dir_path / "09_match_report.csv"

    console.print("[bold blue]Starting pipeline[/bold blue]")
    input_quality = None

    # Stage 1: Detect and extract table structure
    try:
        log_stage_start(1, "Detect and extract table structure")
        structured_input = read_ingested_input_file(
            input_path,
            delimiter=delimiter,
            sheet_name=sheet_name,
            use_ai=use_ai,
            all_sheets=all_sheets,
            ocr=ocr,
        )
        structured_input.dataframe.to_csv(raw_copy_path, index=False)
        write_json(structured_input.to_report(), structure_report_path)
        quarantine_items = [
            item.to_dict() for item in structured_input.quarantine_items
        ]
        write_json(quarantine_items, quarantine_json_path)
        quarantine_to_dataframe(structured_input.quarantine_items).to_csv(
            quarantine_csv_path,
            index=False,
        )
        console.print(f"Saved raw copy to [green]{raw_copy_path}[/green]")
        console.print(
            f"Saved structure report to [green]{structure_report_path}[/green]"
        )
        console.print(
            f"Saved ingestion quarantine to [green]{quarantine_json_path}[/green]"
        )
        log_stage_complete(1, len(structured_input.dataframe))
    except Exception as e:
        logger.error(f"Stage 1 failed: {e}")
        console.print(f"[red bold]✗ Stage 1 failed: {e}[/red bold]")
        raise

    # Stage 2: Parse rows
    try:
        log_stage_start(2, "Parse rows")
        raw_rows = raw_rows_from_structured_input(
            structured_input,
            str(Path(input_path).name),
        )
        write_json(_serialize_models(raw_rows), parsed_path)
        console.print(f"Saved parsed rows to [green]{parsed_path}[/green]")
        log_stage_complete(2, len(raw_rows))
    except Exception as e:
        logger.error(f"Stage 2 failed: {e}")
        console.print(f"[red bold]✗ Stage 2 failed: {e}[/red bold]")
        raise

    if use_ai:
        try:
            logger.info("Assessing input quality with AI")
            input_quality = _assess_input_quality(raw_rows)
            write_json(input_quality, input_quality_path)
            console.print(
                f"Saved AI input quality assessment to [green]{input_quality_path}[/green]"
            )
        except Exception as e:
            logger.error(f"Input quality assessment artifact failed: {e}")
            console.print(f"[red bold]✗ Input quality assessment failed: {e}[/red bold]")
            raise

    # Stage 3: Schema mapping
    try:
        log_stage_start(3, "Infer schema mapping")
        headers = list(raw_rows[0].data.keys()) if raw_rows else []
        sample_values = raw_rows[0].data if raw_rows else None

        try:
            mapping = save_schema_mapping(
                headers,
                mapping_path,
                use_ai=use_ai,
                sample_values=sample_values,
                column_profiles=structured_input.field_evidence,
            )
            validate_schema_mapping(mapping, headers)
        except ValueError as e:
            logger.error(f"Schema validation failed: {e}")
            raise

        console.print(f"Saved inferred mapping to [green]{mapping_path}[/green]")
        log_stage_complete(3, len(mapping))
    except Exception as e:
        logger.error(f"Stage 3 failed: {e}")
        console.print(f"[red bold]✗ Stage 3 failed: {e}[/red bold]")
        raise

    # Stage 4: Apply schema mapping
    try:
        log_stage_start(4, "Apply schema mapping")
        mapped_rows = apply_schema_mapping(raw_rows, mapping)
        assert_mapped_records_valid(mapped_rows)
        write_json(_serialize_models(mapped_rows), mapped_path)
        console.print(f"Saved mapped rows to [green]{mapped_path}[/green]")
        log_stage_complete(4, len(mapped_rows))
    except Exception as e:
        logger.error(f"Stage 4 failed: {e}")
        console.print(f"[red bold]✗ Stage 4 failed: {e}[/red bold]")
        raise

    # Stage 5: Normalize rows
    try:
        log_stage_start(5, "Normalize rows")
        normalized_rows = normalize_mapped_rows(mapped_rows)
        assert_mapped_records_valid(normalized_rows)

        # Filter out empty rows
        normalized_rows, removed = filter_empty_rows(normalized_rows)

        write_json(_serialize_models(normalized_rows), normalized_path)
        console.print(f"Saved normalized rows to [green]{normalized_path}[/green]")
        log_stage_complete(5, len(normalized_rows))
    except Exception as e:
        logger.error(f"Stage 5 failed: {e}")
        console.print(f"[red bold]✗ Stage 5 failed: {e}[/red bold]")
        raise

    # Stage 6: Resolve candidates from the cache, then score
    try:
        log_stage_start(6, "Resolve candidates and score")
        with ResolutionCache(cache_path) as cache:
            canonical_wines = cache.all_canonical()
        logger.info(f"Loaded {len(canonical_wines)} cached wines from {cache_path}")

        match_results: list[MatchResult] = []
        resolution_records: list[dict] = []
        unresolved_rows: list[dict] = []
        for idx, row in enumerate(normalized_rows, 1):
            if idx % max(1, len(normalized_rows) // 10) == 0:
                logger.debug(f"Processing row {idx}/{len(normalized_rows)}")

            search_results = find_candidate_records_with_diagnostics(row, canonical_wines)
            candidates = [result.wine for result in search_results]
            blocking_reasons = {
                result.wine.id: result.blocking_reason
                for result in search_results
            }
            ranked = rank_candidates(
                row,
                candidates,
                use_ai_scoring=use_ai,
                blocking_reasons=blocking_reasons,
            )
            metrics = _match_metrics(ranked)
            match_results.append(
                MatchResult(
                    row_number=row.row_number,
                    user_row=_serialize_match_row(row),
                    candidates=ranked,
                    **metrics,
                )
            )

            query = build_search_query(row)
            resolution_records.append(
                {
                    "row_number": row.row_number,
                    "source": "cache" if ranked else "unresolved",
                    "query": query,
                    "num_candidates": len(ranked),
                    "top_score": ranked[0].score if ranked else None,
                }
            )
            if not ranked and query:
                unresolved_rows.append(
                    {
                        "row_number": str(row.row_number),
                        "producer": row.producer or "",
                        "name": row.name or "",
                        "vintage": row.vintage or "",
                        "query": query,
                        "url": build_search_url(query),
                    }
                )

        write_json(_serialize_models(match_results), candidates_path)
        write_json(resolution_records, resolution_path)
        with lookup_urls_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["row_number", "producer", "name", "vintage", "query", "url"],
            )
            writer.writeheader()
            writer.writerows(unresolved_rows)
        console.print(f"Saved candidate matches to [green]{candidates_path}[/green]")
        if unresolved_rows:
            console.print(
                f"[yellow]{len(unresolved_rows)} rows unresolved → "
                f"{lookup_urls_path} (resolve via ct-ingest, then re-run)[/yellow]"
            )
        log_stage_complete(6, len(match_results))
    except Exception as e:
        logger.error(f"Stage 6 failed: {e}")
        console.print(f"[red bold]✗ Stage 6 failed: {e}[/red bold]")
        raise

    # Stage 7: Review matches
    try:
        log_stage_start(7, "Review matches")
        reviewed = review_matches([result.model_dump() for result in match_results])
        if include_quarantine:
            first_quarantine_row = len(reviewed) + 1
            for offset, item in enumerate(structured_input.quarantine_items):
                reviewed.append(
                    ReviewedMatch(
                        row_number=first_quarantine_row + offset,
                        user_row={
                            **(item.data or {}),
                            "quarantine_reason": item.reason,
                            "source_name": item.source_name,
                            "source_row_number": item.row_number,
                        },
                        best_match=None,
                        status="rejected",
                        reason=f"Quarantined during ingestion: {item.reason}",
                        num_candidates=0,
                    )
                )
        write_json(_serialize_models(reviewed), reviewed_path)
        console.print(f"Saved reviewed matches to [green]{reviewed_path}[/green]")

        # Flywheel: teach the cache which signature resolved to which iWine,
        # so the next run is an exact hit instead of a fresh search.
        try:
            with ResolutionCache(cache_path) as cache:
                for record in reviewed:
                    best = record.best_match
                    if record.status != "accepted" or best is None or not best.ct_wine_id:
                        continue
                    definition = cache.get_definition(best.ct_wine_id)
                    if definition is None:
                        continue
                    user_row = record.user_row or {}
                    signature = ResolutionCache.signature(
                        user_row.get("producer"),
                        user_row.get("name"),
                        user_row.get("vintage"),
                    )
                    cache.record_resolution(signature, definition, best.score)
        except Exception as exc:
            logger.warning("Resolution write-back skipped: %s", exc)

        # Log review statistics
        accepted = sum(1 for r in reviewed if r.status == "accepted")
        review_needed = sum(1 for r in reviewed if r.status == "review_needed")
        rejected = sum(1 for r in reviewed if r.status == "rejected")
        logger.info(
            f"Review stats - Accepted: {accepted}, Review needed: {review_needed}, Rejected: {rejected}"
        )

        log_stage_complete(7, len(reviewed))
    except Exception as e:
        logger.error(f"Stage 7 failed: {e}")
        console.print(f"[red bold]✗ Stage 7 failed: {e}[/red bold]")
        raise

    # Stage 8: Export
    try:
        log_stage_start(8, "Export to CellarTracker format")
        exported_count = export_reviewed_matches(
            [record.model_dump() for record in reviewed],
            output_path,
            export_review_needed=export_review_needed,
            export_rejected_as_unmatched=export_rejected_as_unmatched,
        )
        console.print(f"Exported CellarTracker import to [green]{output_path}[/green]")
        log_stage_complete(8, exported_count)
    except Exception as e:
        logger.error(f"Stage 8 failed: {e}")
        console.print(f"[red bold]✗ Stage 8 failed: {e}[/red bold]")
        raise

    # Stage 9: Comparison report
    try:
        log_stage_start(9, "Write match comparison report")
        export_review_report([record.model_dump() for record in reviewed], report_path)
        console.print(f"Saved match comparison report to [green]{report_path}[/green]")
        log_stage_complete(9, len(reviewed))
    except Exception as e:
        logger.error(f"Stage 9 failed: {e}")
        console.print(f"[red bold]✗ Stage 9 failed: {e}[/red bold]")
        raise

    # Save manifest
    try:
        manifest_path = out_dir_path / "run_manifest.yaml"
        artifacts = {
            "raw_copy": str(raw_copy_path),
            "structure_report": str(structure_report_path),
            "parsed": str(parsed_path),
            "ingestion_quarantine": str(quarantine_json_path),
            "ingestion_quarantine_csv": str(quarantine_csv_path),
            "mapping": str(mapping_path),
            "mapped": str(mapped_path),
            "normalized": str(normalized_path),
            "resolution": str(resolution_path),
            "lookup_urls": str(lookup_urls_path),
            "candidates": str(candidates_path),
            "reviewed": str(reviewed_path),
            "report": str(report_path),
        }
        if input_quality is not None:
            artifacts["input_quality"] = str(input_quality_path)

        manifest = {
            "input_path": str(input_path),
            "ct_cache": str(cache_path),
            "output_path": str(output_path),
            "artifacts": artifacts,
            "stats": {
                "rows_parsed": len(raw_rows),
                "rows_quarantined": len(structured_input.quarantine_items),
                "rows_mapped": len(mapped_rows),
                "rows_normalized": len(normalized_rows),
                "candidate_sets": len(match_results),
                "resolved_from_cache": sum(
                    1 for r in resolution_records if r["source"] == "cache"
                ),
                "unresolved": len(unresolved_rows),
                "reviewed_matches": len(reviewed),
                "accepted_matches": sum(1 for r in reviewed if r.status == "accepted"),
                "review_needed_matches": sum(1 for r in reviewed if r.status == "review_needed"),
                "rejected_matches": sum(1 for r in reviewed if r.status == "rejected"),
            },
            "policy": scoring_policy_manifest(),
            "export_policy": {
                "export_review_needed": export_review_needed,
                "export_rejected_as_unmatched": export_rejected_as_unmatched,
                "include_quarantine": include_quarantine,
            },
            "ingestion_policy": {
                "all_sheets": all_sheets,
                "ocr": ocr,
            },
        }
        write_yaml(manifest, manifest_path)
        console.print(f"Saved run manifest to [green]{manifest_path}[/green]")
        logger.info(f"✓ Pipeline complete: {output_path}")
    except Exception as e:
        logger.error(f"Manifest save failed: {e}")
        console.print(f"[red bold]✗ Manifest save failed: {e}[/red bold]")
        raise

    result = {
        "raw_copy": str(raw_copy_path),
        "structure_report": str(structure_report_path),
        "parsed": str(parsed_path),
        "ingestion_quarantine": str(quarantine_json_path),
        "ingestion_quarantine_csv": str(quarantine_csv_path),
        "mapping": str(mapping_path),
        "mapped": str(mapped_path),
        "normalized": str(normalized_path),
        "resolution": str(resolution_path),
        "lookup_urls": str(lookup_urls_path),
        "candidates": str(candidates_path),
        "reviewed": str(reviewed_path),
        "export": str(output_path),
        "report": str(report_path),
        "manifest": str(manifest_path),
    }
    if input_quality is not None:
        result["input_quality"] = str(input_quality_path)
    return result
