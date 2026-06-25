import csv
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from heapq import nlargest
from pathlib import Path

from rapidfuzz import fuzz

from .models import CanonicalWine, NormalizedWineRow
from .normalize import normalize_size, normalize_text

CANONICAL_FIELD_ALIASES = {
    "bottle size": "size",
    "bottlesize": "size",
    "winery": "producer",
    "wine": "name",
    "nation": "country",
}
LEGACY_CANONICAL_HEADER = [
    "producer",
    "name",
    "vintage",
    "region",
    "appellation",
    "varietal",
    "quantity",
    "size",
    "notes",
]
LEGACY_CANONICAL_FALLBACK_HEADER = [
    "producer",
    "name",
    "vintage",
    "country",
    "appellation",
    "varietal",
    "quantity",
    "size",
    "location",
    "bin",
    "notes",
]
SEARCH_STOPWORDS = {
    "and",
    "de",
    "del",
    "della",
    "di",
    "la",
    "le",
    "red",
    "rose",
    "rouge",
    "the",
    "vin",
    "vino",
    "white",
    "wine",
}
_SEARCH_CACHE: dict[str, tuple[tuple["_CanonicalSearchRecord", ...], dict[str, tuple[int, ...]]]] = {}
_SEARCH_CACHE_MAX_ENTRIES = 16


@dataclass(frozen=True)
class _CanonicalSearchRecord:
    wine: CanonicalWine
    producer: str | None
    name: str | None
    country: str | None
    region: str | None
    appellation: str | None
    varietal: str | None
    vintage: str | None
    tokens: frozenset[str]


@dataclass(frozen=True)
class CandidateSearchResult:
    wine: CanonicalWine
    blocking_reason: str


def load_canonical_wines(path: str | Path) -> list[CanonicalWine]:
    records: list[CanonicalWine] = []
    for index, row in enumerate(_read_canonical_rows(path), start=1):
        row = _repair_canonical_row(row)
        extracted = _extract_canonical_fields(row)
        region = extracted["region"] or extracted["appellation"] or ""
        appellation = extracted["appellation"] or region
        varietal = extracted["varietal"] or appellation
        notes = extracted["notes"]
        producer = extracted["producer"]
        name = extracted["name"]
        if not producer and not name:
            continue
        ct_wine_id = _clean_text(row.get("ct_wine_id"))
        records.append(
            CanonicalWine(
                id=f"ct:{ct_wine_id}" if ct_wine_id else str(index),
                ct_wine_id=ct_wine_id,
                producer=producer or "",
                name=name or "",
                vintage=extracted["vintage"] or "",
                country=extracted["country"] or None,
                region=region,
                appellation=appellation,
                varietal=varietal,
                quantity=_safe_int(extracted["quantity"]),
                size=extracted["size"] or "",
                notes=notes or None,
                source="cellartracker_html" if ct_wine_id else "local_csv",
            )
        )
    return records


def _read_canonical_rows(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    with path.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.reader(source))

    if not rows:
        return []

    raw_header = [_normalize_header_name(cell) for cell in rows[0]]
    max_width = max(len(row) for row in rows)
    if raw_header == LEGACY_CANONICAL_HEADER and max_width > len(raw_header):
        header = LEGACY_CANONICAL_FALLBACK_HEADER.copy()
    else:
        header = raw_header.copy()
        if max_width > len(header):
            for index in range(1, max_width - len(header) + 1):
                header.append(f"_extra_{index}")

    records: list[dict[str, str]] = []
    for row in rows[1:]:
        padded_row = list(row) + [""] * max(0, len(header) - len(row))
        values = padded_row[: len(header)]
        record = {header[index]: values[index].strip() for index in range(len(header))}
        records.append(record)
    return records


