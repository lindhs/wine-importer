from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class ScoringPolicy:
    accept_threshold: float = 0.70
    review_threshold: float = 0.55
    ai_score_min: float = 0.55
    ai_score_max: float = 0.70
    ai_score_fuzzy_weight: float = 0.65
    ai_score_confidence_weight: float = 0.35


SCORING_POLICY: Final = ScoringPolicy()

FIELD_WEIGHTS: Final[dict[str, float]] = {
    "producer": 0.35,
    "name": 0.35,
    "appellation": 0.15,
    "vintage": 0.10,
    "varietal": 0.05,
    "region": 0.05,
}

REVIEW_ACCEPT_SCORE: Final = SCORING_POLICY.accept_threshold
REVIEW_MIN_SCORE: Final = SCORING_POLICY.review_threshold

AI_SCORING_MIN_SCORE: Final = SCORING_POLICY.ai_score_min
AI_SCORING_MAX_SCORE: Final = SCORING_POLICY.ai_score_max
AI_SCORE_FUZZY_WEIGHT: Final = SCORING_POLICY.ai_score_fuzzy_weight
AI_SCORE_CONFIDENCE_WEIGHT: Final = SCORING_POLICY.ai_score_confidence_weight


def scoring_policy_manifest() -> dict[str, float]:
    return {
        "accept_threshold": SCORING_POLICY.accept_threshold,
        "review_threshold": SCORING_POLICY.review_threshold,
        "ai_score_min": SCORING_POLICY.ai_score_min,
        "ai_score_max": SCORING_POLICY.ai_score_max,
        "review_accept_score": SCORING_POLICY.accept_threshold,
        "review_min_score": SCORING_POLICY.review_threshold,
        "ai_scoring_min_score": SCORING_POLICY.ai_score_min,
        "ai_scoring_max_score": SCORING_POLICY.ai_score_max,
    }


def is_ai_scoring_candidate(score: float) -> bool:
    return AI_SCORING_MIN_SCORE <= score <= AI_SCORING_MAX_SCORE


def classify_review_score(score: float) -> tuple[str, str]:
    if score > REVIEW_ACCEPT_SCORE:
        return "accepted", "High confidence automatic match"
    if score >= REVIEW_MIN_SCORE:
        return "review_needed", "Candidate requires manual verification"
    return "rejected", "No strong candidate match found"
