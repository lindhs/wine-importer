from wine_importer.config import (
    EXISTENCE_LOOKUP_POLICY,
    SCORING_POLICY,
    classify_review_score,
    is_ai_scoring_candidate,
    scoring_policy_manifest,
)
from wine_importer.models import CanonicalWine, NormalizedWineRow
from wine_importer.score import score_candidate_breakdown


def _barbaresco_row(vineyard: str | None = None) -> NormalizedWineRow:
    return NormalizedWineRow(
        row_number=1,
        producer="Produttori del Barbaresco",
        name="Barbaresco Riserva",
        vintage="2016",
        vineyard=vineyard,
        normalized_producer="produttori del barbaresco",
        normalized_name="barbaresco riserva",
        normalized_vintage="2016",
        normalized_vineyard=vineyard.lower() if vineyard else None,
    )


def _barbaresco_canonical(ct_id: str, vineyard: str | None) -> CanonicalWine:
    return CanonicalWine(
        id=f"ct:{ct_id}",
        ct_wine_id=ct_id,
        producer="Produttori del Barbaresco",
        name="Barbaresco Riserva",
        vintage="2016",
        vineyard=vineyard,
        appellation="Barbaresco",
    )


def test_vineyard_breaks_tie_between_identical_wines() -> None:
    row = _barbaresco_row(vineyard="Asili")
    asili = _barbaresco_canonical("111", "Asili")
    rabaja = _barbaresco_canonical("222", "Rabajà")

    asili_score = score_candidate_breakdown(row, asili).score
    rabaja_breakdown = score_candidate_breakdown(row, rabaja)

    assert asili_score > rabaja_breakdown.score
    assert "vineyard" in rabaja_breakdown.hard_conflicts


def test_matching_vineyard_adds_bonus() -> None:
    row = _barbaresco_row(vineyard="Asili")
    with_vineyard = score_candidate_breakdown(row, _barbaresco_canonical("111", "Asili")).score
    no_vineyard_on_canonical = score_candidate_breakdown(
        row, _barbaresco_canonical("111", None)
    ).score

    assert with_vineyard > no_vineyard_on_canonical


def test_tiebreaker_is_noop_when_canonical_lacks_field() -> None:
    # Golden-safety: a canonical without vineyard/subregion (the local-CSV case)
    # scores identically whether or not the row carries those fields.
    canonical = _barbaresco_canonical("111", None)
    with_row_vineyard = score_candidate_breakdown(_barbaresco_row("Asili"), canonical).score
    without_row_vineyard = score_candidate_breakdown(_barbaresco_row(None), canonical).score

    assert with_row_vineyard == without_row_vineyard


def test_existence_policy_is_stricter_than_import() -> None:
    assert classify_review_score(0.80)[0] == "accepted"
    assert classify_review_score(0.80, EXISTENCE_LOOKUP_POLICY)[0] == "review_needed"
    assert classify_review_score(0.60, EXISTENCE_LOOKUP_POLICY)[0] == "rejected"


def test_ai_scoring_band_shifts_with_policy() -> None:
    assert not is_ai_scoring_candidate(0.82, SCORING_POLICY)
    assert is_ai_scoring_candidate(0.82, EXISTENCE_LOOKUP_POLICY)


def test_manifest_records_active_policy_name() -> None:
    assert scoring_policy_manifest()["policy_name"] == "import"
    existence = scoring_policy_manifest(EXISTENCE_LOOKUP_POLICY)
    assert existence["policy_name"] == "existence_lookup"
    assert existence["accept_threshold"] == 0.85
