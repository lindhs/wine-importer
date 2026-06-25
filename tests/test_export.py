import csv
from pathlib import Path

from wine_importer.export import export_reviewed_matches


def test_export_reviewed_matches_uses_canonical_values_and_mapped_fields(tmp_path: Path) -> None:
    output_path = tmp_path / "cellartracker.csv"
    reviewed_matches = [
        {
            "row_number": 1,
            "user_row": {
                "producer": "Ch. Magoe",
                "name": "Chato. Margoe Grand Vin",
                "vintage": "2015",
                "quantity": 2.0,
                "size": "750 ml",
                "location": "Cellar A",
                "bin": "1A",
                "notes": "Original note",
            },
            "best_match": {
                "canonical_id": "1",
                "producer": "Chateau Margaux",
                "name": "Chateau Margaux Grand Vin",
                "vintage": "2015",
            },
            "status": "accepted",
            "reason": "High confidence automatic match",
        }
    ]

    export_reviewed_matches(reviewed_matches, output_path)

    with output_path.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    assert len(rows) == 1
    assert rows[0]["Vintage"] == "2015"
    assert rows[0]["UserWine1"] == "Chateau Margaux"
    assert rows[0]["UserWine2"] == "Chateau Margaux Grand Vin"
    assert rows[0]["Quantity"] == "2"
    assert rows[0]["BottleSize"] == "750 ml"
    assert rows[0]["Location"] == "Cellar A"
    assert rows[0]["Bin"] == "1A"
    assert "Original note" in rows[0]["Notes"]
    assert "match_status=accepted" in rows[0]["Notes"]


def test_export_writes_ct_wine_id_and_url_provenance(tmp_path: Path) -> None:
    output_path = tmp_path / "cellartracker.csv"
    reviewed_matches = [
        {
            "row_number": 1,
            "user_row": {"producer": "Ridge", "name": "Lytton Springs", "vintage": "1993"},
            "best_match": {
                "canonical_id": "ct:18856",
                "ct_wine_id": "18856",
                "producer": "Ridge",
                "name": "Lytton Springs",
                "vintage": "1993",
            },
            "status": "accepted",
            "reason": "High confidence automatic match",
        }
    ]

    export_reviewed_matches(reviewed_matches, output_path)

    with output_path.open("r", encoding="utf-8", newline="") as source:
        notes = list(csv.DictReader(source))[0]["Notes"]
    assert "ct_wine_id=18856" in notes
    assert "ct_url=https://www.cellartracker.com/wine.asp?iWine=18856" in notes


def test_export_reviewed_matches_skips_non_accepted_by_default(tmp_path: Path) -> None:
    output_path = tmp_path / "cellartracker.csv"
    reviewed_matches = [
        {
            "row_number": 1,
            "user_row": {"producer": "Input Producer", "name": "Input Wine"},
            "best_match": {"producer": "Canonical Producer", "name": "Canonical Wine"},
            "status": "review_needed",
            "reason": "Candidate requires manual verification",
        },
        {
            "row_number": 2,
            "user_row": {"producer": "Rejected Producer", "name": "Rejected Wine"},
            "best_match": {"producer": "Wrong Producer", "name": "Wrong Wine"},
            "status": "rejected",
            "reason": "No strong candidate match found",
        },
    ]

    export_reviewed_matches(reviewed_matches, output_path)

    with output_path.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    assert rows == []


def test_export_reviewed_matches_can_export_review_needed(tmp_path: Path) -> None:
    output_path = tmp_path / "cellartracker.csv"
    reviewed_matches = [
        {
            "row_number": 1,
            "user_row": {"producer": "Input Producer", "name": "Input Wine"},
            "best_match": {
                "canonical_id": "9",
                "producer": "Canonical Producer",
                "name": "Canonical Wine",
            },
            "status": "review_needed",
            "reason": "Candidate requires manual verification",
        }
    ]

    export_reviewed_matches(reviewed_matches, output_path, export_review_needed=True)

    with output_path.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    assert len(rows) == 1
    assert rows[0]["UserWine1"] == "Canonical Producer"
    assert "canonical_id=9" in rows[0]["Notes"]


def test_export_reviewed_matches_can_export_rejected_as_unmatched(tmp_path: Path) -> None:
    output_path = tmp_path / "cellartracker.csv"
    reviewed_matches = [
        {
            "row_number": 1,
            "user_row": {"producer": "Input Producer", "name": "Input Wine"},
            "best_match": {
                "canonical_id": "9",
                "producer": "Wrong Producer",
                "name": "Wrong Wine",
            },
            "status": "rejected",
            "reason": "No strong candidate match found",
        }
    ]

    export_reviewed_matches(
        reviewed_matches,
        output_path,
        export_rejected_as_unmatched=True,
    )

    with output_path.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    assert len(rows) == 1
    assert rows[0]["UserWine1"] == "Input Producer"
    assert rows[0]["UserWine2"] == "Input Wine"
    assert "canonical_id" not in rows[0]["Notes"]
