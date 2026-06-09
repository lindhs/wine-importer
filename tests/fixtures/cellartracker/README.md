# CellarTracker HTML fixtures

**These fixtures are currently SYNTHETIC** — hand-written stand-ins modeled on
CellarTracker's page structure. They exercise the parser contract, but the
parser has not yet been validated against real pages. Replace them with real
saved pages and re-run the test suite; adjust `_extract_labeled_fields` /
`_find_wine_id` in `wine_importer/cellartracker_lookup.py` if the structure
differs.

## How to capture real fixtures (one-time, ~10 minutes)

1. Open a **private/incognito browser window and stay logged out** — saved
   pages must not contain your username, session cookies, or `CK=` tokens.
2. Visit cellartracker.com and run a search with many hits (e.g. "1993 ridge
   lytton springs"). Save the results page via File > Save Page As >
   **"Webpage, HTML Only"** as `search_results_many.html` in this directory.
3. Run a search with zero hits (e.g. gibberish). Save as
   `search_results_empty.html`.
4. Open one fully-populated vintage wine page (producer, varietal,
   designation, vineyard, country, region, subregion, appellation all
   present). Save as `wine_full.html`.
5. Open one sparse page — an NV sparkling wine with few fields. Save as
   `wine_sparse.html`.
6. Before committing, confirm no personal data:
   `grep -il 'CK=\|password\|logout' tests/fixtures/cellartracker/*.html`
   should print nothing.
7. Run `pytest tests/test_cellartracker_lookup.py -q` and fix any parser
   mismatches — then update the test expectations to the real wines and
   delete the SYNTHETIC notice above.
