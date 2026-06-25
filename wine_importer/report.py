from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.table import Table

from .cellartracker_lookup import WINE_URL_TEMPLATE
from .normalize import normalize_size, normalize_text, normalize_vintage

REPORT_COLUMNS = [
    "row_number",
    "status",
    "score",
    "top_1_score",
    "top_2_score",
    "score_margin",
    "num_candidates",
    "blocking_reason",
    "producer_score",
    "name_score",
    "vintage_score",
    "region_score",
    "hard_conflicts",
    "suggested_action",
    "reason",
    "input_item",
    "best_candidate_item",
    "diff_fields",
    "canonical_id",
    "ct_wine_id",
    "ct_url",
    "resolution_source",
    "input_producer",
    "candidate_producer",
    "input_name",
    "candidate_name",
    "input_vintage",
    "candidate_vintage",
    "input_country",
    "candidate_country",
    "input_region",
    "candidate_region",
    "input_appellation",
    "candidate_appellation",
    "input_varietal",
    "candidate_varietal",
    "input_quantity",
    "candidate_quantity",
    "input_size",
    "candidate_size",
    "input_location",
    "input_bin",
    "input_notes",
    "candidate_notes",
]


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        return text[:-2]
    return text


def _score(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.4f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return _text(value)


def _list_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_text(item) for item in value if _text(item))
    return _text(value)


def _candidate_source(best_match: dict[str, Any]) -> dict[str, Any]:
    source = best_match.get("source") or {}
    return source if isinstance(source, dict) else {}


def _candidate_value(best_match: dict[str, Any], field: str) -> Any:
    source = _candidate_source(best_match)
    value = best_match.get(field)
    return value if _text(value) else source.get(field)


def _input_value(user_row: dict[str, Any], field: str) -> Any:
    aliases = {
        "producer": ("producer", "Producer", "UserWine1"),
        "name": ("name", "Name", "UserWine2"),
        "vintage": ("vintage", "Vintage"),
        "country": ("country", "Country", "UserWine5"),
        "region": ("region", "Region", "UserWine7"),
        "appellation": ("appellation", "Appellation", "UserWine8"),
        "varietal": ("varietal", "Varietal", "UserWine2"),
        "quantity": ("quantity", "Quantity", "Qty"),
        "size": ("size", "bottle_size", "BottleSize", "Bottle Size"),
        "location": ("location", "Location", "Cellar"),
        "bin": ("bin", "Bin"),
        "notes": ("notes", "Notes", "BottleNote"),
    }
    for key in aliases.get(field, (field,)):
        value = user_row.get(key)
        if _text(value):
            return value
    original = user_row.get("original")
    if isinstance(original, dict):
        for key in aliases.get(field, (field,)):
            value = original.get(key)
            if _text(value):
                return value
    return ""


def _format_item(*values: Any) -> str:
    parts = [_text(value) for value in values]
    return " | ".join(part for part in parts if part)


