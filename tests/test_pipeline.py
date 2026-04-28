import json
from pathlib import Path

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

    reviewed = json.loads(Path(artifacts["reviewed"]).read_text(encoding="utf-8"))
    assert isinstance(reviewed, list)
    assert len(reviewed) >= 1
    assert "producer" in reviewed[0]["user_row"]
