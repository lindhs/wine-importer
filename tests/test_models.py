from wine_importer.models import CandidateMatch, CanonicalWine, NormalizedWineRow
from wine_importer.score import rank_candidates


def test_canonical_wine_minimal_fields_get_safe_defaults() -> None:
    wine = CanonicalWine(id="ct:12345", producer="Ridge", name="Lytton Springs", vintage="1993")

    assert wine.ct_wine_id is None
    assert wine.type is None
    assert wine.designation is None
    assert wine.vineyard is None
    assert wine.region == ""
    assert wine.subregion is None
    assert wine.appellation == ""
    assert wine.varietal == ""
    assert wine.source == "local_csv"


def test_canonical_wine_round_trips_all_fields() -> None:
    wine = CanonicalWine(
        id="ct:67890",
        ct_wine_id="67890",
        producer="Produttori del Barbaresco",
        name="Barbaresco Riserva",
        vintage="2016",
        type="Red",
        designation="Riserva",
        vineyard="Asili",
        country="Italy",
        region="Piedmont",
        subregion="Langhe",
        appellation="Barbaresco",
        varietal="Nebbiolo",
        quantity=3,
        size="750 ml",
        notes="library release",
        source="cellartracker_html",
    )

    assert CanonicalWine.model_validate(wine.model_dump()) == wine


def test_canonical_wine_loads_legacy_dict_without_new_fields() -> None:
    legacy = {
        "id": "row-1",
        "producer": "Ridge",
        "name": "Monte Bello",
        "vintage": "2015",
        "region": "Santa Cruz Mountains",
        "appellation": "Santa Cruz Mountains",
        "varietal": "Cabernet Sauvignon",
    }

    wine = CanonicalWine.model_validate(legacy)

    assert wine.ct_wine_id is None
    assert wine.source == "local_csv"


def test_candidate_match_round_trips_ct_wine_id() -> None:
    match = CandidateMatch(row_number=1, canonical_id="ct:42", ct_wine_id="42", score=0.9)

    assert CandidateMatch.model_validate(match.model_dump()).ct_wine_id == "42"
    assert CandidateMatch(row_number=2).ct_wine_id is None


def test_rank_candidates_carries_ct_wine_id_from_canonical() -> None:
    row = NormalizedWineRow(
        row_number=1,
        producer="Ridge",
        name="Lytton Springs",
        vintage="1993",
        normalized_producer="ridge",
        normalized_name="lytton springs",
        normalized_vintage="1993",
    )
    canonical = CanonicalWine(
        id="ct:111",
        ct_wine_id="111",
        producer="Ridge",
        name="Lytton Springs",
        vintage="1993",
    )

    candidates = rank_candidates(row, [canonical])

    assert candidates[0].ct_wine_id == "111"