def _normalize_header_name(value: str) -> str:
    normalized = str(value).lstrip("\ufeff").strip().lower()
    normalized = " ".join(normalized.split())
    return CANONICAL_FIELD_ALIASES.get(normalized, normalized)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _collapse_notes(row: dict[str, str]) -> str | None:
    notes_parts: list[str] = []
    for key, value in row.items():
        if key in {"notes", "bottlenote", "purchasenote", "privatenote", "tastingnotes"} or key.startswith("_extra_"):
            cleaned = _clean_text(value)
            if cleaned:
                notes_parts.append(cleaned)
    if not notes_parts:
        return None
    return " | ".join(notes_parts)


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        cleaned = _clean_text(value)
        if cleaned:
            return cleaned
    return None


def _join_non_empty(*values: str | None) -> str | None:
    parts: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        if cleaned:
            parts.append(cleaned)
    if not parts:
        return None
    return " ".join(parts)


def _extract_canonical_fields(row: dict[str, str]) -> dict[str, str | None]:
    producer = _first_non_empty(
        row.get("producer"),
        row.get("winery"),
        row.get("userwine1"),
    )
    name = _first_non_empty(row.get("name")) or _join_non_empty(
        row.get("userwine2"),
        row.get("userwine3"),
        row.get("userwine4"),
    )
    country = _first_non_empty(
        row.get("country"),
        row.get("nation"),
        row.get("userwine5"),
    )
    region = _first_non_empty(row.get("region")) or _join_non_empty(
        row.get("userwine7"),
        row.get("userwine8"),
    ) or _first_non_empty(
        row.get("userwine7"),
        row.get("userwine6"),
        row.get("userwine8"),
    )
    appellation = _first_non_empty(
        row.get("appellation"),
        row.get("userwine8"),
        row.get("userwine3"),
        row.get("userwine7"),
        row.get("userwine6"),
    )
    varietal = _first_non_empty(
        row.get("varietal"),
        row.get("userwine2"),
        row.get("userwine3"),
    )
    return {
        "producer": producer,
        "name": name,
        "vintage": _first_non_empty(row.get("vintage")),
        "country": country,
        "region": region,
        "appellation": appellation,
        "varietal": varietal,
        "quantity": _first_non_empty(row.get("quantity")),
        "size": _first_non_empty(row.get("size"), row.get("bottlesize")),
        "notes": _collapse_notes(row),
    }


def _repair_canonical_row(row: dict[str, str]) -> dict[str, str]:
    repaired = dict(row)
    varietal = _clean_text(repaired.get("varietal"))
    quantity = _clean_text(repaired.get("quantity"))
    size = _clean_text(repaired.get("size"))

    if (
        not size
        and varietal
        and quantity
        and _safe_int(varietal) is not None
        and normalize_size(quantity) is not None
    ):
        repaired["varietal"] = ""
        repaired["quantity"] = varietal
        repaired["size"] = quantity

    return repaired


def _safe_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _has_token_overlap(value_a: str | None, value_b: str | None) -> bool:
    if not value_a or not value_b:
        return False
    tokens_a = set(value_a.split())
    tokens_b = set(value_b.split())
    return bool(tokens_a & tokens_b)


def _has_strong_name_token_overlap(value_a: str | None, value_b: str | None) -> bool:
    if not value_a or not value_b:
        return False
    tokens_a = {token for token in value_a.split() if len(token) >= 4}
    tokens_b = {token for token in value_b.split() if len(token) >= 4}
    return bool(tokens_a & tokens_b)


def _strong_producer_match(normalized_producer: str | None, canonical_producer: str | None) -> bool:
    if not normalized_producer or not canonical_producer:
        return False
    return fuzz.token_sort_ratio(normalized_producer, canonical_producer) >= 70


def _blocking_reason(
    normalized_row: NormalizedWineRow,
    canonical: _CanonicalSearchRecord,
) -> str | None:
    producer = normalized_row.normalized_producer
    name = normalized_row.normalized_name
    appellation = normalized_row.normalized_appellation

    if _strong_producer_match(producer, canonical.producer):
        return "producer"
    if appellation and canonical.appellation and (
        appellation == canonical.appellation
        or appellation in canonical.appellation
        or canonical.appellation in appellation
    ):
        return "appellation"
    if _has_strong_name_token_overlap(name, canonical.name):
        return "name_token"
    return None


