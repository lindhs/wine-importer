"""Golden-run regression test.

Pins the end-to-end behavior of the deterministic pipeline against
data/raw/wine_raw_test1.csv. Any change to parsing, mapping, normalization,
matching, or review thresholds that shifts these counts will fail here first.
If a change is intentional, update the expected values in the same commit and
explain why in the commit message.
"""

import csv
import json
from pathlib import Path

import yaml

from wine_importer.pipeline import run_pipeline

GOLDEN_STATS = {
    "rows_parsed": 31,
    "rows_quarantined": 0,
    "rows_mapped": 31,
    "rows_normalized": 31,
    "candidate_sets": 31,
    "reviewed_matches": 31,
    "accepted_matches": 24,
    "review_needed_matches": 5,
    "rejected_matches": 2,
}
GOLDEN_EXPORT_ROWS = 24  # accepted rows only (default export policy)


def test_golden_run_matches_reference_counts(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    input_path = root / "data" / "raw" / "wine_raw_test1.csv"
    canonical_path = root / "data" / "canonical" / "wine_canonical_clean.csv"
    out_dir = tmp_path / "run"

    artifacts = run_pipeline(str(input_path), str(canonical_path), str(out_dir))

    manifest = yaml.safe_load(Path(artifacts["manifest"]).read_text(encoding="utf-8"))
    assert manifest["stats"] == GOLDEN_STATS

    reviewed = json.loads(Path(artifacts["reviewed"]).read_text(encoding="utf-8"))
    statuses: dict[str, int] = {}
    for item in reviewed:
        statuses[item["status"]] = statuses.get(item["status"], 0) + 1
    assert statuses == {
        "accepted": GOLDEN_STATS["accepted_matches"],
        "review_needed": GOLDEN_STATS["review_needed_matches"],
        "rejected": GOLDEN_STATS["rejected_matches"],
    }

    with Path(artifacts["export"]).open("r", encoding="utf-8", newline="") as handle:
        export_rows = list(csv.DictReader(handle))
    assert len(export_rows) == GOLDEN_EXPORT_ROWS

    with Path(artifacts["report"]).open("r", encoding="utf-8", newline="") as handle:
        report_rows = list(csv.DictReader(handle))
    assert len(report_rows) == GOLDEN_STATS["reviewed_matches"]
