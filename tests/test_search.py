from pathlib import Path

from wine_importer.models import NormalizedWineRow
from wine_importer.search import (
    find_candidate_records,
    find_candidate_records_with_diagnostics,
    load_canonical_wines,
)


def test_load_canonical_wines_with_capital_headers(tmp_path: Path) -> None:
    path = tmp_path / "canonical.csv"
    path.write_text(
        "Producer,Name,Vintage,Country,Region,Appellation,Varietal,Quantity,Bottle Size,Notes\n"
        "Canopy,Tres Patas Garnacha,,Spain,Méntrida,Spanish Grenache,Spanish Grenache,1,750ml,\n",
        encoding="utf-8",
    )

    wines = load_canonical_wines(path)

    assert len(wines) == 1
    assert wines[0].producer == "Canopy"
    assert wines[0].name == "Tres Patas Garnacha"
    assert wines[0].vintage == ""
    assert wines[0].country == "Spain"
    assert wines[0].region == "Méntrida"
    assert wines[0].appellation == "Spanish Grenache"
    assert wines[0].size == "750ml"


def test_load_canonical_wines_handles_legacy_rows_with_extra_columns(tmp_path: Path) -> None:
    path = tmp_path / "canonical.csv"
    path.write_text(
        "producer,name,vintage,region,appellation,varietal,quantity,size,notes\n"
        "Canopy,Tres Patas Garnacha,,Spain,Méntrida,Spanish Grenache,1,750ml,,,Reference note\n",
        encoding="utf-8",
    )

    wines = load_canonical_wines(path)

    assert len(wines) == 1
    assert wines[0].country == "Spain"
    assert wines[0].region == "Méntrida"
    assert wines[0].appellation == "Méntrida"
    assert wines[0].varietal == "Spanish Grenache"
    assert wines[0].notes == "Reference note"


def test_find_candidate_records_blocks_on_identity_fields(tmp_path: Path) -> None:
    path = tmp_path / "canonical.csv"
    path.write_text(
        "Producer,Name,Vintage,Country,Region,Appellation,Varietal,Quantity,Bottle Size,Notes\n"
        "Canopy,Tres Patas Garnacha,2018,Spain,Méntrida,Spanish Grenache,Spanish Grenache,1,750ml,\n",
        encoding="utf-8",
    )

    wines = load_canonical_wines(path)
    row = NormalizedWineRow(
        row_number=1,
        producer="Canopy",
        name="Tres Patas Garnacha",
        vintage="2018",
        country="Spain",
        region="Méntrida",
        appellation="Spanish Grenache",
        varietal="Spanish Grenache",
        normalized_producer="canopy",
        normalized_name="tres patas garnacha",
        normalized_vintage="2018",
        normalized_country="spain",
        normalized_region="mentrida",
        normalized_appellation="spanish grenache",
        normalized_varietal="spanish grenache",
    )

    candidates = find_candidate_records(row, wines)
    assert len(candidates) == 1
    assert candidates[0].producer == "Canopy"

    diagnostic_candidates = find_candidate_records_with_diagnostics(row, wines)
    assert diagnostic_candidates[0].blocking_reason == "producer"


def test_find_candidate_records_rejects_without_strong_overlap(tmp_path: Path) -> None:
    path = tmp_path / "canonical.csv"
    path.write_text(
        "Producer,Name,Vintage,Country,Region,Appellation,Varietal,Quantity,Bottle Size,Notes\n"
        "Canopy,Tres Patas Garnacha,2018,Spain,Méntrida,Spanish Grenache,1,750ml,,\n",
        encoding="utf-8",
    )

    wines = load_canonical_wines(path)
    row = NormalizedWineRow(
        row_number=1,
        producer="Different",
        name="Unrelated Wine",
        vintage="2018",
        country="France",
        region="Bordeaux",
        appellation="Bordeaux",
        varietal="Merlot",
        normalized_producer="different",
        normalized_name="unrelated wine",
        normalized_vintage="2018",
        normalized_country="france",
        normalized_region="bordeaux",
        normalized_appellation="bordeaux",
        normalized_varietal="merlot",
    )

    candidates = find_candidate_records(row, wines)
    assert candidates == []


def test_find_candidate_records_returns_typos_via_approximate_lookup(tmp_path: Path) -> None:
    path = tmp_path / "canonical.csv"
    path.write_text(
        "Producer,Name,Vintage,Country,Region,Appellation,Varietal,Quantity,Bottle Size,Notes\n"
        "Chateau Margaux,Chateau Margaux Grand Vin,2015,France,Bordeaux,Medoc,Cabernet Sauvignon,2,750ml,\n"
        "Chateau Lagrange,Chateau Lagrange,2015,France,Bordeaux,Medoc,Cabernet Sauvignon,2,750ml,\n",
        encoding="utf-8",
    )

    wines = load_canonical_wines(path)
    row = NormalizedWineRow(
        row_number=1,
        producer="Ch. Magoe",
        name="Chato. Margoe Grand Vin",
        vintage="2015",
        country="France",
        region="Bordo",
        appellation="Medoc",
        varietal="Cab-Sauv",
        normalized_producer="chateau magoe",
        normalized_name="chato margoe grand vin",
        normalized_vintage="2015",
        normalized_country="france",
        normalized_region="bordo",
        normalized_appellation="medoc",
        normalized_varietal="cabernet sauvignon",
    )

    candidates = find_candidate_records(row, wines)

    assert candidates
    assert candidates[0].producer == "Chateau Margaux"
