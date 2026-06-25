import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wine_importer.cellartracker_lookup import (
    CTParseError,
    append_resolutions,
    build_search_query,
    build_search_url,
    extract_iwine_ids,
    load_resolution_store,
    parse_wine_definition,
    to_canonical_wine,
)
from wine_importer.cli import app
from wine_importer.models import NormalizedWineRow
from wine_importer.resolution_cache import ResolutionCache
from wine_importer.score import rank_candidates
from wine_importer.search import load_canonical_wines

FIXTURES = Path(__file__).parent / "fixtures" / "cellartracker"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_extract_iwine_ids_dedupes_and_preserves_order() -> None:
    ids = extract_iwine_ids(_fixture("search_results_many.html"))

    assert ids == ["11111", "22222", "33333"]


def test_extract_iwine_ids_returns_empty_for_no_hits() -> None:
    assert extract_iwine_ids(_fixture("search_results_empty.html")) == []


def test_parse_full_wine_page() -> None:
    definition = parse_wine_definition(_fixture("wine_full.html"))

    assert definition.ct_wine_id == "18856"
    assert definition.display_name == "1993 Ridge Lytton Springs"
    assert definition.vintage == "1993"
    assert definition.type == "Red"
    assert definition.producer == "Ridge"
    assert definition.varietal == "Zinfandel Blend"
    assert definition.designation == "Lytton Springs"
    assert definition.vineyard == "Lytton Estate"
    assert definition.country == "USA"
    assert definition.region == "California"
    assert definition.subregion == "Sonoma County"
    assert definition.appellation == "Dry Creek Valley"
    assert definition.url == "https://www.cellartracker.com/wine.asp?iWine=18856"


def test_parse_sparse_wine_page_fills_what_it_can() -> None:
    definition = parse_wine_definition(_fixture("wine_sparse.html"))

    assert definition.ct_wine_id == "43210"
    assert definition.display_name == "NV Gloria Ferrer Blanc de Noirs"
    assert definition.vintage == "NV"
    assert definition.producer == "Gloria Ferrer"
    assert definition.type == "White - Sparkling"
    assert definition.country == "USA"
    assert definition.varietal is None
    assert definition.appellation is None


def test_parse_rejects_search_results_page() -> None:
    with pytest.raises(CTParseError, match="multiple wines"):
        parse_wine_definition(_fixture("search_results_many.html"))


def test_parse_rejects_non_wine_html() -> None:
    with pytest.raises(CTParseError, match="no CellarTracker wine id"):
        parse_wine_definition("<html><body><p>hello</p></body></html>")


def test_build_search_query_skips_empty_fields() -> None:
    row = NormalizedWineRow(
        row_number=1,
        producer="Ch. Talbot",
        name="Grand Cru Classe",
        vintage="1989",
        normalized_producer="chateau talbot",
        normalized_name="grand cru classe",
        normalized_vintage="1989",
    )

    assert build_search_query(row) == "1989 chateau talbot grand cru classe"


def test_build_search_url_encodes_query() -> None:
    url = build_search_url("1989 chateau talbot")

    assert url == (
        "https://www.cellartracker.com/list.asp?Table=List"
        "&szSearch=1989+chateau+talbot"
    )


def test_to_canonical_wine_maps_definition_fields() -> None:
    definition = parse_wine_definition(_fixture("wine_full.html"))

    wine = to_canonical_wine(definition)

    assert wine.id == "ct:18856"
    assert wine.ct_wine_id == "18856"
    assert wine.producer == "Ridge"
    assert wine.name == "Lytton Springs"
    assert wine.vintage == "1993"
    assert wine.region == "California"
    assert wine.appellation == "Dry Creek Valley"
    assert wine.source == "cellartracker_html"


def test_converted_wine_scores_with_ct_wine_id() -> None:
    definition = parse_wine_definition(_fixture("wine_full.html"))
    row = NormalizedWineRow(
        row_number=1,
        producer="Ridge",
        name="Lytton Springs",
        vintage="1993",
        normalized_producer="ridge",
        normalized_name="lytton springs",
        normalized_vintage="1993",
    )

    candidates = rank_candidates(row, [to_canonical_wine(definition)])

    assert candidates[0].ct_wine_id == "18856"
    assert candidates[0].score > 0.7


def test_resolution_store_appends_and_dedupes(tmp_path: Path) -> None:
    store_path = tmp_path / "resolutions.json"
    definition = parse_wine_definition(_fixture("wine_full.html"))

    first_added = append_resolutions([definition], store_path)
    second_added = append_resolutions([definition], store_path)
    store = load_resolution_store(store_path)

    assert first_added == 1
    assert second_added == 0
    assert list(store) == ["18856"]
    assert store["18856"]["definition"]["producer"] == "Ridge"


