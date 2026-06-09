from pathlib import Path

import pandas as pd

EXPORT_COLUMNS = [
    "Vintage",
    "UserWine1",
    "UserWine2",
    "Quantity",
    "BottleSize",
    "Location",
    "Bin",
    "Notes",
]


def _first_non_empty(*values) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _format_quantity(value) -> str:
    text = _first_non_empty(value)
    if not text:
        return ""
    if text.endswith(".0"):
        return text[:-2]
    return text


def _build_export_notes(
    record: dict,
    user_row: dict,
    best_match: dict,
    *,
    include_canonical_id: bool = True,
) -> str:
    parts: list[str] = []
    original_notes = _first_non_empty(user_row.get("notes"), user_row.get("Notes"))
    if original_notes:
        parts.append(original_notes)

    status = _first_non_empty(record.get("status"))
    reason = _first_non_empty(record.get("reason"))
    if status:
        parts.append(f"match_status={status}")
    if reason:
        parts.append(reason)
    canonical_id = _first_non_empty(best_match.get("canonical_id")) if include_canonical_id else ""
    if canonical_id:
        parts.append(f"canonical_id={canonical_id}")

    return " | ".join(parts)


def _user_export_row(record: dict, user_row: dict) -> dict[str, str]:
    notes = _build_export_notes(record, user_row, {}, include_canonical_id=False)
    return {
        "Vintage": _first_non_empty(user_row.get("vintage"), user_row.get("Vintage")),
        "UserWine1": _first_non_empty(user_row.get("producer"), user_row.get("UserWine1"), user_row.get("Producer")),
        "UserWine2": _first_non_empty(user_row.get("name"), user_row.get("UserWine2"), user_row.get("Name")),
        "Quantity": _format_quantity(user_row.get("quantity") if "quantity" in user_row else user_row.get("Quantity")),
        "BottleSize": _first_non_empty(
            user_row.get("size"),
            user_row.get("BottleSize"),
            user_row.get("Bottle Size"),
        ),
        "Location": _first_non_empty(user_row.get("location"), user_row.get("Location")),
        "Bin": _first_non_empty(user_row.get("bin"), user_row.get("Bin")),
        "Notes": notes,
    }


def _matched_export_row(record: dict, user_row: dict, best_match: dict) -> dict[str, str]:
    notes = _build_export_notes(record, user_row, best_match)
    return {
        "Vintage": _first_non_empty(best_match.get("vintage"), user_row.get("vintage"), user_row.get("Vintage")),
        "UserWine1": _first_non_empty(best_match.get("producer"), user_row.get("producer"), user_row.get("UserWine1"), user_row.get("Producer")),
        "UserWine2": _first_non_empty(best_match.get("name"), user_row.get("name"), user_row.get("UserWine2"), user_row.get("Name")),
        "Quantity": _format_quantity(user_row.get("quantity") if "quantity" in user_row else user_row.get("Quantity")),
        "BottleSize": _first_non_empty(
            user_row.get("size"),
            user_row.get("BottleSize"),
            user_row.get("Bottle Size"),
        ),
        "Location": _first_non_empty(user_row.get("location"), user_row.get("Location")),
        "Bin": _first_non_empty(user_row.get("bin"), user_row.get("Bin")),
        "Notes": notes,
    }


def export_reviewed_matches(
    reviewed_matches: list[dict],
    output_path: str | Path,
    *,
    export_review_needed: bool = False,
    export_rejected_as_unmatched: bool = False,
) -> int:
    rows = []
    for record in reviewed_matches:
        user_row = record.get("user_row", {}) or {}
        best_match = record.get("best_match", {}) or {}
        status = _first_non_empty(record.get("status"))

        if status == "accepted":
            rows.append(_matched_export_row(record, user_row, best_match))
        elif status == "review_needed" and export_review_needed:
            rows.append(_matched_export_row(record, user_row, best_match))
        elif status == "rejected" and export_rejected_as_unmatched:
            rows.append(_user_export_row(record, user_row))
    df = pd.DataFrame(rows, columns=EXPORT_COLUMNS)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False)
    return len(rows)
