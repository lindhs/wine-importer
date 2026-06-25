"""Live CellarTracker canary — excluded by default (`-m network` to run).

CellarTracker blocks automated clients at the CDN, which is why resolution is
browser-assisted. This canary reflects that reality:

- if a request is blocked (the normal case), it SKIPS — there is nothing to
  scrape, so capture fixtures manually per tests/fixtures/cellartracker/README.md;
- if a wine page ever returns HTML (e.g. a sanctioned API/path opens up), it
  asserts the parser still understands the structure, catching HTML drift.

Run manually: `pytest -m network tests/test_network_canary.py`
"""

import urllib.error
import urllib.request

import pytest

from wine_importer.cellartracker_lookup import parse_wine_definition

KNOWN_WINE_URL = "https://www.cellartracker.com/wine.asp?iWine=18856"


@pytest.mark.network
def test_cellartracker_wine_page_still_parses() -> None:
    request = urllib.request.Request(
        KNOWN_WINE_URL, headers={"User-Agent": "wine-importer-canary/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            html = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        pytest.skip(
            f"CellarTracker blocked automated access (HTTP {error.code}); "
            "capture fixtures manually instead of scraping."
        )
    except urllib.error.URLError as error:
        pytest.skip(f"No network/route to CellarTracker: {error}")

    if status != 200:
        pytest.skip(f"CellarTracker returned HTTP {status}; not a parseable page.")

    definition = parse_wine_definition(html)
    assert definition.ct_wine_id == "18856"
    assert definition.producer
