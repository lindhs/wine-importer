# wine-importer

Local CLI pipeline for turning messy wine spreadsheets into a cleaned,
CellarTracker-ready CSV.

## Install

```bash
python -m pip install -e .
```

## Run

```bash
wine-importer run data/raw/wine_raw_test1.csv \
  --canonical data/canonical/wine_canonical_clean.csv \
  --out-dir runs/example
```

Optional AI helpers use `OPENAI_API_KEY` from `.env` or the shell:

```bash
wine-importer run data/raw/wine_raw_test1.csv \
  --canonical data/canonical/wine_canonical_clean.csv \
  --out-dir runs/example \
  --use-ai
```

## Useful Commands

```bash
wine-importer inspect data/raw/sample_input.csv
wine-importer report runs/example/07_reviewed_matches.json --out runs/example/09_match_report.csv
wine-importer export runs/example/07_reviewed_matches.json --out runs/example/08_cellartracker_import.csv
wine-importer export runs/example/07_reviewed_matches.json --out runs/example/08_cellartracker_import.csv --export-review-needed
python3 setup_api_key.py
python3 -m pytest -q
```

See [WORKFLOW.md](WORKFLOW.md) for the full stage-by-stage workflow and
flowchart.

## Outputs

Pipeline runs write staged artifacts into `runs/<name>/`:

- `01_raw_copy.csv`
- `02_parsed_rows.json`
- `02_input_quality.json` when `--use-ai` is enabled
- `03_mapping.yaml`
- `04_mapped_rows.json`
- `05_normalized_rows.json`
- `06_candidate_matches.json`
- `07_reviewed_matches.json`
- `08_cellartracker_import.csv`
- `09_match_report.csv`
- `run_manifest.yaml`

By default, `08_cellartracker_import.csv` exports only accepted matches. Use
`--export-review-needed` to include review-needed rows with their current best
canonical candidate, or `--export-rejected-as-unmatched` to include rejected
rows as user-entered unmatched wines.

## Project Layout

```text
wine_importer/       source modules
tests/               regression tests
data/raw/            sample input files
data/canonical/      sample canonical files
runs/                generated pipeline output, ignored by git
```
