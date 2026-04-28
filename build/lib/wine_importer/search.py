from pathlib import Path

import pandas as pd

from .models import CanonicalWine, NormalizedWineRow


def load_canonical_wines(path: str | Path) -> list[CanonicalWine]:
    df = pd.read_csv(path, dtype=str).fillna("")
    records: list[CanonicalWine] = []
    for index, row in enumerate(df.to_dict(orient="records"), start=1):
        records.append(
            CanonicalWine(
                id=str(index),
                producer=str(row.get("producer", "") or "").strip(),
                name=str(row.get("name", "") or "").strip(),
                vintage=str(row.get("vintage", "") or "").strip(),
                region=str(row.get("region", "") or "").strip(),
                appellation=str(row.get("appellation", "") or "").strip(),
                varietal=str(row.get("varietal", "") or "").strip(),
                quantity=_safe_int(row.get("quantity", "")),
                size=str(row.get("size", "") or "").strip(),
                notes=str(row.get("notes", "") or "").strip(),
            )
        )
    return records


def _safe_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def find_candidate_records(
    normalized_row: NormalizedWineRow,
    canonical_wines: list[CanonicalWine],
    max_candidates: int = 10,
) -> list[CanonicalWine]:
    if not normalized_row.normalized_vintage:
        return canonical_wines[:max_candidates]

    exact_vintage = [wine for wine in canonical_wines if wine.vintage == normalized_row.normalized_vintage]
    if exact_vintage:
        return exact_vintage[:max_candidates]

    if normalized_row.normalized_region:
        region_matches = [
            wine
            for wine in canonical_wines
            if wine.region.lower() == normalized_row.normalized_region
            or wine.appellation.lower() == normalized_row.normalized_appellation
        ]
        if region_matches:
            return region_matches[:max_candidates]

    return canonical_wines[:max_candidates]


# TODO: add embedding-based vector search or approximate nearest neighbor lookup for canonical matches.
