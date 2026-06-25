# wine-importer Rebuild Plan

## Goal

Evolve wine-importer from a self-referential canonicalization pipeline (matching against a local hand-curated CSV) into a reference-data-backed entity resolution system, where the authoritative canonical layer is CellarTracker's wine database, discovered via text search and identified by stable `iWine` IDs. The deterministic pipeline, human-in-the-loop review, and staged-artifact design all stay — they are the project's strengths. What changes is where canonical truth comes from and how richly candidates are scored.

The rebuild is organized into eight phases. Each phase is independently shippable, keeps the test suite green, and leaves the pipeline runnable end to end. Phases are ordered so that the riskiest external dependency (CellarTracker scraping) lands only after the internal foundations are solid.

> **Status note (2026-06-09):** baseline verified against the current codebase — 46 tests passing. Table detection (Phase 2) already exists in `table_detect.py` and is wired into ingestion; that phase is an audit/extend pass, not a build. See per-phase notes.

---

## Phase 0 — Baseline and guardrails

Before changing anything, lock in current behavior so regressions are visible.

Run the full pipeline against `data/raw/wine_raw_test1.csv` and store the expected row counts and accepted/review/rejected splits in a test. Add an end-to-end regression test that executes `run_pipeline()` on the sample input and asserts the manifest counts match the golden run. The existing `test_pipeline_creates_artifacts` asserts artifacts *exist*; the golden test goes further and pins the *numbers*. This becomes the safety net for every later phase.

Add the two new dependencies the rebuild will need as an optional extra in `pyproject.toml` so the core pipeline stays installable without network features:

```toml
[project.optional-dependencies]
cellartracker = ["requests>=2.31", "beautifulsoup4>=4.12"]
```

There is currently no CI. Create `.github/workflows/ci.yml` running `pytest -q` on push and pull request against Python 3.11/3.12 (the remote is `github.com/lindhs/wine-importer`).

**Deliverables:** golden-run regression test, `cellartracker` optional extra, GitHub Actions workflow.

---

## Phase 1 — Data model consolidation

This phase fixes internal schema debt before any new features build on top of it.

### 1a. Single `size` field

`MappedWineRow` carries both `size` and `bottle_size`, and the `FIELD_KEYWORDS` table in `schema_map.py` lists overlapping keyword sets for both (the `bottle_size` entry even contains the literal keyword `"size"`), which means two runs over similar files can land the same data in different slots. Consolidate to `size` as the only internal field. The migration touches:

- `models.py` — remove `bottle_size` and `normalized_bottle_size`
- `schema_map.py` — delete the `bottle_size` keyword entry (its aliases are already covered by `size`), drop the `bottle_size=` kwarg in `apply_schema_mapping`
- `ai_schema.py` — remove `bottle_size` from `WINE_FIELDS`
- `ingest.py` — `CORE_FIELDS` and the field-evidence logic fold `bottle_size` into `size`
- `normalize.py` — drop the dual normalization
- `export.py` — the `_first_non_empty` chain simplifies, still emitting the `BottleSize` column on export
- `report.py` — keep `bottle_size`-style aliases only where they refer to *original input column names*, not internal fields

Update affected tests.

### 1b. Extend the canonical model toward CellarTracker's Wine Definition

`CanonicalWine` grows to mirror the fields CellarTracker exposes on every wine page, because those are the fields the new lookup layer will scrape and the scorer will compare:

```python
class CanonicalWine(BaseModel):
    id: str                          # local id OR "ct:{iWine}"
    ct_wine_id: str | None = None    # CellarTracker iWine when known
    producer: str
    name: str
    vintage: str
    type: str | None = None          # Red / White / Rosé / Sparkling...
    designation: str | None = None
    vineyard: str | None = None
    country: str | None = None
    region: str = ""                 # loosened: CT pages may lack these
    subregion: str | None = None
    appellation: str = ""
    varietal: str = ""
    quantity: int | None = None
    size: str | None = None
    notes: str | None = None
    source: str = "local_csv"        # local_csv | cellartracker_html | cache
```

**Correction from review:** `region`, `appellation`, and `varietal` are currently required `str`. CellarTracker scrapes will not always have them, so they get `""` defaults in the same migration (empty strings score 0 in the existing fuzzy comparisons, so scorer behavior is unchanged for populated data).