def _normalize_for_compare(field: str, value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    if field == "vintage":
        return normalize_vintage(text) or ""
    if field == "size":
        return normalize_size(text) or ""
    return normalize_text(text) or ""


def _diff_fields(user_row: dict[str, Any], best_match: dict[str, Any]) -> str:
    fields = ["producer", "name", "vintage", "country", "region", "appellation", "varietal", "size"]
    diffs: list[str] = []
    for field in fields:
        input_value = _input_value(user_row, field)
        candidate_value = _candidate_value(best_match, field)
        if not _text(input_value) or not _text(candidate_value):
            continue
        if _normalize_for_compare(field, input_value) != _normalize_for_compare(field, candidate_value):
            diffs.append(field)
    return ", ".join(diffs)


def _suggested_action(record: dict[str, Any], best_match: dict[str, Any]) -> str:
    status = _text(record.get("status"))
    conflicts = best_match.get("hard_conflicts") or []
    margin = record.get("score_margin")
    if status == "accepted" and not conflicts:
        return "export"
    if status == "accepted" and conflicts:
        return "spot_check"
    if status == "review_needed":
        try:
            if margin is not None and float(margin) < 0.1:
                return "compare_top_candidates"
        except (TypeError, ValueError):
            pass
        return "manual_review"
    if status == "rejected":
        return "do_not_export"
    return ""


def build_review_report_rows(reviewed_matches: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in reviewed_matches:
        user_row = record.get("user_row") or {}
        best_match = record.get("best_match") or {}
        source = _candidate_source(best_match)
        ct_wine_id = best_match.get("ct_wine_id") or source.get("ct_wine_id")
        ct_url = WINE_URL_TEMPLATE.format(iwine=ct_wine_id) if ct_wine_id else ""
        resolution_source = _text(source.get("source")) if best_match else ""

        input_item = _format_item(
            _input_value(user_row, "vintage"),
            _input_value(user_row, "producer"),
            _input_value(user_row, "name"),
            _input_value(user_row, "region"),
            _input_value(user_row, "size"),
        )
        candidate_item = _format_item(
            _candidate_value(best_match, "vintage"),
            _candidate_value(best_match, "producer"),
            _candidate_value(best_match, "name"),
            _candidate_value(best_match, "region"),
            _candidate_value(best_match, "size"),
        )

        rows.append(
            {
                "row_number": _text(record.get("row_number")),
                "status": _text(record.get("status")),
                "score": _score(best_match.get("score")),
                "top_1_score": _score(record.get("top_1_score")),
                "top_2_score": _score(record.get("top_2_score")),
                "score_margin": _score(record.get("score_margin")),
                "num_candidates": _text(record.get("num_candidates")),
                "blocking_reason": _text(best_match.get("blocking_reason")),
                "producer_score": _score(best_match.get("producer_score")),
                "name_score": _score(best_match.get("name_score")),
                "vintage_score": _score(best_match.get("vintage_score")),
                "region_score": _score(best_match.get("region_score")),
                "hard_conflicts": _list_text(best_match.get("hard_conflicts")),
                "suggested_action": _suggested_action(record, best_match),
                "reason": _text(record.get("reason")),
                "input_item": input_item,
                "best_candidate_item": candidate_item,
                "diff_fields": _diff_fields(user_row, best_match) if best_match else "",
                "canonical_id": _text(best_match.get("canonical_id") or source.get("id")),
                "ct_wine_id": _text(ct_wine_id),
                "ct_url": ct_url,
                "resolution_source": resolution_source,
                "input_producer": _text(_input_value(user_row, "producer")),
                "candidate_producer": _text(_candidate_value(best_match, "producer")),
                "input_name": _text(_input_value(user_row, "name")),
                "candidate_name": _text(_candidate_value(best_match, "name")),
                "input_vintage": _text(_input_value(user_row, "vintage")),
                "candidate_vintage": _text(_candidate_value(best_match, "vintage")),
                "input_country": _text(_input_value(user_row, "country")),
                "candidate_country": _text(source.get("country")),
                "input_region": _text(_input_value(user_row, "region")),
                "candidate_region": _text(_candidate_value(best_match, "region")),
                "input_appellation": _text(_input_value(user_row, "appellation")),
                "candidate_appellation": _text(_candidate_value(best_match, "appellation")),
                "input_varietal": _text(_input_value(user_row, "varietal")),
                "candidate_varietal": _text(_candidate_value(best_match, "varietal")),
                "input_quantity": _text(_input_value(user_row, "quantity")),
                "candidate_quantity": _text(source.get("quantity")),
                "input_size": _text(_input_value(user_row, "size")),
                "candidate_size": _text(source.get("size")),
                "input_location": _text(_input_value(user_row, "location")),
                "input_bin": _text(_input_value(user_row, "bin")),
                "input_notes": _text(_input_value(user_row, "notes")),
                "candidate_notes": _text(source.get("notes")),
            }
        )
    return rows


def export_review_report(reviewed_matches: list[dict[str, Any]], output_path: str | Path) -> None:
    rows = build_review_report_rows(reviewed_matches)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=REPORT_COLUMNS).to_csv(output_file, index=False)


def print_review_report(
    reviewed_matches: list[dict[str, Any]],
    *,
    status: str | None = None,
    limit: int = 20,
    console: Console | None = None,
) -> None:
    console = console or Console()
    rows = build_review_report_rows(reviewed_matches)
    if status:
        rows = [row for row in rows if row["status"] == status]

    counts = Counter(row["status"] for row in build_review_report_rows(reviewed_matches))
    console.print(
        "[bold]Match summary[/bold] "
        f"accepted={counts.get('accepted', 0)} "
        f"review_needed={counts.get('review_needed', 0)} "
        f"rejected={counts.get('rejected', 0)}"
    )

    display_columns = [
        ("row_number", "Row", True),
        ("status", "Status", True),
        ("score", "Score", True),
        ("input_item", "Input", False),
        ("best_candidate_item", "Best Candidate", False),
        ("diff_fields", "Diff", False),
    ]
    table = Table(title="Best Candidate Comparison")
    for _, label, no_wrap in display_columns:
        table.add_column(label, overflow="fold", no_wrap=no_wrap)
    for row in rows[:limit]:
        table.add_row(*(row[column] for column, _, _ in display_columns))
    console.print(table)
    if limit and len(rows) > limit:
        console.print(f"Showing {limit} of {len(rows)} rows")
