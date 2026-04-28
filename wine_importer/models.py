from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, Field


class RawRow(BaseModel):
    source_file: str
    row_number: int
    data: dict[str, str]


class MappedWineRow(BaseModel):
    row_number: int
    producer: str | None = None
    name: str | None = None
    vineyard: str | None = None
    vintage: str | None = None
    country: str | None = None
    region: str | None = None
    subregion: str | None = None
    appellation: str | None = None
    varietal: str | None = None
    quantity: float | None = None
    size: str | None = None
    bottle_size: str | None = None
    purchase_date: str | None = None
    location: str | None = None
    bin: str | None = None
    notes: str | None = None
    ratings: dict[str, str] = Field(default_factory=dict)
    original: dict[str, str] = Field(default_factory=dict)


class NormalizedWineRow(MappedWineRow):
    normalized_producer: str | None = None
    normalized_name: str | None = None
    normalized_vineyard: str | None = None
    normalized_vintage: str | None = None
    normalized_country: str | None = None
    normalized_region: str | None = None
    normalized_subregion: str | None = None
    normalized_appellation: str | None = None
    normalized_varietal: str | None = None
    normalized_size: str | None = None
    normalized_bottle_size: str | None = None


class CanonicalWine(BaseModel):
    id: str
    producer: str
    name: str
    vintage: str
    country: str | None = None
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
    blocking_reason: str | None = None
    producer_score: float | None = None
    name_score: float | None = None
    vintage_score: float | None = None
    region_score: float | None = None
    appellation_score: float | None = None
    varietal_score: float | None = None
    hard_conflicts: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)


class MatchResult(BaseModel):
    row_number: int
    user_row: dict[str, Any]
    candidates: list[CandidateMatch] = Field(default_factory=list)
    top_1_score: float | None = None
    top_2_score: float | None = None
    score_margin: float | None = None
    num_candidates: int = 0


class ReviewedMatch(BaseModel):
    row_number: int
    user_row: dict[str, Any]
    best_match: CandidateMatch | None = None
    status: Literal["accepted", "review_needed", "rejected"]
    reason: str | None = None
    top_1_score: float | None = None
    top_2_score: float | None = None
    score_margin: float | None = None
    num_candidates: int = 0
