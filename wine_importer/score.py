import logging
from dataclasses import dataclass

from rapidfuzz import fuzz

from .config import FIELD_WEIGHTS, is_ai_scoring_candidate
from .models import CandidateMatch, CanonicalWine, NormalizedWineRow
from .normalize import normalize_text, normalize_vintage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CandidateScoreBreakdown:
    score: float
    producer_score: float
    name_score: float
    appellation_score: float
    vintage_score: float
    varietal_score: float
    region_score: float
    hard_conflicts: list[str]


def _score_component(value_a: str | None, value_b: str | None) -> float:
    if not value_a or not value_b:
        return 0.0
    value_a = normalize_text(value_a) or ""
    value_b = normalize_text(value_b) or ""
    if not value_a or not value_b:
        return 0.0
    return fuzz.token_sort_ratio(value_a, value_b) / 100.0


def score_candidate_breakdown(
    normalized_row: NormalizedWineRow,
    canonical: CanonicalWine,
) -> CandidateScoreBreakdown:
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
    hard_conflicts: list[str] = []

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
        hard_conflicts.append("country")

    row_vintage = normalize_vintage(normalized_row.normalized_vintage or normalized_row.vintage)
    canonical_vintage = normalize_vintage(canonical.vintage)
    if row_vintage and canonical_vintage and row_vintage != canonical_vintage:
        total -= 0.5
        hard_conflicts.append("vintage")

    if producer_score < 0.2 and name_score < 0.3:
        total = 0.0

    return CandidateScoreBreakdown(
        score=min(max(total, 0.0), 1.0),
        producer_score=producer_score,
        name_score=name_score,
        appellation_score=appellation_score,
        vintage_score=vintage_score,
        varietal_score=varietal_score,
        region_score=region_score,
        hard_conflicts=hard_conflicts,
    )


def score_candidate(normalized_row: NormalizedWineRow, canonical: CanonicalWine) -> float:
    return score_candidate_breakdown(normalized_row, canonical).score


def rank_candidates(
    normalized_row: NormalizedWineRow,
    canonical_wines: list[CanonicalWine],
    top_n: int = 5,
    use_ai_scoring: bool = False,
    blocking_reasons: dict[str, str] | None = None,
) -> list[CandidateMatch]:
    candidate_scores: list[CandidateMatch] = []
    for canonical in canonical_wines:
        breakdown = score_candidate_breakdown(normalized_row, canonical)
        score = breakdown.score

        # Enhance ambiguous matches with AI semantic verification
        if use_ai_scoring and is_ai_scoring_candidate(score):
            try:
                from .ai_schema import score_candidate_with_ai

                enhanced_score = score_candidate_with_ai(
                    normalized_row.producer,
                    normalized_row.name,
                    normalized_row.vintage,
                    normalized_row.region,
                    canonical.producer,
                    canonical.name,
                    canonical.vintage,
                    canonical.region,
                    score,
                )
                logger.debug(
                    f"Row {normalized_row.row_number}: AI enhanced score for "
                    f"{canonical.producer} {canonical.name} from {score:.2f} to {enhanced_score:.2f}"
                )
                score = enhanced_score
            except Exception as e:
                logger.debug(f"AI scoring failed (continuing with fuzzy score): {e}")

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
                blocking_reason=(blocking_reasons or {}).get(canonical.id),
                producer_score=breakdown.producer_score,
                name_score=breakdown.name_score,
                vintage_score=breakdown.vintage_score,
                region_score=breakdown.region_score,
                appellation_score=breakdown.appellation_score,
                varietal_score=breakdown.varietal_score,
                hard_conflicts=breakdown.hard_conflicts,
                source=canonical.model_dump(),
            )
        )
    ordered = sorted(candidate_scores, key=lambda item: item.score, reverse=True)
    return ordered[:top_n]
