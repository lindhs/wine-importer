import json
import os
import csv
from pathlib import Path

import yaml

from wine_importer.ai_runtime import load_project_env
from wine_importer.pipeline import run_pipeline
from wine_importer.resolution_cache import ResolutionCache


def test_pipeline_creates_artifacts(tmp_path: Path, seed_cache) -> None:
    root = Path(__file__).resolve().parents[1]
    input_path = root / "data" / "raw" / "sample_input.csv"
    canonical_path = root / "data" / "canonical" / "sample_canonical.csv"
    out_dir = tmp_path / "run"
    ct_cache = seed_cache(canonical_path)

    artifacts = run_pipeline(str(input_path), str(out_dir), ct_cache=ct_cache)

    assert Path(artifacts["raw_copy"]).exists()
    assert Path(artifacts["structure_report"]).exists()
    assert Path(artifacts["parsed"]).exists()
    assert Path(artifacts["ingestion_quarantine"]).exists()
    assert Path(artifacts["ingestion_quarantine_csv"]).exists()
    assert Path(artifacts["mapping"]).exists()
    assert Path(artifacts["mapped"]).exists()
    assert Path(artifacts["normalized"]).exists()
    assert Path(artifacts["candidates"]).exists()
    assert Path(artifacts["reviewed"]).exists()
    assert Path(artifacts["export"]).exists()
    assert Path(artifacts["report"]).exists()

    reviewed = json.loads(Path(artifacts["reviewed"]).read_text(encoding="utf-8"))
    candidates = json.loads(Path(artifacts["candidates"]).read_text(encoding="utf-8"))
    manifest = yaml.safe_load(Path(artifacts["manifest"]).read_text(encoding="utf-8"))
    structure_report = json.loads(Path(artifacts["structure_report"]).read_text(encoding="utf-8"))
    quarantine = json.loads(Path(artifacts["ingestion_quarantine"]).read_text(encoding="utf-8"))
    assert isinstance(reviewed, list)
    assert len(reviewed) >= 1
    assert "producer" in reviewed[0]["user_row"]
    assert "top_1_score" in candidates[0]
    assert "score_margin" in candidates[0]
    assert "blocking_reason" in candidates[0]["candidates"][0]
    assert manifest["policy"]["accept_threshold"] == 0.70
    assert manifest["policy"]["review_threshold"] == 0.55
    assert manifest["export_policy"]["export_review_needed"] is False
    assert manifest["artifacts"]["structure_report"] == artifacts["structure_report"]
    assert manifest["artifacts"]["ingestion_quarantine"] == artifacts["ingestion_quarantine"]
    assert manifest["stats"]["rows_quarantined"] == 0
    assert structure_report["selected_regions"]
    assert quarantine == []


def test_pipeline_writes_ai_input_quality_artifact(tmp_path: Path, monkeypatch, seed_cache) -> None:
    root = Path(__file__).resolve().parents[1]
    input_path = root / "data" / "raw" / "sample_input.csv"
    canonical_path = root / "data" / "canonical" / "sample_canonical.csv"
    out_dir = tmp_path / "run"
    ct_cache = seed_cache(canonical_path)

    def fake_assessment(sample_data):
        return {"completeness": 8, "rows_sampled": len(sample_data)}

    monkeypatch.setattr(
        "wine_importer.ai_schema.assess_input_quality_with_ai",
        fake_assessment,
    )

    artifacts = run_pipeline(
        str(input_path),
        str(out_dir),
        ct_cache=ct_cache,
        use_ai=True,
    )

    quality = json.loads(Path(artifacts["input_quality"]).read_text(encoding="utf-8"))
    manifest = yaml.safe_load(Path(artifacts["manifest"]).read_text(encoding="utf-8"))

    assert quality["completeness"] == 8
    assert quality["rows_sampled"] > 0
    assert manifest["artifacts"]["input_quality"] == artifacts["input_quality"]
    assert manifest["policy"]["review_min_score"] == 0.55
    assert manifest["policy"]["review_threshold"] == 0.55


