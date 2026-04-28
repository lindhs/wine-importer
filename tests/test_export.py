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
