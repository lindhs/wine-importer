from wine_importer.review import review_match_result


def _match(score: float) -> dict:
    return {
        "row_number": 1,
        "user_row": {},
        "candidates": [
            {
                "row_number": 1,
                "canonical_id": "1",
                "producer": "Producer",
                "name": "Wine",
                "score": score,
            }
        ],
    }


def test_review_thresholds_are_shared_policy() -> None:
    assert review_match_result(_match(0.71)).status == "accepted"
    assert review_match_result(_match(0.70)).status == "review_needed"
    assert review_match_result(_match(0.55)).status == "review_needed"
    assert review_match_result(_match(0.54)).status == "rejected"