All new fields are optional with defaults, so existing canonical CSVs keep loading unchanged. `CandidateMatch` gains `ct_wine_id: str | None = None` so the discovered identity flows through matching, review, and export.

**Deliverables:** consolidated `size`, extended `CanonicalWine` and `CandidateMatch`, all existing tests passing, new model tests for round-tripping the optional fields.

---

## Phase 2 — Table detection audit (revised: this already exists)

**Correction from review:** the original plan assumed the parser treats row 1 as the header. It doesn't — `table_detect.py` already implements `detect_table_regions()` with header-confidence scoring (recognized-field ratio, distinctness, numeric density; threshold 0.45), it is wired into ingestion (`ingest.py` → `_ingest_raw_matrix`), preamble rows are handled, and `test_pipeline_extracts_table_after_preamble` passes. The detected regions and confidence scores are already recorded in `01_structure_report.json`, so no new `02_table_region.json` artifact is needed.

The remaining work is hardening, not building:

- Add unit-test fixtures for the cases the heuristic hasn't been proven against: blank rows inside the data region, multiple tables in one sheet, merged-cell artifacts from Excel exports, files with *no* recognizable header at all (must fall back to line-parsing without corrupting data).
- Audit `_header_confidence()` against those fixtures and tune only if a fixture fails.
- When `--use-ai` is enabled and no region clears the confidence floor, the existing AI parser path is the fallback — AI stays a fallback, never the first step. Verify this path has a test.

**Deliverables:** edge-case fixtures and unit tests for `detect_table_regions`, fixes only where fixtures expose bugs, WORKFLOW.md note on detection behavior.

---

## Phase 3 — Browser-assisted CellarTracker resolution (revised 2026-06-10)

**Correction from verification:** the original plan specced polite `requests`-based scraping. CellarTracker blocks non-browser clients at the CloudFront edge — even `robots.txt` returns 403 to plain curl. Getting through would mean impersonating a browser to defeat an intentional technical barrier; that path is rejected. The sanctioned routes are: the user's own browser, the documented `xlquery.asp` own-data export, and a partner API granted on request (see `docs/cellartracker_api_request.md`).

The revised transport: **the tool builds search URLs, the user's real browser does all fetching**, the user saves wine pages locally, and the tool parses the saved files. Zero automated requests to CellarTracker, no credentials, no ToS exposure. All page-structure knowledge still lives in one module (`wine_importer/cellartracker_lookup.py`), so a sanctioned API client can replace the browser step later without touching the parsers.

### Module design

```python
@dataclass(frozen=True)
class CTWineDefinition: ...           # ct_wine_id, display_name, vintage, type,
                                      # producer, varietal, designation, vineyard,
                                      # country, region, subregion, appellation, url

def build_search_query(row: NormalizedWineRow) -> str: ...
def build_search_url(query: str) -> str: ...
def extract_iwine_ids(search_html: str) -> list[str]: ...
def parse_wine_definition(wine_html: str) -> CTWineDefinition: ...   # raises CTParseError
def to_canonical_wine(defn: CTWineDefinition) -> CanonicalWine: ...
def load_resolution_store(path) / append_resolutions(defs, path): ...  # JSON store,
                                      # formalized into the SQLite cache in Phase 4
```

No HTTP code anywhere in the module. `to_canonical_wine` produces `id="ct:{iWine}"`, `source="cellartracker_html"`, so the existing scorer works on CT candidates unchanged.

### Workflow (CLI)

- `wine-importer ct-urls <run_dir>` — reads `05_normalized_rows.json` (skipping rows already accepted in `07_reviewed_matches.json`), writes `06a_lookup_urls.csv`; `--open N` opens N browser tabs per batch with a confirm prompt between batches.
- The user saves wine pages ("HTML Only") into `<run_dir>/ct_inbox/`.
- `wine-importer ct-ingest <run_dir>` — parses the inbox, writes `06a_resolutions.json` (parsed definitions and per-file parse errors), appends confirmed identities to the persistent store at `~/.wine-importer/resolutions.json`.
- `wine-importer ct-lookup "<text or saved file>"` — debug helper.
- `wine-importer ct-build-canonical --out <csv>` — interim bridge: materializes the resolution store into a canonical CSV that today's `--canonical` flag consumes. `load_canonical_wines` was taught to read the `ct_wine_id` column back (id `ct:{iWine}`, `source=cellartracker_html`), so the identity flows through matching to export. This turns the loop into a flywheel before Phase 6; Phase 6 reads the store natively and makes this command redundant.

