import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from wine_importer.cellartracker_lookup import CTWineDefinition, parse_wine_definition
from wine_importer.cli import app
from wine_importer.models import NormalizedWineRow
from wine_importer.resolution_cache import (
    NEGATIVE_TTL_DAYS,
    POSITIVE_TTL_DAYS,
    ResolutionCache,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cellartracker"


def _definition() -> CTWineDefinition:
    return parse_wine_definition((FIXTURES / "wine_full.html").read_text(encoding="utf-8"))


def test_signature_collapses_accents_and_abbreviations() -> None:
    a = ResolutionCache.signature("Ch. Talbot", "Grand Cru", "1989")
    b = ResolutionCache.signature("Château Talbot", "Grand Cru", "1989")

    assert a == b == "chateau talbot|grand cru|1989"


def test_store_and_get_definition_round_trip(tmp_path: Path) -> None:
    with ResolutionCache(tmp_path / "c.db") as cache:
        cache.store_definition(_definition())
        fetched = cache.get_definition("18856")

    assert fetched is not None
    assert fetched.producer == "Ridge"
    assert fetched.appellation == "Dry Creek Valley"


def test_store_definitions_counts_only_new(tmp_path: Path) -> None:
    with ResolutionCache(tmp_path / "c.db") as cache:
        assert cache.store_definitions([_definition()]) == 1
        assert cache.store_definitions([_definition()]) == 0


def test_all_canonical_carries_ct_wine_id(tmp_path: Path) -> None:
    with ResolutionCache(tmp_path / "c.db") as cache:
        cache.store_definition(_definition())
        wines = cache.all_canonical()

    assert len(wines) == 1
    assert wines[0].id == "ct:18856"
    assert wines[0].ct_wine_id == "18856"
    assert wines[0].source == "cellartracker_html"


def test_record_resolution_then_lookup_hits(tmp_path: Path) -> None:
    with ResolutionCache(tmp_path / "c.db") as cache:
        sig = ResolutionCache.signature("Ridge", "Lytton Springs", "1993")
        cache.record_resolution(sig, _definition(), score=0.91)
        hit = cache.lookup(sig)

    assert hit is not None
    assert hit.ct_wine_id == "18856"
    assert hit.definition is not None
    assert hit.score == 0.91
    assert not hit.is_negative


def test_positive_resolution_expires_after_ttl(tmp_path: Path) -> None:
    with ResolutionCache(tmp_path / "c.db") as cache:
        sig = ResolutionCache.signature("Ridge", "Lytton Springs", "1993")
        cache.record_resolution(sig, _definition())
        future = datetime.now(timezone.utc) + timedelta(days=POSITIVE_TTL_DAYS + 1)

        assert cache.lookup(sig) is not None
        assert cache.lookup(sig, now=future) is None


def test_negative_cache_records_miss_with_short_ttl(tmp_path: Path) -> None:
    with ResolutionCache(tmp_path / "c.db") as cache:
        sig = ResolutionCache.signature("Imaginary", "Wine", "2099")
        cache.record_miss(sig)
        hit = cache.lookup(sig)
        expired = cache.lookup(
            sig, now=datetime.now(timezone.utc) + timedelta(days=NEGATIVE_TTL_DAYS + 1)
        )

    assert hit is not None
    assert hit.is_negative
    assert hit.definition is None
    assert expired is None


def test_signature_for_row_uses_normalized_fields() -> None:
    row = NormalizedWineRow(
        row_number=1,
        producer="Ch. Talbot",
        name="Grand Cru",
        vintage="1989",
        normalized_producer="chateau talbot",
        normalized_name="grand cru",
        normalized_vintage="1989",
    )

    assert ResolutionCache.signature_for_row(row) == "chateau talbot|grand cru|1989"


def test_import_json_store_migrates_definitions(tmp_path: Path) -> None:
    json_path = tmp_path / "resolutions.json"
    json_path.write_text(
        json.dumps(
            {
                "18856": {
                    "definition": {
                        "ct_wine_id": "18856",
                        "display_name": "1993 Ridge Lytton Springs",
                        "producer": "Ridge",
                        "url": "https://www.cellartracker.com/wine.asp?iWine=18856",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with ResolutionCache(tmp_path / "c.db") as cache:
        added = cache.import_json_store(json_path)
        fetched = cache.get_definition("18856")

    assert added == 1
    assert fetched is not None and fetched.producer == "Ridge"


def test_stats_and_clear(tmp_path: Path) -> None:
    with ResolutionCache(tmp_path / "c.db") as cache:
        sig = ResolutionCache.signature("Ridge", "Lytton Springs", "1993")
        cache.record_resolution(sig, _definition())
        cache.record_miss(ResolutionCache.signature("X", "Y", "2000"))

        stats = cache.stats()
        assert stats == {
            "wine_definitions": 1,
            "resolutions_positive": 1,
            "resolutions_negative": 1,
        }

        cache.clear()
        assert cache.stats() == {
            "wine_definitions": 0,
            "resolutions_positive": 0,
            "resolutions_negative": 0,
        }


def test_cache_stats_cli(tmp_path: Path) -> None:
    cache_path = tmp_path / "c.db"
    with ResolutionCache(cache_path) as cache:
        cache.store_definition(_definition())

    result = CliRunner().invoke(app, ["cache", "stats", "--cache", str(cache_path)])

    assert result.exit_code == 0, result.output
    assert "wine_definitions: 1" in result.output


def test_cache_clear_cli(tmp_path: Path) -> None:
    cache_path = tmp_path / "c.db"
    with ResolutionCache(cache_path) as cache:
        cache.store_definition(_definition())

    result = CliRunner().invoke(app, ["cache", "clear", "--yes", "--cache", str(cache_path)])

    assert result.exit_code == 0, result.output
    with ResolutionCache(cache_path) as cache:
        assert cache.stats()["wine_definitions"] == 0
