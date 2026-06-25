# wine-importer

`wine-importer` is a local-first CLI pipeline for importing messy wine inventories into a cleaned, CellarTracker-ready CSV.

## Features

- Inspect CSV/TSV/XLSX/JSON/text inputs and preview extracted wine rows
- Detect wine-like table regions before schema mapping, even when headers are not on row 1
- Infer schema mappings from headers and column-value profiles
- Quarantine uncertain rows, skipped regions, and unsupported documents for review
- Normalize wine metadata with deterministic rules
- Perform canonical wine search and fuzzy scoring using RapidFuzz
- Review matches automatically with review-needed thresholds
- Export a CellarTracker-ready CSV conservatively from accepted matches
- Keep each stage as a reusable, independent pipeline step

## Requirements

- Python 3.11+
- Typer
- Pydantic
- pandas
- PyYAML
- RapidFuzz
- rich
- pytest
- ruff

Optional document helpers:

- `pypdf` for text-based PDFs
- `Pillow` and `pytesseract` for OCR image inputs

## Installation

```bash
python -m pip install -e .
```

## CLI Usage

```bash
wine-importer inspect data/raw/sample_input.csv
wine-importer inspect data/raw/sample_input.tsv --delimiter "\t"
wine-importer inspect data/raw/sample_input.xlsx --sheet-name Sheet1
wine-importer inspect data/raw/workbook.xlsx --all-sheets
wine-importer inspect cellar_photo.png --ocr
wine-importer inspect unstructured_file.foo --use-ai
# Candidates come from the resolution cache (~/.wine-importer/ct_cache.db by
# default). Seed it once from a legacy canonical CSV, or grow it from
# browser-confirmed CellarTracker resolutions (ct-urls -> ct-ingest).
wine-importer cache import-canonical data/canonical/sample_canonical.csv

wine-importer run data/raw/sample_input.csv --out-dir runs/example
wine-importer run data/raw/sample_input.tsv --out-dir runs/example --delimiter "\t"
wine-importer run data/raw/sample_input.xlsx --out-dir runs/example --sheet-name Sheet1
wine-importer run data/raw/workbook.xlsx --out-dir runs/example --all-sheets
wine-importer run data/raw/notes.txt --out-dir runs/example --include-quarantine
wine-importer run cellar_photo.png --out-dir runs/example --ocr
wine-importer run some_unknown_file.foo --out-dir runs/example --use-ai
wine-importer run data/raw/wine_raw_test1.csv --ct-cache /tmp/ct.db --out-dir runs/example

wine-importer normalize runs/example/04_mapped_rows.json --out runs/example/05_normalized_rows.json
wine-importer match runs/example/05_normalized_rows.json --out runs/example/06_candidate_matches.json
wine-importer review runs/example/06_candidate_matches.json --out runs/example/07_reviewed_matches.json
wine-importer export runs/example/07_reviewed_matches.json --out runs/example/08_cellartracker_import.csv
```

## Pipeline Artifacts

- `01_raw_copy.csv`
- `01_structure_report.json`
- `02_parsed_rows.json`
- `02_ingestion_quarantine.json`
- `02_ingestion_quarantine.csv`
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
`--export-review-needed` to include review-needed rows, and
`--export-rejected-as-unmatched` to include rejected rows as unmatched wines.
Use `--include-quarantine` when you want quarantined ingestion rows to appear in
review/report artifacts as rejected rows.

## Sample Data

- `data/raw/sample_input.csv`
- `data/canonical/sample_canonical.csv`

## Project Layout

```
wine-importer/
  pyproject.toml
  README.md
  data/
    raw/
    canonical/
    output/
  runs/
  wine_importer/
    __init__.py
    cli.py
    models.py
    ingest.py
    pipeline.py
    parse.py
    table_detect.py
    schema_map.py
    normalize.py
    search.py
    score.py
    review.py
    export.py
    io.py
  tests/
    test_normalize.py
    test_score.py
    test_pipeline.py
```
