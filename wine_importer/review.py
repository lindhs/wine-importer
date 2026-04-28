from .models import CandidateMatch, ReviewedMatch


def review_match_result(match_result: dict) -> ReviewedMatch:
    candidates = match_result.get("candidates", []) or []
    ordered = sorted(candidates, key=lambda candidate: candidate.get("score", 0.0), reverse=True)
    best_match = None
    if ordered:
        best_match = CandidateMatch(**ordered[0])

    score = best_match.score if best_match is not None else 0.0
    if score >= 0.92:
        status = "accepted"
        reason = "High confidence automatic match"
    elif 0.75 <= score < 0.92:
        status = "review_needed"
        reason = "Candidate requires manual verification"
    else:
        status = "rejected"
        reason = "No strong candidate match found"

    return ReviewedMatch(
        row_number=match_result.get("row_number", 0),
        user_row=match_result.get("user_row", {}),
        best_match=best_match,
        status=status,
        reason=reason,
    )


def review_matches(match_results: list[dict]) -> list[ReviewedMatch]:
    reviewed: list[ReviewedMatch] = []
    for result in match_results:
        reviewed.append(review_match_result(result))
    return reviewed


# TODO: add interactive terminal review support using rich prompts and user confirmation.
