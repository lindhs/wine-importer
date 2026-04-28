import re
import unicodedata

from .models import MappedWineRow, NormalizedWineRow

REPLACEMENTS = [
    (r"\bch\.?\b", "chateau"),
    (r"\bst\.?\b", "saint"),
    (r"\bcab[- ]?sauv\b", "cabernet sauvignon"),
    (r"\b(\d+)ml\b", r"\1 ml"),
    (r"\bpaulliac\b", "pauillac"),
    (r"\bmaraux\b", "margaux"),
    (r"\bconnaught\b", "connaught"),
]

SIZE_PATTERNS = [
    (r"\b(\d+(?:\.\d+)?)\s*(?:ml)\b", lambda v: f"{int(float(v))} ml"),
    (r"\b(\d+(?:\.\d+)?)\s*(?:l|liter|litre)\b", lambda v: f"{int(float(v) * 1000)} ml"),
    (r"\bmagnum\b", lambda _: "1500 ml"),
    (r"\bjeroboam\b", lambda _: "3000 ml"),
]

NV_PATTERNS = [r"\b(?:nv|n/v|non[- ]vintage|non[- ]vintage|nonvintage)\b", r"\bn\.?v\.?\b"]


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    normalized = strip_accents(normalized)
    normalized = normalized.lower()
    for pattern, replacement in REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized)
    normalized = re.sub(r"[^\w\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def normalize_vintage(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if any(re.search(pattern, normalized) for pattern in NV_PATTERNS):
        return "nv"
    match = re.search(r"\b(18|19|20)\d{2}\b", normalized)
    if match:
        return match.group(0)
    return normalized


def normalize_size(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = strip_accents(str(value).strip().lower())
    for pattern, transform in SIZE_PATTERNS:
        match = re.search(pattern, normalized)
        if match:
            return transform(match.group(1))
    normalized = re.sub(r"[^\w\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def normalize_mapped_rows(rows: list[MappedWineRow]) -> list[NormalizedWineRow]:
    normalized_rows: list[NormalizedWineRow] = []
    for row in rows:
        normalized_row = NormalizedWineRow(
            row_number=row.row_number,
            producer=row.producer,
            name=row.name,
            vineyard=row.vineyard,
            vintage=row.vintage,
            country=row.country,
            region=row.region,
            subregion=row.subregion,
            appellation=row.appellation,
            varietal=row.varietal,
            quantity=row.quantity,
            size=row.size,
            bottle_size=row.bottle_size,
            purchase_date=row.purchase_date,
            location=row.location,
            bin=row.bin,
            notes=row.notes,
            ratings=row.ratings,
            original=row.original,
            normalized_producer=normalize_text(row.producer),
            normalized_name=normalize_text(row.name),
            normalized_vineyard=normalize_text(row.vineyard),
            normalized_vintage=normalize_vintage(row.vintage),
            normalized_country=normalize_text(row.country),
            normalized_region=normalize_text(row.region),
            normalized_subregion=normalize_text(row.subregion),
            normalized_appellation=normalize_text(row.appellation),
            normalized_varietal=normalize_text(row.varietal),
            normalized_size=normalize_size(row.size),
            normalized_bottle_size=normalize_size(row.bottle_size),
        )
        normalized_rows.append(normalized_row)
    return normalized_rows
