from __future__ import annotations

import logging
import re
import unicodedata
from typing import Iterable

from .models import MappedWineRow, RawRow
from .io import write_yaml

logger = logging.getLogger(__name__)

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


def infer_schema_mapping(
    headers: Iterable[str],
    use_ai: bool = False,
    sample_values: dict[str, str] | None = None,
    column_profiles: dict[str, dict] | None = None,
) -> dict[str, str]:
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

    if column_profiles:
        for header in normalized:
            if header in used_headers:
                continue
            profile = column_profiles.get(header) or {}
            field = profile.get("best_field")
            confidence = float(profile.get("confidence") or 0.0)
            if field in FIELD_KEYWORDS and field not in mapping and confidence >= 0.65:
                mapping[field] = header
                used_headers.add(header)

        _infer_text_identity_fields_from_profiles(
            normalized,
            mapping,
            used_headers,
            column_profiles,
        )

    # Try AI enhancement if keyword matching is weak
    if use_ai and len(mapping) < 4:  # Less than 4 fields matched by keywords
        logger.info("Keyword mapping found only %d fields; attempting AI enhancement", len(mapping))
        try:
            from .ai_schema import infer_schema_mapping_with_ai

            ai_mapping = infer_schema_mapping_with_ai(normalized, sample_values)
            # Prefer AI mappings for fields we haven't found
            for field, header in ai_mapping.items():
                if field not in mapping and header not in used_headers:
                    mapping[field] = header
                    used_headers.add(header)
                    logger.debug("AI suggestion: %s → %s", header, field)
        except Exception as e:
            logger.warning("AI schema mapping failed: %s (continuing with keyword mapping)", e)

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


def save_schema_mapping(
    headers: Iterable[str],
    output_path: str | bytes,
    use_ai: bool = False,
    sample_values: dict[str, str] | None = None,
    column_profiles: dict[str, dict] | None = None,
) -> dict[str, str]:
    mapping = infer_schema_mapping(
        headers,
        use_ai=use_ai,
        sample_values=sample_values,
        column_profiles=column_profiles,
    )
    write_yaml(mapping, output_path)
    return mapping


def _infer_text_identity_fields_from_profiles(
    headers: list[str],
    mapping: dict[str, str],
    used_headers: set[str],
    column_profiles: dict[str, dict],
) -> None:
    text_candidates = sorted(
        (
            (
                index,
                header,
                float((column_profiles.get(header) or {}).get("text_score") or 0.0),
            )
            for index, header in enumerate(headers)
            if header not in used_headers
        ),
        key=lambda item: item[0],
    )
    text_candidates = [
        (index, header, score)
        for index, header, score in text_candidates
        if score >= 0.45
    ]
    if "producer" not in mapping and text_candidates:
        _, header, _ = text_candidates.pop(0)
        mapping["producer"] = header
        used_headers.add(header)
    if "name" not in mapping and text_candidates:
        _, header, _ = text_candidates.pop(0)
        mapping["name"] = header
        used_headers.add(header)


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
