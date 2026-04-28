import re

from .models import MappedWineRow, NormalizedWineRow

REPLACEMENTS = [
    (r"\bCh\.", "Chateau"),
    (r"\bSt\.", "Saint"),
    (r"\bCab\-Sauv\b", "Cabernet Sauvignon"),
    (r"\b750ml\b", "750 ml"),
    (r"\bPaulliac\b", "Pauillac"),
    (r"\bMaraux\b", "Margaux"),
]


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    for pattern, replacement in REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"[^\w\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


def normalize_mapped_rows(rows: list[MappedWineRow]) -> list[NormalizedWineRow]:
    normalized_rows: list[NormalizedWineRow] = []
    for row in rows:
        normalized_row = NormalizedWineRow(
            row_number=row.row_number,
            producer=row.producer,
            name=row.name,
            vintage=row.vintage,
            region=row.region,
            appellation=row.appellation,
            varietal=row.varietal,
            quantity=row.quantity,
            size=row.size,
            location=row.location,
            bin=row.bin,
            notes=row.notes,
            original=row.original,
            normalized_producer=normalize_text(row.producer),
            normalized_name=normalize_text(row.name),
            normalized_vintage=normalize_text(row.vintage),
            normalized_region=normalize_text(row.region),
            normalized_appellation=normalize_text(row.appellation),
            normalized_varietal=normalize_text(row.varietal),
            normalized_size=normalize_text(row.size),
        )
        normalized_rows.append(normalized_row)
    return normalized_rows