def test_ct_urls_writes_csv_for_unaccepted_rows(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    rows = [
        NormalizedWineRow(
            row_number=1,
            producer="Ridge",
            name="Lytton Springs",
            vintage="1993",
            normalized_producer="ridge",
            normalized_name="lytton springs",
            normalized_vintage="1993",
        ),
        NormalizedWineRow(
            row_number=2,
            producer="Shafer",
            name="Hillside Select",
            vintage="1990",
            normalized_producer="shafer",
            normalized_name="hillside select",
            normalized_vintage="1990",
        ),
    ]
    (run / "05_normalized_rows.json").write_text(
        json.dumps([row.model_dump() for row in rows]), encoding="utf-8"
    )
    (run / "07_reviewed_matches.json").write_text(
        json.dumps(
            [
                {"row_number": 1, "status": "accepted"},
                {"row_number": 2, "status": "review_needed"},
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["ct-urls", str(run)])

    assert result.exit_code == 0, result.output
    content = (run / "06a_lookup_urls.csv").read_text(encoding="utf-8")
    assert "shafer" in content
    assert "ridge" not in content


def test_ct_ingest_parses_inbox_and_updates_store(tmp_path: Path) -> None:
    run = tmp_path / "run"
    inbox = run / "ct_inbox"
    inbox.mkdir(parents=True)
    shutil.copy(FIXTURES / "wine_full.html", inbox / "wine_full.html")
    (inbox / "junk.html").write_text("<html><body>nothing</body></html>", encoding="utf-8")
    cache_path = tmp_path / "ct_cache.db"

    result = CliRunner().invoke(
        app, ["ct-ingest", str(run), "--cache", str(cache_path)]
    )

    assert result.exit_code == 0, result.output
    resolutions = json.loads((run / "06a_resolutions.json").read_text(encoding="utf-8"))
    statuses = {item["file"]: item["status"] for item in resolutions}
    assert statuses == {"wine_full.html": "parsed", "junk.html": "error"}
    with ResolutionCache(cache_path) as store:
        assert store.get_definition("18856") is not None


def test_ct_lookup_prints_url_for_free_text() -> None:
    result = CliRunner().invoke(app, ["ct-lookup", "1989 chateau talbot"])

    assert result.exit_code == 0, result.output
    assert "szSearch=1989+chateau+talbot" in result.output


def test_ct_build_canonical_preserves_ct_wine_id_through_round_trip(tmp_path: Path) -> None:
    cache_path = tmp_path / "ct_cache.db"
    with ResolutionCache(cache_path) as store:
        store.store_definition(parse_wine_definition(_fixture("wine_full.html")))
    canonical_path = tmp_path / "canonical.csv"

    result = CliRunner().invoke(
        app,
        ["ct-build-canonical", "--out", str(canonical_path), "--cache", str(cache_path)],
    )

    assert result.exit_code == 0, result.output
    wines = load_canonical_wines(canonical_path)
    assert len(wines) == 1
    wine = wines[0]
    assert wine.id == "ct:18856"
    assert wine.ct_wine_id == "18856"
    assert wine.producer == "Ridge"
    assert wine.name == "Lytton Springs"
    assert wine.appellation == "Dry Creek Valley"
    assert wine.source == "cellartracker_html"


def test_built_canonical_drives_a_match_carrying_ct_wine_id(tmp_path: Path) -> None:
    cache_path = tmp_path / "ct_cache.db"
    with ResolutionCache(cache_path) as store:
        store.store_definition(parse_wine_definition(_fixture("wine_full.html")))
    canonical_path = tmp_path / "canonical.csv"
    CliRunner().invoke(
        app,
        ["ct-build-canonical", "--out", str(canonical_path), "--cache", str(cache_path)],
    )

    row = NormalizedWineRow(
        row_number=1,
        producer="Ridge",
        name="Lytton Springs",
        vintage="1993",
        normalized_producer="ridge",
        normalized_name="lytton springs",
        normalized_vintage="1993",
    )
    candidates = rank_candidates(row, load_canonical_wines(canonical_path))

    assert candidates[0].ct_wine_id == "18856"
    assert candidates[0].score > 0.7


def test_local_csv_without_ct_wine_id_keeps_sequential_id() -> None:
    root = Path(__file__).resolve().parents[1]
    wines = load_canonical_wines(root / "data" / "canonical" / "wine_canonical_clean.csv")

    assert wines[0].id == "1"
    assert wines[0].ct_wine_id is None
    assert wines[0].source == "local_csv"
