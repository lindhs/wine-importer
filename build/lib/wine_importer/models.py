from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, Field


class RawRow(BaseModel):
    row_number: int
    data: dict[str, str]


class MappedWineRow(BaseModel):
    row_number: int
    producer: str | None = None
    name: str | None = None
    vintage: str | None = None
    region: str | None = None
    appellation: str | None = None
    varietal: str | None = None
    quantity: int | None = None
    size: str | None = None
    location: str | None = None
    bin: str | None = None
    notes: str | None = None
    original: dict[str, str] = Field(default_factory=dict)


class NormalizedWineRow(MappedWineRow):
    normalized_producer: str | None = None
    normalized_name: str | None = None
    normalized_vintage: str | None = None
    normalized_region: str | None = None
    normalized_appellation: str | None = None
    normalized_varietal: str | None = None
    normalized_size: str | None = None


class CanonicalWine(BaseModel):
    id: str
    producer: str
    name: str
    vintage: str
    region: str
    appellation: str
    varietal: str
    quantity: int | None = None
    size: str | None = None
    notes: str | None = None


class CandidateMatch(BaseModel):
    row_number: int
    canonical_id: str | None = None
    producer: str | None = None
    name: str | None = None
    vintage: str | None = None
    region: str | None = None
    appellation: str | None = None
    varietal: str | None = None
    score: float = 0.0
    source: dict[str, Any] = Field(default_factory=dict)


class MatchResult(BaseModel):
    row_number: int
    user_row: dict[str, Any]
    candidates: list[CandidateMatch] = Field(default_factory=list)


class ReviewedMatch(BaseModel):
    row_number: int
    user_row: dict[str, Any]
    best_match: CandidateMatch | None = None
    status: Literal["accepted", "review_needed", "rejected"]
    reason: str | None = None
