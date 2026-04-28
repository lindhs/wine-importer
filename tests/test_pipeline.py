import json
import os
from pathlib import Path

import yaml

from wine_importer.ai_runtime import load_project_env
from wine_importer.pipeline import run_pipeline


def test_pipeline_creates_artifacts(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    input_path = root / "data" / "raw" / "sample_input.csv"
    canonical_path = root / "data" / "canonical" / "sample_canonical.csv"
    out_dir = tmp_path / "run"

    artifacts = run_pipeline(str(input_path), str(canonical_path), str(out_dir))

    assert Path(artifacts["raw_copy"]).exists()
    assert Path(artifacts["parsed"]).exists()
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
    assert isinstance(reviewed, list)
    assert len(reviewed) >= 1
    assert "producer" in reviewed[0]["user_row"]
    assert "top_1_score" in candidates[0]
    assert "score_margin" in candidates[0]
    assert "blocking_reason" in candidates[0]["candidates"][0]
    assert manifest["policy"]["accept_threshold"] == 0.70
    assert manifest["policy"]["review_threshold"] == 0.55
    assert manifest["export_policy"]["export_review_needed"] is False


def test_pipeline_writes_ai_input_quality_artifact(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    input_path = root / "data" / "raw" / "sample_input.csv"
    canonical_path = root / "data" / "canonical" / "sample_canonical.csv"
    out_dir = tmp_path / "run"

    def fake_assessment(sample_data):
        return {"completeness": 8, "rows_sampled": len(sample_data)}

    monkeypatch.setattr(
        "wine_importer.ai_schema.assess_input_quality_with_ai",
        fake_assessment,
    )

    artifacts = run_pipeline(
        str(input_path),
        str(canonical_path),
        str(out_dir),
        use_ai=True,
    )

    quality = json.loads(Path(artifacts["input_quality"]).read_text(encoding="utf-8"))
    manifest = yaml.safe_load(Path(artifacts["manifest"]).read_text(encoding="utf-8"))

    assert quality["completeness"] == 8
    assert quality["rows_sampled"] > 0
    assert manifest["artifacts"]["input_quality"] == artifacts["input_quality"]
    assert manifest["policy"]["review_min_score"] == 0.55
    assert manifest["policy"]["review_threshold"] == 0.55


def test_load_project_env_prefers_current_working_directory(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    loaded = load_project_env()

    assert loaded is True
    assert os.environ["OPENAI_API_KEY"] == "test-key"
