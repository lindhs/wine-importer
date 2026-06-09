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

## Phase 3 — CellarTracker lookup adapter

This is the centerpiece. A new module, `wine_importer/cellartracker_lookup.py`, that resolves a normalized wine row to candidate `iWine` IDs by text search and Wine Definition scraping. It is deliberately isolated: nothing else in the codebase knows about HTML, and all CellarTracker fragility lives behind one interface.

### Module design

```python
@dataclass(frozen=True)
class CTWineDefinition:
    ct_wine_id: str
    display_name: str
    vintage: str | None
    type: str | None
    producer: str | None
    varietal: str | None
    designation: str | None
    vineyard: str | None
    country: str | None
    region: str | None
    subregion: str | None
    appellation: str | None
    url: str

def build_search_query(row: NormalizedWineRow) -> str: ...
def fetch_search_results(query: str, session: requests.Session) -> str: ...
def extract_iwine_ids(search_html: str) -> list[str]: ...
def fetch_wine_definition(iwine_id: str, session: requests.Session) -> CTWineDefinition: ...
def lookup_candidates(row: NormalizedWineRow, *, max_candidates: int = 10,
                      cache: ResolutionCache | None = None) -> list[CTWineDefinition]: ...
def to_canonical_wine(defn: CTWineDefinition) -> CanonicalWine: ...
```

`build_search_query` concatenates `{vintage} {producer} {name} {varietal} {appellation}`, skipping empty fields, using the normalized values. `extract_iwine_ids` parses `wine.asp?iWine=(\d+)` links from search-result HTML. `fetch_wine_definition` parses the wine-page detail block into the dataclass — this is the single function that knows CellarTracker's page structure, so when their HTML changes, one function and its fixtures change. `to_canonical_wine` converts a definition into a `CanonicalWine` with `id="ct:{iWine}"` and `source="cellartracker_html"`, which means the existing scorer works on CT candidates with zero modification.

### Operational discipline

The adapter must be a polite client. Use a shared `requests.Session` with a descriptive User-Agent, a configurable delay between requests (default ~1–2 seconds), retry with exponential backoff on transient errors, and a hard cap on definitions fetched per row (default 10). Every network failure degrades gracefully: log, return what was gathered, never crash the pipeline. Authentication tokens (the `CK=` session key seen in RSS URLs) must never be committed, logged, or required — the public search path works without them. Before relying on scraping at volume, review CellarTracker's terms of service; the design should keep the door open to swapping the scraper for an official API or export-based ingestion if one becomes available, which is another reason all CT knowledge sits behind this one module.

### Testing

No live network calls in tests. Save real search-result and wine-page HTML as fixtures under `tests/fixtures/cellartracker/`, and test `extract_iwine_ids` and `fetch_wine_definition` against them. Use `responses` or monkeypatched sessions for the orchestration tests.

**Deliverables:** the module, fixture-based tests, a `wine-importer ct-lookup "<query>"` debug CLI command that prints candidates for a free-text query.

---

## Phase 4 — Resolution cache

Repeated runs must not re-scrape wines already resolved. Add `wine_importer/resolution_cache.py` backed by SQLite (preferred over JSON: concurrent-safe, queryable, scales past a few thousand wines):

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

The signature is built from normalized fields so that "Ch. Talbot / 1989" and "Château Talbot / 1989" hash identically after normalization. Negative results are cached too (with a shorter TTL) so unmatched wines don't trigger a search on every run. The cache file lives at a configurable path (default `~/.wine-importer/ct_cache.db`), is git-ignored, and a `wine-importer cache stats|clear` subcommand exposes it.

**Added from review:** while restructuring candidate sourcing, fix the in-memory search-index cache in `search.py` — `_SEARCH_CACHE` is keyed on `id(canonical_wines)` (`search.py:334`), which can silently serve stale data when a garbage-collected object's id is reused. Replace the key with a content hash of the canonical records.

Over time this cache *becomes* a growing local canonical mirror — the original local-CSV concept, but populated automatically from confirmed resolutions instead of curated by hand.

**Deliverables:** cache module with TTL handling and negative caching, cache CLI subcommands, integration into `lookup_candidates`, content-hash fix for `_SEARCH_CACHE`.

---

## Phase 5 — Scorer enrichment

The scorer currently weighs producer, name, appellation, vintage, varietal, and region. The lookup layer brings richer identity fields, and the scorer should use them.

Extend `rank_candidates` / the field-weight table in `score.py` to also compare `vineyard`, `designation`, and `subregion` when both sides have them, with conflict penalties mirroring the existing vintage/country logic (a vineyard mismatch between two otherwise-identical Barolos is exactly the tiebreaker case). Extend `score_candidate_with_ai()` in `ai_schema.py` to pass appellation, varietal, vineyard, designation, and country into the prompt — the borderline cases AI arbitrates are precisely the ones these fields decide.

Introduce a second threshold profile. Import matching keeps the current `accept=0.70 / review=0.55`. Existence lookup ("does this exact wine already exist in CT?") is a stricter question and gets `accept=0.85 / review=0.65`. Put both in `config.py` as named `ScoringPolicy` instances and record the active policy in the run manifest (which already tracks thresholds via `scoring_policy_manifest()`).

**Deliverables:** enriched deterministic scorer with tests for the new conflict penalties, enriched AI prompt, dual threshold policies in config and manifest.

---

## Phase 6 — Pipeline integration

Wire the lookup into the staged pipeline as a proper stage rather than a side path, preserving the artifact-per-stage paradigm.

The new flow inserts a resolution stage between normalization and scoring:

```
05_normalized_rows.json
        ↓
Stage 6a: canonical resolution
   per row: cache hit? → use cached candidates
            else local canonical candidates (existing token-index search)
            else (--use-ct-lookup) CellarTracker search → definitions → cache
        ↓
06a_resolution.json        (per-row: source used, query sent, ids found, cache hits)
        ↓
Stage 6b: score candidates  (existing rank_candidates, unchanged interface)
        ↓
06_candidate_matches.json   (candidates now carry ct_wine_id when resolved via CT)
```

CLI surface: `--use-ct-lookup` enables the network path, `--ct-cache PATH` overrides the cache location, `--canonical` becomes optional when `--use-ct-lookup` is set (local CSV degrades from required reference to optional seed). The deterministic offline pipeline remains the default — no flag, no network, byte-identical behavior to today, which the Phase 0 golden test enforces.

`06a_resolution.json` is the new audit artifact: for every row it records which source resolved it (cache / local / cellartracker / none), the search query issued, candidate ids returned, and timing. The run manifest gains resolution counts (cache hits, live lookups, not-found).

**Deliverables:** resolution stage, new artifact, CLI flags, manifest extensions, updated mermaid flowchart in WORKFLOW.md, integration tests with mocked lookup.

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
| 3 — CT lookup adapter | 1 | **high** (external HTML) | 2 days |
| 4 — Resolution cache | 3 | low | 1 day |
| 5 — Scorer enrichment | 1 | medium | 1 day |
| 6 — Pipeline integration | 3, 4, 5 | medium | 1–2 days |
| 7 — Export/report | 6 | low | half a day |
| 8 — Hardening | all | low | 1 day |

Phases 2 and 5 are independent of the CT track and can be done in parallel with 3–4. Every phase ends with `pytest -q` green and the golden-run regression intact.
