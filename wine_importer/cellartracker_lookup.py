"""Browser-assisted CellarTracker resolution.

CellarTracker blocks automated clients at the CDN edge, so this module
contains no HTTP code at all. The transport is the user's own browser:
the tool builds search URLs, the user opens them and saves wine pages
locally, and the functions here parse those saved files. All knowledge
of CellarTracker's page structure lives in this one module so that a
sanctioned API client can replace the browser step without touching
anything else.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from .models import CanonicalWine, NormalizedWineRow

SEARCH_URL_TEMPLATE = "https://www.cellartracker.com/list.asp?Table=List&szSearch={query}"
WINE_URL_TEMPLATE = "https://www.cellartracker.com/wine.asp?iWine={iwine}"
DEFAULT_RESOLUTION_STORE = Path.home() / ".wine-importer" / "resolutions.json"

_IWINE_PATTERN = re.compile(r"(?:iWine=|/wines/)(\d+)")

# Field labels CellarTracker shows on wine pages, lowercased without colons.
_LABEL_FIELDS = {
    "producer": "producer",
    "vintage": "vintage",
    "type": "type",
    "variety": "varietal",
    "varietal": "varietal",
    "designation": "designation",
    "vineyard": "vineyard",
    "country": "country",
    "region": "region",
    "subregion": "subregion",
    "sub region": "subregion",
    "appellation": "appellation",
}


class CTParseError(ValueError):
    """Raised when a saved CellarTracker page cannot be parsed."""


@dataclass(frozen=True)
class CTWineDefinition:
    ct_wine_id: str
    display_name: str
    vintage: str | None = None
    type: str | None = None
    producer: str | None = None
    varietal: str | None = None
    designation: str | None = None
    vineyard: str | None = None
    country: str | None = None
    region: str | None = None
    subregion: str | None = None
    appellation: str | None = None
    url: str = ""


def build_search_query(row: NormalizedWineRow) -> str:
    parts = [
        row.normalized_vintage or row.vintage,
        row.normalized_producer or row.producer,
        row.normalized_name or row.name,
        row.normalized_varietal or row.varietal,
        row.normalized_appellation or row.appellation,
    ]
    return " ".join(part.strip() for part in parts if part and part.strip())


def build_search_url(query: str) -> str:
    return SEARCH_URL_TEMPLATE.format(query=quote_plus(query))


def extract_iwine_ids(search_html: str) -> list[str]:
    ids: list[str] = []
    for match in _IWINE_PATTERN.finditer(search_html):
        if match.group(1) not in ids:
            ids.append(match.group(1))
    return ids


def parse_wine_definition(wine_html: str) -> CTWineDefinition:
    soup = _soup(wine_html)
    ct_wine_id = _find_wine_id(soup, wine_html)
    if not ct_wine_id:
        if len(extract_iwine_ids(wine_html)) > 1:
            raise CTParseError(
                "page references multiple wines — this looks like a search "
                "results page; save an individual wine page instead"
            )
        raise CTParseError("no CellarTracker wine id found in page")

    display_name = _find_display_name(soup)
    if not display_name:
        raise CTParseError("no wine title found in page")

    fields = _extract_labeled_fields(soup)
    vintage = fields.pop("vintage", None) or _vintage_from_display_name(display_name)
    return CTWineDefinition(
        ct_wine_id=ct_wine_id,
        display_name=display_name,
        vintage=vintage,
        url=WINE_URL_TEMPLATE.format(iwine=ct_wine_id),
        **fields,
    )


def parse_saved_page(path: str | Path) -> CTWineDefinition:
    return parse_wine_definition(
        Path(path).read_text(encoding="utf-8", errors="replace")
    )


def to_canonical_wine(definition: CTWineDefinition) -> CanonicalWine:
    return CanonicalWine(
        id=f"ct:{definition.ct_wine_id}",
        ct_wine_id=definition.ct_wine_id,
        producer=definition.producer or "",
        name=_wine_name_from_display(definition),
        vintage=definition.vintage or "",
        type=definition.type,
        designation=definition.designation,
        vineyard=definition.vineyard,
        country=definition.country,
        region=definition.region or "",
        subregion=definition.subregion,
        appellation=definition.appellation or "",
        varietal=definition.varietal or "",
        source="cellartracker_html",
    )


# Columns written by build-canonical; load_canonical_wines reads ct_wine_id back
# so the CellarTracker identity survives the round-trip into matching.
CANONICAL_CSV_COLUMNS = [
    "ct_wine_id",
    "producer",
    "name",
    "vintage",
    "country",
    "region",
    "appellation",
    "varietal",
    "size",
    "notes",
]


def resolution_store_to_canonical(store: dict[str, dict]) -> list[CanonicalWine]:
    wines: list[CanonicalWine] = []
    for entry in store.values():
        definition_data = entry.get("definition")
        if not isinstance(definition_data, dict):
            continue
        try:
            definition = CTWineDefinition(**definition_data)
        except TypeError:
            continue
        wines.append(to_canonical_wine(definition))
    return wines


def canonical_to_csv_row(wine: CanonicalWine) -> dict[str, str]:
    return {
        "ct_wine_id": wine.ct_wine_id or "",
        "producer": wine.producer,
        "name": wine.name,
        "vintage": wine.vintage,
        "country": wine.country or "",
        "region": wine.region,
        "appellation": wine.appellation,
        "varietal": wine.varietal,
        "size": wine.size or "",
        "notes": wine.notes or "",
    }


def load_resolution_store(path: str | Path = DEFAULT_RESOLUTION_STORE) -> dict[str, dict]:
    store_path = Path(path)
    if not store_path.exists():
        return {}
    return json.loads(store_path.read_text(encoding="utf-8"))


def append_resolutions(
    definitions: list[CTWineDefinition],
    path: str | Path = DEFAULT_RESOLUTION_STORE,
) -> int:
    store_path = Path(path)
    store = load_resolution_store(store_path)
    added = 0
    for definition in definitions:
        if definition.ct_wine_id not in store:
            added += 1
        store[definition.ct_wine_id] = {
            "definition": asdict(definition),
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return added


def _soup(html: str):
    try:
        from bs4 import BeautifulSoup
    except ImportError as error:
        raise CTParseError(
            "beautifulsoup4 is required to parse CellarTracker pages; "
            "install it with: pip install -e '.[cellartracker]'"
        ) from error
    return BeautifulSoup(html, "html.parser")


def _find_wine_id(soup, html: str) -> str | None:
    og_url = soup.find("meta", property="og:url")
    if og_url and og_url.get("content"):
        match = _IWINE_PATTERN.search(og_url["content"])
        if match:
            return match.group(1)
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        match = _IWINE_PATTERN.search(canonical["href"])
        if match:
            return match.group(1)
    ids = extract_iwine_ids(html)
    if len(ids) == 1:
        return ids[0]
    return None


def _find_display_name(soup) -> str | None:
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content", "").strip():
        return og_title["content"].strip()
    if soup.title and soup.title.get_text(strip=True):
        title = soup.title.get_text(strip=True)
        return re.sub(r"\s*[-|–]\s*CellarTracker.*$", "", title).strip() or None
    return None


def _extract_labeled_fields(soup) -> dict[str, str]:
    fields: dict[str, str] = {}
    for element in soup.find_all(["span", "td", "th", "dt", "strong", "b", "label"]):
        label = element.get_text(strip=True).rstrip(":").lower()
        field = _LABEL_FIELDS.get(label)
        if not field or field in fields:
            continue
        value = _value_for_label_element(element)
        if value:
            fields[field] = value
    return fields


def _value_for_label_element(element) -> str | None:
    sibling = element.find_next_sibling()
    if sibling is not None:
        text = sibling.get_text(strip=True)
        if text:
            return text
    parent = element.parent
    if parent is not None:
        label_text = element.get_text(strip=True)
        remainder = (
            parent.get_text(" ", strip=True)
            .replace(label_text, "", 1)
            .strip()
            .lstrip(":")
            .strip()
        )
        if remainder:
            return remainder
    return None


def _vintage_from_display_name(display_name: str) -> str | None:
    match = re.match(r"^((?:18|19|20)\d{2})\b", display_name)
    if match:
        return match.group(1)
    if re.match(r"^(?:NV|N\.V\.)\b", display_name, re.IGNORECASE):
        return "NV"
    return None


def _wine_name_from_display(definition: CTWineDefinition) -> str:
    name = definition.display_name
    if definition.vintage and name.lower().startswith(definition.vintage.lower()):
        name = name[len(definition.vintage):].strip()
    if definition.producer and name.lower().startswith(definition.producer.lower()):
        name = name[len(definition.producer):].strip()
    return name or definition.display_name
