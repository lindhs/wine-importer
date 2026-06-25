"""SQLite-backed resolution cache.

Formalizes Phase 3's JSON resolution store. Two tables:

- ``wine_definitions`` — every CellarTracker wine we've parsed, keyed by
  iWine id. This is the growing canonical mirror; ``all_canonical()`` turns
  it into the candidate list the matcher searches.
- ``resolutions`` — maps a normalized wine signature ("producer|name|vintage")
  to the iWine it resolved to, so a repeated run is a cache hit and never
  re-opens the browser. A NULL ct_wine_id is a *negative* cache entry
  ("searched, confirmed not on CellarTracker") with a shorter TTL.

There is no local canonical CSV in the rebuilt design — this cache is the
canonical layer, populated exclusively from browser-confirmed resolutions.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .cellartracker_lookup import (
    CTWineDefinition,
    load_resolution_store,
    to_canonical_wine,
)
from .models import CanonicalWine, NormalizedWineRow
from .normalize import normalize_text, normalize_vintage

DEFAULT_CACHE_PATH = Path.home() / ".wine-importer" / "ct_cache.db"
POSITIVE_TTL_DAYS = 180
NEGATIVE_TTL_DAYS = 30


@dataclass(frozen=True)
class CachedResolution:
    signature: str
    ct_wine_id: str | None
    definition: CTWineDefinition | None
    score: float | None
    resolved_at: datetime
    ttl_days: int

    @property
    def is_negative(self) -> bool:
        return self.ct_wine_id is None

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now > self.resolved_at + timedelta(days=self.ttl_days)


class ResolutionCache:
    def __init__(self, path: str | Path = DEFAULT_CACHE_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def __enter__(self) -> "ResolutionCache":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS resolutions (
                signature   TEXT PRIMARY KEY,
                ct_wine_id  TEXT,
                score       REAL,
                resolved_at TEXT NOT NULL,
                ttl_days    INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wine_definitions (
                ct_wine_id  TEXT PRIMARY KEY,
                definition  TEXT NOT NULL,
                fetched_at  TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    # ---- signatures -------------------------------------------------------

    @staticmethod
    def signature(producer: str | None, name: str | None, vintage: str | None) -> str:
        parts = [
            normalize_text(producer) or "",
            normalize_text(name) or "",
            normalize_vintage(vintage) or "",
        ]
        return "|".join(parts)

    @classmethod
    def signature_for_row(cls, row: NormalizedWineRow) -> str:
        return "|".join(
            [
                row.normalized_producer or normalize_text(row.producer) or "",
                row.normalized_name or normalize_text(row.name) or "",
                row.normalized_vintage or normalize_vintage(row.vintage) or "",
            ]
        )

    # ---- wine definitions -------------------------------------------------

    def store_definition(self, definition: CTWineDefinition) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO wine_definitions (ct_wine_id, definition, fetched_at) "
            "VALUES (?, ?, ?)",
            (
                definition.ct_wine_id,
                json.dumps(asdict(definition), ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def store_definitions(self, definitions: list[CTWineDefinition]) -> int:
        existing = {row["ct_wine_id"] for row in self._conn.execute(
            "SELECT ct_wine_id FROM wine_definitions"
        )}
        added = sum(1 for d in definitions if d.ct_wine_id not in existing)
        for definition in definitions:
            self.store_definition(definition)
        return added

    def get_definition(self, ct_wine_id: str) -> CTWineDefinition | None:
        row = self._conn.execute(
            "SELECT definition FROM wine_definitions WHERE ct_wine_id = ?",
            (ct_wine_id,),
        ).fetchone()
        if row is None:
            return None
        return _definition_from_json(row["definition"])

    def all_definitions(self) -> list[CTWineDefinition]:
        rows = self._conn.execute(
            "SELECT definition FROM wine_definitions ORDER BY ct_wine_id"
        ).fetchall()
        definitions = []
        for row in rows:
            definition = _definition_from_json(row["definition"])
            if definition is not None:
                definitions.append(definition)
        return definitions

    def all_canonical(self) -> list[CanonicalWine]:
        return [to_canonical_wine(definition) for definition in self.all_definitions()]

    # ---- resolutions (signature -> iWine) ---------------------------------

    def record_resolution(
        self,
        signature: str,
        definition: CTWineDefinition,
        score: float | None = None,
        ttl_days: int = POSITIVE_TTL_DAYS,
    ) -> None:
        self.store_definition(definition)
        self._conn.execute(
            "INSERT OR REPLACE INTO resolutions (signature, ct_wine_id, score, resolved_at, ttl_days) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                signature,
                definition.ct_wine_id,
                score,
                datetime.now(timezone.utc).isoformat(),
                ttl_days,
            ),
        )
        self._conn.commit()

    def record_miss(self, signature: str, ttl_days: int = NEGATIVE_TTL_DAYS) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO resolutions (signature, ct_wine_id, score, resolved_at, ttl_days) "
            "VALUES (?, NULL, NULL, ?, ?)",
            (signature, datetime.now(timezone.utc).isoformat(), ttl_days),
        )
        self._conn.commit()

    def lookup(self, signature: str, now: datetime | None = None) -> CachedResolution | None:
        row = self._conn.execute(
            "SELECT signature, ct_wine_id, score, resolved_at, ttl_days "
            "FROM resolutions WHERE signature = ?",
            (signature,),
        ).fetchone()
        if row is None:
            return None
        definition = self.get_definition(row["ct_wine_id"]) if row["ct_wine_id"] else None
        resolution = CachedResolution(
            signature=row["signature"],
            ct_wine_id=row["ct_wine_id"],
            definition=definition,
            score=row["score"],
            resolved_at=datetime.fromisoformat(row["resolved_at"]),
            ttl_days=row["ttl_days"],
        )
        if resolution.is_expired(now):
            return None
        return resolution

    # ---- migration / maintenance ------------------------------------------

    def import_json_store(self, path: str | Path) -> int:
        store = load_resolution_store(path)
        definitions = []
        for entry in store.values():
            definition = _definition_from_json_dict(entry.get("definition"))
            if definition is not None:
                definitions.append(definition)
        return self.store_definitions(definitions)

    def import_canonical_csv(self, path: str | Path) -> int:
        # Migrate a legacy hand-curated canonical CSV into the cache so the
        # offline pipeline keeps working without a --canonical flag.
        from .search import load_canonical_wines

        definitions = [_definition_from_canonical(wine) for wine in load_canonical_wines(path)]
        return self.store_definitions(definitions)

    def stats(self) -> dict[str, int]:
        definitions = self._conn.execute(
            "SELECT COUNT(*) AS n FROM wine_definitions"
        ).fetchone()["n"]
        positive = self._conn.execute(
            "SELECT COUNT(*) AS n FROM resolutions WHERE ct_wine_id IS NOT NULL"
        ).fetchone()["n"]
        negative = self._conn.execute(
            "SELECT COUNT(*) AS n FROM resolutions WHERE ct_wine_id IS NULL"
        ).fetchone()["n"]
        return {
            "wine_definitions": definitions,
            "resolutions_positive": positive,
            "resolutions_negative": negative,
        }

    def clear(self) -> None:
        self._conn.executescript("DELETE FROM resolutions; DELETE FROM wine_definitions;")
        self._conn.commit()


def _definition_from_canonical(wine: CanonicalWine) -> CTWineDefinition:
    return CTWineDefinition(
        ct_wine_id=wine.ct_wine_id or wine.id,
        display_name=" ".join(p for p in (wine.vintage, wine.producer, wine.name) if p),
        vintage=wine.vintage or None,
        type=wine.type,
        producer=wine.producer or None,
        varietal=wine.varietal or None,
        designation=wine.designation,
        vineyard=wine.vineyard,
        country=wine.country,
        region=wine.region or None,
        subregion=wine.subregion,
        appellation=wine.appellation or None,
        url="",
    )


def _definition_from_json(raw: str) -> CTWineDefinition | None:
    try:
        return _definition_from_json_dict(json.loads(raw))
    except (json.JSONDecodeError, TypeError):
        return None


def _definition_from_json_dict(data: object) -> CTWineDefinition | None:
    if not isinstance(data, dict):
        return None
    try:
        return CTWineDefinition(**data)
    except TypeError:
        return None