### Testing

No live network calls in tests, ever. Fixtures live under `tests/fixtures/cellartracker/`; they start synthetic and are replaced with real saved pages per the checklist in that directory's README (captured logged-out, scrubbed of any session data before commit).

**Deliverables (shipped):** the module, fixture-based parser tests, the three CLI commands with tests, the API request email draft.

---

## Phase 4 — Resolution cache

Repeated runs must not re-resolve wines already confirmed. Phase 3's JSON store (`~/.wine-importer/resolutions.json`) migrates into `wine_importer/resolution_cache.py` backed by SQLite (concurrent-safe, queryable, scales past a few thousand wines). **Per the 2026-06-10 decision there is no local canonical list** — this cache *is* the canonical layer, populated exclusively from browser-confirmed resolutions:

```sql
CREATE TABLE resolutions (
    signature   TEXT PRIMARY KEY,   -- normalized "producer|name|vintage"
    ct_wine_id  TEXT,               -- NULL means "searched, not found"
    definition  TEXT,               -- JSON of CTWineDefinition
    score       REAL,
    resolved_at TEXT,
    ttl_days    INTEGER DEFAULT 180
);
CREATE TABLE wine_definitions (
    ct_wine_id  TEXT PRIMARY KEY,
    definition  TEXT,
    fetched_at  TEXT
);
```

The signature is built from normalized fields so that "Ch. Talbot / 1989" and "Château Talbot / 1989" hash identically after normalization. Negative results ("searched in browser, confirmed not on CT") are cached too so unmatched wines don't reappear in every `ct-urls` batch. The cache file lives at a configurable path (default `~/.wine-importer/ct_cache.db`), is git-ignored, and a `wine-importer cache stats|clear` subcommand exposes it.

**Added from review:** while restructuring candidate sourcing, fix the in-memory search-index cache in `search.py` — `_SEARCH_CACHE` is keyed on `id(canonical_wines)` (`search.py:334`), which can silently serve stale data when a garbage-collected object's id is reused. Replace the key with a content hash of the canonical records.

**Deliverables (shipped):** `resolution_cache.py` with `ResolutionCache` (SQLite, `wine_definitions` + `resolutions` tables), positive/negative TTLs, `signature`/`signature_for_row` helpers, `all_canonical()`, `import_json_store()` migration of the Phase 3 JSON store; `ct-ingest`/`ct-build-canonical` repointed at `--cache`; `cache stats|clear|import-json` CLI; `_SEARCH_CACHE` rekeyed from `id()` to a content hash (with a size cap). The signature→iWine `resolutions` table is populated by Phase 6's resolution stage; `record_resolution`/`record_miss`/`lookup` are ready for it.

---

## Phase 5 — Scorer enrichment

The scorer currently weighs producer, name, appellation, vintage, varietal, and region. The lookup layer brings richer identity fields, and the scorer should use them.

Extend `rank_candidates` / the field-weight table in `score.py` to also compare `vineyard`, `designation`, and `subregion` when both sides have them, with conflict penalties mirroring the existing vintage/country logic (a vineyard mismatch between two otherwise-identical Barolos is exactly the tiebreaker case). Extend `score_candidate_with_ai()` in `ai_schema.py` to pass appellation, varietal, vineyard, designation, and country into the prompt — the borderline cases AI arbitrates are precisely the ones these fields decide.

Introduce a second threshold profile. Import matching keeps the current `accept=0.70 / review=0.55`. Existence lookup ("does this exact wine already exist in CT?") is a stricter question and gets `accept=0.85 / review=0.65`. Put both in `config.py` as named `ScoringPolicy` instances and record the active policy in the run manifest (which already tracks thresholds via `scoring_policy_manifest()`).