def _passes_blocking(normalized_row: NormalizedWineRow, canonical: _CanonicalSearchRecord) -> bool:
    return _blocking_reason(normalized_row, canonical) is not None


def _tokenize(*values: str | None) -> frozenset[str]:
    tokens: set[str] = set()
    for value in values:
        normalized = normalize_text(value)
        if not normalized:
            continue
        for token in normalized.split():
            if len(token) <= 1 or token in SEARCH_STOPWORDS:
                continue
            tokens.add(token)
    return frozenset(tokens)


def _canonical_content_key(canonical_wines: list[CanonicalWine]) -> str:
    # Key the index cache on canonical *content*, not id(canonical_wines):
    # a Python object id can be reused after GC and silently serve a stale
    # index for a different list.
    hasher = hashlib.sha1()
    hasher.update(str(len(canonical_wines)).encode("utf-8"))
    for wine in canonical_wines:
        hasher.update(
            "\x1f".join(
                (wine.id, wine.producer, wine.name, wine.vintage, wine.appellation)
            ).encode("utf-8")
        )
        hasher.update(b"\x1e")
    return hasher.hexdigest()


def _build_search_index(
    canonical_wines: list[CanonicalWine],
) -> tuple[tuple[_CanonicalSearchRecord, ...], dict[str, tuple[int, ...]]]:
    cache_key = _canonical_content_key(canonical_wines)
    cached = _SEARCH_CACHE.get(cache_key)
    if cached is not None:
        return cached

    records: list[_CanonicalSearchRecord] = []
    token_index: defaultdict[str, list[int]] = defaultdict(list)

    for index, wine in enumerate(canonical_wines):
        record = _CanonicalSearchRecord(
            wine=wine,
            producer=normalize_text(wine.producer),
            name=normalize_text(wine.name),
            country=normalize_text(wine.country),
            region=normalize_text(wine.region),
            appellation=normalize_text(wine.appellation),
            varietal=normalize_text(wine.varietal),
            vintage=normalize_text(wine.vintage),
            tokens=_tokenize(
                wine.producer,
                wine.name,
                wine.country,
                wine.region,
                wine.appellation,
                wine.varietal,
                wine.vintage,
            ),
        )
        records.append(record)
        for token in record.tokens:
            token_index[token].append(index)

    finalized_index = {token: tuple(indices) for token, indices in token_index.items()}
    finalized_records = tuple(records)
    if len(_SEARCH_CACHE) >= _SEARCH_CACHE_MAX_ENTRIES:
        _SEARCH_CACHE.clear()
    _SEARCH_CACHE[cache_key] = (finalized_records, finalized_index)
    return finalized_records, finalized_index


def _query_token_weights(normalized_row: NormalizedWineRow) -> dict[str, float]:
    weighted_tokens: dict[str, float] = {}
    field_weights = (
        (normalized_row.normalized_producer or normalized_row.producer, 3.0),
        (normalized_row.normalized_name or normalized_row.name, 3.0),
        (normalized_row.normalized_appellation or normalized_row.appellation, 2.5),
        (normalized_row.normalized_region or normalized_row.region, 2.0),
        (normalized_row.normalized_varietal or normalized_row.varietal, 1.5),
        (normalized_row.normalized_country or normalized_row.country, 1.0),
        (normalized_row.normalized_vintage or normalized_row.vintage, 0.75),
    )
    for value, weight in field_weights:
        for token in _tokenize(value):
            weighted_tokens[token] = max(weighted_tokens.get(token, 0.0), weight)
    return weighted_tokens


