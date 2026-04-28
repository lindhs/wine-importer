import csv
from pathlib import Path

from wine_importer.report import build_review_report_rows, export_review_report


def _reviewed_match() -> dict:
    return {
        "row_number": 4,
        "user_row": {
            "producer": "Ch. Magoe",
            "name": "Chato Margoe Grand Vin",
            "vintage": "2015",
            "country": "France",
            "region": "Bordeaux",
            "quantity": 2.0,
            "size": "750ml",
            "location": "Cellar A",
            "bin": "1A",
            "notes": "Original note",
        },
        "best_match": {
            "canonical_id": "99",
            "producer": "Chateau Margaux",
            "name": "Chateau Margaux Grand Vin",
            "vintage": "2015",
            "region": "Bordeaux",
            "score": 0.81234,
            "blocking_reason": "producer",
            "producer_score": 0.83,
            "name_score": 0.91,
            "vintage_score": 1.0,
            "region_score": 1.0,
            "hard_conflicts": [],
            "source": {
                "id": "99",
                "producer": "Chateau Margaux",
                "name": "Chateau Margaux Grand Vin",
                "vintage": "2015",
                "country": "France",
                "region": "Bordeaux",
                "appellation": "Medoc",
                "varietal": "Cabernet Sauvignon",
                "quantity": 1,
                "size": "750 ml",
                "notes": "Reference note",
            },
        },
        "status": "accepted",
        "reason": "High confidence automatic match",
        "top_1_score": 0.81234,
        "top_2_score": 0.6,
        "score_margin": 0.21234,
        "num_candidates": 2,
    }


def test_build_review_report_rows_compares_input_to_best_candidate() -> None:
    rows = build_review_report_rows([_reviewed_match()])

    assert rows[0]["row_number"] == "4"
    assert rows[0]["status"] == "accepted"
    assert rows[0]["score"] == "0.8123"
    assert rows[0]["top_1_score"] == "0.8123"
    assert rows[0]["top_2_score"] == "0.6"
    assert rows[0]["score_margin"] == "0.2123"
    assert rows[0]["num_candidates"] == "2"
    assert rows[0]["blocking_reason"] == "producer"
    assert rows[0]["producer_score"] == "0.83"
    assert rows[0]["name_score"] == "0.91"
    assert rows[0]["suggested_action"] == "export"
    assert rows[0]["canonical_id"] == "99"
    assert rows[0]["input_item"] == "2015 | Ch. Magoe | Chato Margoe Grand Vin | Bordeaux | 750ml"
    assert rows[0]["best_candidate_item"] == "2015 | Chateau Margaux | Chateau Margaux Grand Vin | Bordeaux | 750 ml"
    assert rows[0]["candidate_notes"] == "Reference note"
    assert "producer" in rows[0]["diff_fields"]
    assert "name" in rows[0]["diff_fields"]


def test_export_review_report_writes_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "report.csv"

    export_review_report([_reviewed_match()], output_path)

    with output_path.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    assert len(rows) == 1
    assert rows[0]["status"] == "accepted"
    assert rows[0]["candidate_producer"] == "Chateau Margaux"
    assert rows[0]["input_bin"] == "1A"