**Deliverables (shipped):** deterministic scorer gains `vineyard` and `subregion` tiebreakers (bonus on match, penalty + hard-conflict on mismatch) gated on both-sides-present, so local-CSV scoring and the golden run are byte-identical; `score_candidate_with_ai` now passes appellation/varietal/vineyard/country (and canonical designation) into the prompt; `config.py` adds the named `EXISTENCE_LOOKUP_POLICY` (0.85/0.65) alongside `import` (0.70/0.55), `classify_review_score`/`is_ai_scoring_candidate`/`scoring_policy_manifest` are policy-parameterized, and the manifest records `policy_name`. (Designation has no input-row field, so it's AI-prompt-only deterministically — `name_score` already captures it.)

---

## Phase 6 — Pipeline integration

Wire the lookup into the staged pipeline as a proper stage rather than a side path, preserving the artifact-per-stage paradigm.

The new flow inserts a resolution stage between normalization and scoring. **Per the 2026-06-10 decision the local canonical CSV is removed entirely** — the resolution cache is the only candidate source, and the existing token-index search (`wine_importer/search.py`) is repointed at cache contents:

```
05_normalized_rows.json
        ↓
Stage 6a: canonical resolution
   per row: cache hit (signature or token-index fuzzy match over cached
            CanonicalWines)? → use cached candidates
            else → row lands in 06a_lookup_urls.csv for the
            browser-assisted ct-urls / ct-ingest loop
        ↓
06a_resolution.json        (per-row: cache / browser-confirmed / unresolved,
                            query, candidate ids)
        ↓
Stage 6b: score candidates  (existing rank_candidates, unchanged interface)
        ↓
06_candidate_matches.json   (candidates carry ct_wine_id)
```

CLI surface: `--canonical` is deleted; `--ct-cache PATH` overrides the cache location. The pipeline stays fully offline — unresolved rows flow to review as `rejected`/`review_needed` with a pointer to the lookup CSV, and a re-run after `ct-ingest` picks up the newly cached identities. The Phase 0 golden test is updated in the same commit (the reference run changes when `--canonical` goes away, and the new counts are pinned with the rationale in the commit message).

`06a_resolution.json` is the audit artifact: for every row it records which source resolved it (cache / browser-confirmed / none) and the search query. The run manifest gains resolution counts (cache hits, newly ingested, unresolved).

**Deliverables:** resolution stage, new artifact, `--canonical` removal with golden-test update, manifest extensions, updated mermaid flowchart in WORKFLOW.md, integration tests with a pre-seeded cache.

---

## Phase 7 — Export and report upgrade

The export's job changes subtly: accepted rows resolved via CellarTracker now carry an authoritative identity. Emit `ct_wine_id={id}` and the wine URL into the `Notes` provenance block alongside the existing `match_status=` marker (CellarTracker's import format has no dedicated ID column, so notes-based provenance is the right channel). Populate `UserWine1–8` from the scraped Wine Definition fields per the established mapping: producer, varietal, designation, vineyard, country, region, subregion, appellation.

`09_match_report.csv` gains three columns: `ct_wine_id`, `ct_url`, and `resolution_source`. A reviewer can now click straight to the CellarTracker page to verify a borderline match — this is the single biggest quality-of-life improvement for the human-in-the-loop step.

**Deliverables:** export changes with tests, report columns, README/WORKFLOW updates.

---

## Phase 8 — Hardening and documentation

Close the loop on operational quality. Add a recorded-fixture end-to-end test: a small input file, mocked CT responses, full pipeline run, assertions on every artifact including the cache state. Add scraper canary tests marked `@pytest.mark.network` (excluded by default, runnable manually) that hit one known wine page and fail loudly if CellarTracker's HTML structure has drifted. Document the new architecture in WORKFLOW.md: updated flowchart, the resolution stage, cache behavior, threshold policies, and a troubleshooting section for lookup failures.

Finally, update the project's self-description: this is no longer "a CSV cleaner" — it's a local-first master-data resolution system for wine inventories, with CellarTracker as the reference layer, a growing local cache as the mirror, probabilistic entity resolution in the middle, and a human arbitrating uncertainty at the end.

---

## Execution order and effort estimate

| Phase | Depends on | Risk | Rough effort |
|-------|-----------|------|--------------|
| 0 — Baseline | — | low | half a day |
| 1 — Models | 0 | low | half a day |
| 2 — Table detection audit | 0 | low (exists; audit only) | half a day |
| 3 — CT resolution (browser-assisted) | 1 | medium (HTML drift; no network/ToS risk) | 1–2 days |
| 4 — Resolution cache | 3 | low | 1 day |
| 5 — Scorer enrichment | 1 | medium | 1 day |
| 6 — Pipeline integration | 3, 4, 5 | medium | 1–2 days |
| 7 — Export/report | 6 | low | half a day |
| 8 — Hardening | all | low | 1 day |

Phases 2 and 5 are independent of the CT track and can be done in parallel with 3–4. Every phase ends with `pytest -q` green and the golden-run regression intact.
