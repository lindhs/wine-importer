from .config import classify_review_score
from .models import CandidateMatch, ReviewedMatch


def review_match_result(match_result: dict) -> ReviewedMatch:
    candidates = match_result.get("candidates", []) or []
    ordered = sorted(candidates, key=lambda candidate: candidate.get("score", 0.0), reverse=True)
    best_match = None
    if ordered:
        best_match = CandidateMatch(**ordered[0])

    score = best_match.score if best_match is not None else 0.0
    status, reason = classify_review_score(score)
    top_1_score = float(ordered[0].get("score", 0.0)) if ordered else None
    top_2_score = float(ordered[1].get("score", 0.0)) if len(ordered) > 1 else None
    score_margin = (
        top_1_score - top_2_score
        if top_1_score is not None and top_2_score is not None
        else None
    )

    return ReviewedMatch(
        row_number=match_result.get("row_number", 0),
        user_row=match_result.get("user_row", {}),
        best_match=best_match,
        status=status,
        reason=reason,
        top_1_score=match_result.get("top_1_score", top_1_score),
        top_2_score=match_result.get("top_2_score", top_2_score),
        score_margin=match_result.get("score_margin", score_margin),
        num_candidates=match_result.get("num_candidates", len(ordered)),
    )


def review_matches(match_results: list[dict]) -> list[ReviewedMatch]:
    reviewed: list[ReviewedMatch] = []
    for result in match_results:
        reviewed.append(review_match_result(result))
    return reviewed


# TODO: add interactive terminal review support using rich prompts and user confirmation.
