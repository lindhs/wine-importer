from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from .models import MappedWineRow, RawRow
from .io import write_yaml

FIELD_KEYWORDS = {
    "producer": [
        "producer",
        "winery",
        "domaine",
        "estate",
        "maker",
        "winemaker",
        "user wine 1",
        "wine 1",
    ],
    "name": [
        "name",
        "wine",
        "label",
        "designation",
        "cuvee",
        "wine name",
        "wine title",
        "user wine 2",
        "wine 2",
    ],
    "vineyard": ["vineyard", "estate", "domaine", "estate name"],
    "vintage": ["vintage", "year", "yr", "vintage year"],
    "country": ["country", "nation", "pais", "origin", "origins"],
    "region": ["region", "district", "area", "zone", "territory"],
    "subregion": ["subregion", "sub-region", "area", "sub area"],
    "appellation": ["appellation", "av", "cru", "app", "denomination"],
    "varietal": ["varietal", "grape", "blend", "type", "style", "cuvee"],
    "quantity": ["quantity", "qty", "count", "bottles", "bottle count", "units"],
    "size": ["size", "bottle size", "bottle", "format", "volume", "ml", "cl", "liter", "litre"],
    "bottle_size": ["bottle size", "size", "format", "volume", "ml", "cl", "liter", "litre"],
    "purchase_date": ["purchase date", "bought", "acquired", "date"],
    "location": ["location", "cellar", "storage", "warehouse", "rack"],
    "bin": ["bin", "slot", "position", "shelf"],
    "notes": ["notes", "comment", "description", "review", "personal note"],
}


def infer_schema_mapping(headers: Iterable[str]) -> dict[str, str]:
    normalized = [header.strip() for header in headers]
    mapping: dict[str, str] = {}
    used_headers: set[str] = set()
    for field, keywords in FIELD_KEYWORDS.items():
        for header in normalized:
            if header in used_headers:
                continue
            if _matches_any_keyword(header, keywords) or _normalize_header(header) == field:
                mapping[field] = header
                used_headers.add(header)
                break
    for field in FIELD_KEYWORDS:
        if field not in mapping:
            for header in normalized:
                if _normalize_header(header) == field and header not in used_headers:
                    mapping[field] = header
                    used_headers.add(header)
                    break
    return mapping


def _normalize_header(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", normalized)
    normalized = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", normalized)
    normalized = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", normalized)
    normalized = re.sub(r"[^a-zA-Z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return normalized


def _matches_keyword(header: str, keyword: str) -> bool:
    normalized_header = _normalize_header(header)
    normalized_keyword = _normalize_header(keyword)
    pattern = rf"(^| ){re.escape(normalized_keyword)}( |$)"
    return bool(re.search(pattern, normalized_header))


def _matches_any_keyword(header: str, keywords: Iterable[str]) -> bool:
    return any(_matches_keyword(header, keyword) for keyword in keywords)


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
                vineyard=source.get(mapping.get("vineyard", ""), "") or None,
                vintage=source.get(mapping.get("vintage", ""), "") or None,
                country=source.get(mapping.get("country", ""), "") or None,
                region=source.get(mapping.get("region", ""), "") or None,
                subregion=source.get(mapping.get("subregion", ""), "") or None,
                appellation=source.get(mapping.get("appellation", ""), "") or None,
                varietal=source.get(mapping.get("varietal", ""), "") or None,
                quantity=_safe_float(source.get(mapping.get("quantity", ""), "")),
                size=source.get(mapping.get("size", ""), "") or None,
                bottle_size=source.get(mapping.get("bottle_size", ""), "") or None,
                purchase_date=source.get(mapping.get("purchase_date", ""), "") or None,
                location=source.get(mapping.get("location", ""), "") or None,
                bin=source.get(mapping.get("bin", ""), "") or None,
                notes=source.get(mapping.get("notes", ""), "") or None,
                original=source,
            )
        )
    return mapped_rows


def _safe_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _safe_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None
