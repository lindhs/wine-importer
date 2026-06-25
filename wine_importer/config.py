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
    name: str = "import"


# Import matching: "which catalogued wine does this row map to?" — lenient,
# because a near miss still beats leaving the row unmatched.
SCORING_POLICY: Final = ScoringPolicy()

# Existence lookup: "does this exact wine already exist in CellarTracker?" — a
# stricter question, so accept/review thresholds are higher and the AI
# arbitration band shifts up with them.
EXISTENCE_LOOKUP_POLICY: Final = ScoringPolicy(
    accept_threshold=0.85,
    review_threshold=0.65,
    ai_score_min=0.65,
    ai_score_max=0.85,
    name="existence_lookup",
)

POLICIES: Final[dict[str, ScoringPolicy]] = {
    SCORING_POLICY.name: SCORING_POLICY,
    EXISTENCE_LOOKUP_POLICY.name: EXISTENCE_LOOKUP_POLICY,
}

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


def scoring_policy_manifest(policy: ScoringPolicy = SCORING_POLICY) -> dict[str, float | str]:
    return {
        "policy_name": policy.name,
        "accept_threshold": policy.accept_threshold,
        "review_threshold": policy.review_threshold,
        "ai_score_min": policy.ai_score_min,
        "ai_score_max": policy.ai_score_max,
        "review_accept_score": policy.accept_threshold,
        "review_min_score": policy.review_threshold,
        "ai_scoring_min_score": policy.ai_score_min,
        "ai_scoring_max_score": policy.ai_score_max,
    }


def is_ai_scoring_candidate(score: float, policy: ScoringPolicy = SCORING_POLICY) -> bool:
    return policy.ai_score_min <= score <= policy.ai_score_max


def classify_review_score(
    score: float, policy: ScoringPolicy = SCORING_POLICY
) -> tuple[str, str]:
    if score > policy.accept_threshold:
        return "accepted", "High confidence automatic match"
    if score >= policy.review_threshold:
        return "review_needed", "Candidate requires manual verification"
    return "rejected", "No strong candidate match found"