def test_pipeline_extracts_table_after_preamble(tmp_path: Path, seed_cache) -> None:
    root = Path(__file__).resolve().parents[1]
    canonical_path = root / "data" / "canonical" / "sample_canonical.csv"
    ct_cache = seed_cache(canonical_path)
    input_path = tmp_path / "preamble.csv"
    input_path.write_text(
        "My Cellar Inventory\n"
        "Updated 2024\n"
        "\n"
        "Producer,Name,Vintage,Region,Appellation,Varietal,Quantity,Bottle Size\n"
        "Ch. Margaux,Ch. Margaux Grand Vin,2015,Bordeaux,Medoc,Cab-Sauv,2,750ml\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "run"

    artifacts = run_pipeline(str(input_path), str(out_dir), ct_cache=ct_cache)

    parsed = json.loads(Path(artifacts["parsed"]).read_text(encoding="utf-8"))
    with Path(artifacts["raw_copy"]).open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    assert list(rows[0].keys())[0] == "Producer"
    assert rows[0]["Producer"] == "Ch. Margaux"
    assert parsed[0]["source_row_number"] == 5


def test_pipeline_can_include_quarantined_text_lines_in_review(tmp_path: Path, seed_cache) -> None:
    root = Path(__file__).resolve().parents[1]
    canonical_path = root / "data" / "canonical" / "sample_canonical.csv"
    ct_cache = seed_cache(canonical_path)
    input_path = tmp_path / "inventory.txt"
    input_path.write_text(
        "Ridge Lytton Springs 1993 - 2 bottles\n"
        "This is just a note\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "run"

    artifacts = run_pipeline(
        str(input_path),
        str(out_dir),
        ct_cache=ct_cache,
        include_quarantine=True,
    )

    quarantine = json.loads(Path(artifacts["ingestion_quarantine"]).read_text(encoding="utf-8"))
    reviewed = json.loads(Path(artifacts["reviewed"]).read_text(encoding="utf-8"))
    manifest = yaml.safe_load(Path(artifacts["manifest"]).read_text(encoding="utf-8"))

    assert len(quarantine) == 1
    assert len(reviewed) == 2
    assert reviewed[-1]["user_row"]["quarantine_reason"] == "line did not contain enough wine evidence"
    assert manifest["stats"]["rows_quarantined"] == 1
    assert manifest["export_policy"]["include_quarantine"] is True


def test_pipeline_sends_unresolved_rows_to_lookup_urls(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    input_path = root / "data" / "raw" / "sample_input.csv"
    out_dir = tmp_path / "run"
    empty_cache = tmp_path / "empty.db"  # valid but empty cache: nothing resolves

    artifacts = run_pipeline(str(input_path), str(out_dir), ct_cache=str(empty_cache))

    manifest = yaml.safe_load(Path(artifacts["manifest"]).read_text(encoding="utf-8"))
    assert manifest["stats"]["resolved_from_cache"] == 0
    assert manifest["stats"]["unresolved"] == manifest["stats"]["candidate_sets"]
    assert manifest["stats"]["accepted_matches"] == 0
    assert manifest["ct_cache"] == str(empty_cache)

    resolution = json.loads(Path(artifacts["resolution"]).read_text(encoding="utf-8"))
    assert all(record["source"] == "unresolved" for record in resolution)

    with Path(artifacts["lookup_urls"]).open("r", encoding="utf-8", newline="") as handle:
        lookup_rows = list(csv.DictReader(handle))
    assert lookup_rows
    assert "cellartracker.com" in lookup_rows[0]["url"]


def test_pipeline_records_accepted_resolutions_back_to_cache(tmp_path: Path, seed_cache) -> None:
    root = Path(__file__).resolve().parents[1]
    input_path = root / "data" / "raw" / "wine_raw_test1.csv"
    canonical_path = root / "data" / "canonical" / "wine_canonical_clean.csv"
    ct_cache = seed_cache(canonical_path)

    artifacts = run_pipeline(str(input_path), str(tmp_path / "run"), ct_cache=ct_cache)

    reviewed = json.loads(Path(artifacts["reviewed"]).read_text(encoding="utf-8"))
    accepted = [r for r in reviewed if r["status"] == "accepted"]
    assert accepted

    sample = accepted[0]
    with ResolutionCache(ct_cache) as cache:
        assert cache.stats()["resolutions_positive"] > 0
        hit = cache.lookup(
            ResolutionCache.signature(
                sample["user_row"].get("producer"),
                sample["user_row"].get("name"),
                sample["user_row"].get("vintage"),
            )
        )
    assert hit is not None
    assert hit.ct_wine_id == sample["best_match"]["ct_wine_id"]


def test_load_project_env_prefers_current_working_directory(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    loaded = load_project_env()

    assert loaded is True
    assert os.environ["OPENAI_API_KEY"] == "test-key"
