from __future__ import annotations

from typing import Iterable

from .models import MappedWineRow, RawRow
from .io import write_yaml

FIELD_KEYWORDS = {
    "producer": ["producer", "winery", "domaine", "estate", "maker"],
    "name": ["name", "wine", "label"],
    "vintage": ["vintage", "year"],
    "region": ["region", "district", "area"],
    "appellation": ["appellation", "subregion", "location"],
    "varietal": ["varietal", "grape", "blend"],
    "quantity": ["quantity", "qty", "count"],
    "size": ["size", "bottle size", "bottle"],
    "location": ["location", "cellar", "storage"],
    "bin": ["bin", "slot"],
    "notes": ["notes", "comment", "description"],
}


def infer_schema_mapping(headers: Iterable[str]) -> dict[str, str]:
    normalized = [header.strip() for header in headers]
    mapping: dict[str, str] = {}
    for field, keywords in FIELD_KEYWORDS.items():
        match = _find_header(normalized, keywords)
        if match:
            mapping[field] = match
    for field in FIELD_KEYWORDS:
        if field not in mapping and field in normalized:
            mapping[field] = field
    return mapping


def _find_header(headers: Iterable[str], keywords: Iterable[str]) -> str | None:
    for header in headers:
        lower = header.lower()
        for keyword in keywords:
            if keyword in lower:
                return header
    return None


def save_schema_mapping(headers: Iterable[str], output_path: str | bytes) -> dict[str, str]:
    mapping = infer_schema_mapping(headers)
    write_yaml(mapping, output_path)
    return mapping


def apply_schema_mapping(raw_rows: list[RawRow], mapping: dict[str, str]) -> list[MappedWineRow]:
    mapped_rows: list[MappedWineRow] = []
    for raw in raw_rows:
        source = raw.data
        mapped_rows.append(
            MappedWineRow(
                row_number=raw.row_number,
                producer=source.get(mapping.get("producer", ""), "") or None,
                name=source.get(mapping.get("name", ""), "") or None,
                vintage=source.get(mapping.get("vintage", ""), "") or None,
                region=source.get(mapping.get("region", ""), "") or None,
                appellation=source.get(mapping.get("appellation", ""), "") or None,
                varietal=source.get(mapping.get("varietal", ""), "") or None,
                quantity=_safe_int(source.get(mapping.get("quantity", ""), "")),
                size=source.get(mapping.get("size", ""), "") or None,
                location=source.get(mapping.get("location", ""), "") or None,
                bin=source.get(mapping.get("bin", ""), "") or None,
                notes=source.get(mapping.get("notes", ""), "") or None,
                original=source,
            )
        )
    return mapped_rows


def _safe_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None