def _approximate_candidate_score(
    normalized_row: NormalizedWineRow,
    canonical: _CanonicalSearchRecord,
    query_token_weights: dict[str, float],
) -> float:
    shared_weight = sum(query_token_weights[token] for token in canonical.tokens if token in query_token_weights)
    max_token_weight = sum(query_token_weights.values()) or 1.0
    token_score = shared_weight / max_token_weight

    producer_score = 0.0
    name_score = 0.0
    if normalized_row.normalized_producer and canonical.producer:
        producer_score = fuzz.token_sort_ratio(normalized_row.normalized_producer, canonical.producer) / 100.0
    if normalized_row.normalized_name and canonical.name:
        name_score = fuzz.token_sort_ratio(normalized_row.normalized_name, canonical.name) / 100.0

    score = token_score + (0.45 * producer_score) + (0.55 * name_score)

    if normalized_row.normalized_country and canonical.country and normalized_row.normalized_country == canonical.country:
        score += 0.05
    if normalized_row.normalized_vintage and canonical.vintage and normalized_row.normalized_vintage == canonical.vintage:
        score += 0.05
    if normalized_row.normalized_appellation and canonical.appellation and normalized_row.normalized_appellation == canonical.appellation:
        score += 0.25

    return score


def _has_meaningful_token_overlap(
    canonical: _CanonicalSearchRecord,
    query_token_weights: dict[str, float],
) -> bool:
    for token in canonical.tokens:
        if token in query_token_weights and not token.isdigit():
            return True
    return False


def _has_meaningful_identity_overlap(
    normalized_row: NormalizedWineRow,
    canonical: _CanonicalSearchRecord,
    query_token_weights: dict[str, float],
) -> bool:
    if _blocking_reason(normalized_row, canonical):
        return True
    if _has_strong_name_token_overlap(normalized_row.normalized_name, canonical.name):
        return True
    if _has_token_overlap(normalized_row.normalized_producer, canonical.producer):
        return True
    if _has_token_overlap(normalized_row.normalized_appellation, canonical.appellation):
        return True
    return _has_meaningful_token_overlap(canonical, query_token_weights) and (
        _has_token_overlap(normalized_row.normalized_name, canonical.name)
        or _has_token_overlap(normalized_row.normalized_producer, canonical.producer)
    )


def find_candidate_records_with_diagnostics(
    normalized_row: NormalizedWineRow,
    canonical_wines: list[CanonicalWine],
    max_candidates: int = 10,
) -> list[CandidateSearchResult]:
    if not canonical_wines or max_candidates <= 0:
        return []

    search_records, token_index = _build_search_index(canonical_wines)
    query_token_weights = _query_token_weights(normalized_row)

    scored_indices: defaultdict[int, float] = defaultdict(float)
    for token, weight in query_token_weights.items():
        for index in token_index.get(token, ()):
            scored_indices[index] += weight

    if scored_indices:
        shortlist_size = min(len(search_records), max(max_candidates * 8, 25))
        shortlist = nlargest(shortlist_size, scored_indices, key=scored_indices.get)
    else:
        shortlist = list(range(len(search_records)))

    ranked: list[tuple[int, float, CandidateSearchResult]] = []
    for index in shortlist:
        record = search_records[index]
        reason = _blocking_reason(normalized_row, record)
        approximate_score = _approximate_candidate_score(normalized_row, record, query_token_weights)
        if reason:
            ranked.append((1, approximate_score, CandidateSearchResult(record.wine, reason)))
        elif approximate_score >= 0.4 and _has_meaningful_identity_overlap(
            normalized_row,
            record,
            query_token_weights,
        ):
            ranked.append((0, approximate_score, CandidateSearchResult(record.wine, "approximate")))

    if not ranked:
        fallback_ranked = sorted(
            (
                (
                    _approximate_candidate_score(normalized_row, record, query_token_weights),
                    _has_meaningful_identity_overlap(
                        normalized_row,
                        record,
                        query_token_weights,
                    ),
                    record.wine,
                )
                for record in search_records
            ),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
        return [
            CandidateSearchResult(wine, "approximate")
            for score, has_meaningful_overlap, wine in fallback_ranked[:max_candidates]
            if has_meaningful_overlap and score > 0.3
        ]

    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [result for _, _, result in ranked[:max_candidates]]


def find_candidate_records(
    normalized_row: NormalizedWineRow,
    canonical_wines: list[CanonicalWine],
    max_candidates: int = 10,
) -> list[CanonicalWine]:
    return [
        result.wine
        for result in find_candidate_records_with_diagnostics(
            normalized_row,
            canonical_wines,
            max_candidates=max_candidates,
        )
    ]
