from rapidfuzz import fuzz

from .models import CandidateMatch, CanonicalWine, NormalizedWineRow
from .normalize import normalize_text, normalize_vintage

FIELD_WEIGHTS = {
    "producer": 0.35,
    "name": 0.35,
    "appellation": 0.15,
    "vintage": 0.10,
    "varietal": 0.05,
    "region": 0.05,
}


def _score_component(value_a: str | None, value_b: str | None) -> float:
    if not value_a or not value_b:
        return 0.0
    value_a = normalize_text(value_a) or ""
    value_b = normalize_text(value_b) or ""
    if not value_a or not value_b:
        return 0.0
    return fuzz.token_sort_ratio(value_a, value_b) / 100.0


def score_candidate(normalized_row: NormalizedWineRow, canonical: CanonicalWine) -> float:
    producer_score = _score_component(
        normalized_row.normalized_producer or normalized_row.producer,
        canonical.producer,
    )
    name_score = _score_component(
        normalized_row.normalized_name or normalized_row.name,
        canonical.name,
    )
    region_score = _score_component(
        normalized_row.normalized_region or normalized_row.region,
        canonical.region,
    )
    appellation_score = _score_component(
        normalized_row.normalized_appellation or normalized_row.appellation,
        canonical.appellation,
    )
    vintage_score = _score_component(
        normalized_row.normalized_vintage or normalized_row.vintage,
        canonical.vintage,
    )
    varietal_score = _score_component(
        normalized_row.normalized_varietal or normalized_row.varietal,
        canonical.varietal,
    )

    total = (
        FIELD_WEIGHTS["producer"] * producer_score
        + FIELD_WEIGHTS["name"] * name_score
        + FIELD_WEIGHTS["appellation"] * appellation_score
        + FIELD_WEIGHTS["vintage"] * vintage_score
        + FIELD_WEIGHTS["varietal"] * varietal_score
        + FIELD_WEIGHTS["region"] * region_score
    )

    row_country = normalized_row.normalized_country or normalize_text(normalized_row.country)
    canonical_country = normalize_text(canonical.country) if canonical.country else None
    if row_country and canonical_country and row_country != canonical_country:
        total -= 0.35

    row_vintage = normalize_vintage(normalized_row.normalized_vintage or normalized_row.vintage)
    canonical_vintage = normalize_vintage(canonical.vintage)
    if row_vintage and canonical_vintage and row_vintage != canonical_vintage:
        total -= 0.5

    if producer_score < 0.2 and name_score < 0.3:
        return 0.0

    return min(max(total, 0.0), 1.0)


def rank_candidates(
    normalized_row: NormalizedWineRow,
    canonical_wines: list[CanonicalWine],
    top_n: int = 5,
) -> list[CandidateMatch]:
    candidate_scores: list[CandidateMatch] = []
    for canonical in canonical_wines:
        score = score_candidate(normalized_row, canonical)
        candidate_scores.append(
            CandidateMatch(
                row_number=normalized_row.row_number,
                canonical_id=canonical.id,
                producer=canonical.producer,
                name=canonical.name,
                vintage=canonical.vintage,
                region=canonical.region,
                appellation=canonical.appellation,
                varietal=canonical.varietal,
                score=score,
                source=canonical.model_dump(),
            )
        )
    ordered = sorted(candidate_scores, key=lambda item: item.score, reverse=True)
    return ordered[:top_n]
