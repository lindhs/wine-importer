from wine_importer.models import CanonicalWine, NormalizedWineRow
from wine_importer.score import score_candidate, rank_candidates


def test_score_candidate_returns_high_similarity_for_close_match():
    normalized = NormalizedWineRow(
        row_number=1,
        producer="chateau margaux",
        name="chateau margaux grand vin",
        vintage="2015",
        region="bordeaux",
        appellation="medoc",
        varietal="cabernet sauvignon",
        size="750 ml",
        original={},
    )
    canonical = CanonicalWine(
        id="1",
        producer="Chateau Margaux",
        name="Chateau Margaux Grand Vin",
        vintage="2015",
        region="Bordeaux",
        appellation="Medoc",
        varietal="Cabernet Sauvignon",
        quantity=2,
        size="750 ml",
        notes="Reference record",
    )
    score = score_candidate(normalized, canonical)
    assert score > 0.9


def test_rank_candidates_orders_best_matches_first():
    normalized = NormalizedWineRow(
        row_number=1,
        producer="chateau margaux",
        name="chateau margaux grand vin",
        vintage="2015",
        region="bordeaux",
        appellation="medoc",
        varietal="cabernet sauvignon",
        original={},
    )
    candidates = [
        CanonicalWine(
            id="1",
            producer="Chateau Margaux",
            name="Chateau Margaux Grand Vin",
            vintage="2015",
            region="Bordeaux",
            appellation="Medoc",
            varietal="Cabernet Sauvignon",
        ),
        CanonicalWine(
            id="2",
            producer="Chateau Lagrange",
            name="Chateau Lagrange",
            vintage="2015",
            region="Bordeaux",
            appellation="Medoc",
            varietal="Cabernet Sauvignon",
        ),
    ]
    ranked = rank_candidates(normalized, candidates)
    assert ranked[0].canonical_id == "1"
    assert ranked[0].score >= ranked[1].score
