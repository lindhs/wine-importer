from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, replace
from typing import Any

import pandas as pd

from .normalize import normalize_size
from .schema_map import FIELD_KEYWORDS

MIN_HEADER_CONFIDENCE = 0.45


@dataclass
class TableRegion:
    source_name: str | None
    header_row_index: int
    data_start_row_index: int
    data_end_row_index: int
    confidence: float
    detected_headers: list[str]
    row_count: int
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["header_row_number"] = self.header_row_index + 1
        result["data_start_row_number"] = self.data_start_row_index + 1
        result["data_end_row_number"] = (
            self.data_end_row_index + 1 if self.data_end_row_index >= 0 else None
        )
        return result


@dataclass
class StructuredInput:
    dataframe: pd.DataFrame
    selected_regions: list[TableRegion]
    skipped_regions: list[TableRegion]
    warnings: list[str]
    source_row_numbers: list[int]
    table_indices: list[int]
    sheet_name: str | None = None

    def to_report(self) -> dict[str, Any]:
        return {
            "sheet_name": self.sheet_name,
            "rows": len(self.dataframe),
            "columns": [str(column) for column in self.dataframe.columns],
            "selected_regions": [region.to_dict() for region in self.selected_regions],
            "skipped_regions": [region.to_dict() for region in self.skipped_regions],
            "warnings": self.warnings,
        }


def detect_table_regions(
    df: pd.DataFrame,
    scan_rows: int | None = None,
    source_name: str | None = None,
) -> list[TableRegion]:
    raw = _clean_matrix(df)
    if raw.empty:
        return []

    limit = len(raw) if scan_rows is None else min(len(raw), scan_rows)
    candidates: list[tuple[int, float, list[str]]] = []
    for row_index in range(limit):
        headers = _row_values(raw, row_index)
        confidence = _header_confidence(headers, raw, row_index)
        if confidence >= MIN_HEADER_CONFIDENCE:
            candidates.append((row_index, confidence, _dedupe_headers(headers)))

    regions: list[TableRegion] = []
    candidate_indices = [row_index for row_index, _, _ in candidates]
    for index, (row_index, confidence, headers) in enumerate(candidates):
        data_start = row_index + 1
        next_header = (
            candidate_indices[index + 1]
            if index + 1 < len(candidate_indices)
            else len(raw)
        )
        data_end = next_header - 1
        row_count = _count_data_rows(raw, data_start, data_end, len(headers))
        if row_count <= 0:
            continue
        regions.append(
            TableRegion(
                source_name=source_name,
                header_row_index=row_index,
                data_start_row_index=data_start,
                data_end_row_index=data_end,
                confidence=round(confidence, 4),
                detected_headers=headers,
                row_count=row_count,
            )
        )
    return regions


def extract_table_regions(
    df: pd.DataFrame,
    regions: list[TableRegion],
    *,
    sheet_name: str | None = None,
) -> StructuredInput:
    raw = _clean_matrix(df)
    warnings: list[str] = []
    if raw.empty:
        return StructuredInput(
            dataframe=pd.DataFrame(),
            selected_regions=[],
            skipped_regions=[],
            warnings=["input contained no rows"],
            source_row_numbers=[],
            table_indices=[],
            sheet_name=sheet_name,
        )

    if not regions:
        warnings.append("no clear header row detected; using generic column names")
        return _generic_structured_input(raw, warnings=warnings, sheet_name=sheet_name)

    selected: list[TableRegion] = []
    skipped: list[TableRegion] = []
    records: list[dict[str, str]] = []
    source_row_numbers: list[int] = []
    table_indices: list[int] = []
    output_columns: list[str] = []

    base_signature = _header_signature(regions[0].detected_headers)
    base_fields = _field_signature(regions[0].detected_headers)

    for table_index, region in enumerate(regions, start=1):
        if selected and not _is_compatible(region, base_signature, base_fields):
            skipped.append(replace(region, skip_reason="incompatible headers"))
            continue

        region_records, region_rows = _extract_region_records(raw, region)
        if not region_records:
            skipped.append(replace(region, skip_reason="no data rows"))
            continue

        selected.append(replace(region, row_count=len(region_records)))
        for header in region.detected_headers:
            if header not in output_columns:
                output_columns.append(header)
        for record, source_row in zip(region_records, region_rows, strict=True):
            records.append(record)
            source_row_numbers.append(source_row)
            table_indices.append(table_index)

    if not records:
        warnings.append("detected table headers but no usable data rows")
        return _generic_structured_input(raw, warnings=warnings, sheet_name=sheet_name)

    dataframe = pd.DataFrame(records, columns=output_columns).fillna("")
    return StructuredInput(
        dataframe=dataframe,
        selected_regions=selected,
        skipped_regions=skipped,
        warnings=warnings,
        source_row_numbers=source_row_numbers,
        table_indices=table_indices,
        sheet_name=sheet_name,
    )


def _clean_matrix(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.fillna("").copy()
    cleaned.columns = list(range(len(cleaned.columns)))
    return cleaned.apply(lambda column: column.map(lambda value: str(value).strip()))


def _row_values(df: pd.DataFrame, row_index: int) -> list[str]:
    return [str(value).strip() for value in df.iloc[row_index].tolist()]


def _non_empty(values: list[str]) -> list[str]:
    return [value for value in values if value]


def _normalize_header(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", normalized)
    normalized = re.sub(r"([a-zA-Z])(\d)", r"\1 \2", normalized)
    normalized = re.sub(r"(\d)([a-zA-Z])", r"\1 \2", normalized)
    normalized = re.sub(r"[^a-zA-Z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip().lower()


def _field_for_header(value: str) -> str | None:
    normalized = _normalize_header(value)
    if not normalized:
        return None
    for field, keywords in FIELD_KEYWORDS.items():
        if normalized == field:
            return field
        for keyword in keywords:
            normalized_keyword = _normalize_header(keyword)
            if normalized == normalized_keyword:
                return field
    return None


def _is_numeric_like(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", text):
        return True
    if normalize_size(text) in {"375 ml", "500 ml", "750 ml", "1500 ml", "3000 ml"}:
        return True
    if re.fullmatch(r"(?:18|19|20)\d{2}", text):
        return True
    return bool(re.fullmatch(r"\d+(?:[.,]\d+)?", text))


def _header_confidence(values: list[str], df: pd.DataFrame, row_index: int) -> float:
    populated = _non_empty(values)
    if len(populated) < 2:
        return 0.0

    numeric_density = sum(1 for value in populated if _is_numeric_like(value)) / len(populated)
    if numeric_density > 0.45:
        return 0.0

    normalized_values = [_normalize_header(value) for value in populated]
    distinct_ratio = len(set(normalized_values)) / len(normalized_values)
    if distinct_ratio < 0.6:
        return 0.0

    field_hits = [_field_for_header(value) for value in populated]
    recognized_count = sum(1 for field in field_hits if field)
    recognized_ratio = recognized_count / len(populated)
    if recognized_count < 2:
        if recognized_count != 1 or not _has_section_boundary_before(df, row_index):
            return 0.0

    if not _has_following_data_row(df, row_index + 1, len(values)):
        return 0.0

    width_score = min(len(populated) / 6, 1.0)
    confidence = (
        0.25
        + 0.45 * recognized_ratio
        + 0.15 * distinct_ratio
        + 0.10 * width_score
        + 0.05 * min(recognized_count / 3, 1.0)
    )
    return min(confidence, 1.0)


def _has_following_data_row(df: pd.DataFrame, start_row: int, width: int) -> bool:
    for row_index in range(start_row, min(len(df), start_row + 5)):
        values = _row_values(df, row_index)[:width]
        populated = _non_empty(values)
        if len(populated) < 2:
            continue
        if _basic_header_like(values):
            continue
        return True
    return False


def _has_section_boundary_before(df: pd.DataFrame, row_index: int) -> bool:
    for previous_index in range(row_index - 1, max(-1, row_index - 3), -1):
        values = _row_values(df, previous_index)
        populated = _non_empty(values)
        if not populated:
            continue
        return len(populated) == 1
    return False


def _basic_header_like(values: list[str]) -> bool:
    populated = _non_empty(values)
    if len(populated) < 2:
        return False
    numeric_density = sum(1 for value in populated if _is_numeric_like(value)) / len(populated)
    if numeric_density > 0.45:
        return False
    recognized_count = sum(1 for value in populated if _field_for_header(value))
    return recognized_count >= 2 and (recognized_count / len(populated)) >= 0.45


def _count_data_rows(df: pd.DataFrame, start_row: int, end_row: int, width: int) -> int:
    count = 0
    for row_index in range(start_row, min(end_row + 1, len(df))):
        if _is_data_row(_row_values(df, row_index)[:width]):
            count += 1
    return count


def _is_data_row(values: list[str]) -> bool:
    populated = _non_empty(values)
    if len(populated) < 2:
        return False
    normalized_values = [_normalize_header(value) for value in populated]
    if normalized_values and len(set(normalized_values)) == 1:
        return False
    return True


def _dedupe_headers(values: list[str]) -> list[str]:
    headers: list[str] = []
    seen: dict[str, int] = {}
    for index, value in enumerate(values, start=1):
        header = value.strip()
        if not header or _is_numeric_like(header):
            header = f"column_{index}"
        normalized = _normalize_header(header) or f"column_{index}"
        count = seen.get(normalized, 0) + 1
        seen[normalized] = count
        if count > 1:
            header = f"{header}_{count}"
        headers.append(header)
    return headers


def _header_signature(headers: list[str]) -> set[str]:
    return {_normalize_header(header) for header in headers if _normalize_header(header)}


def _field_signature(headers: list[str]) -> set[str]:
    return {field for header in headers if (field := _field_for_header(header))}


def _is_compatible(
    region: TableRegion,
    base_signature: set[str],
    base_fields: set[str],
) -> bool:
    signature = _header_signature(region.detected_headers)
    fields = _field_signature(region.detected_headers)
    return len(signature & base_signature) >= 2 or len(fields & base_fields) >= 2


def _extract_region_records(
    df: pd.DataFrame,
    region: TableRegion,
) -> tuple[list[dict[str, str]], list[int]]:
    records: list[dict[str, str]] = []
    source_rows: list[int] = []
    width = len(region.detected_headers)
    for row_index in range(
        region.data_start_row_index,
        min(region.data_end_row_index + 1, len(df)),
    ):
        values = _row_values(df, row_index)[:width]
        if not _is_data_row(values):
            continue
        record = {
            header: values[index] if index < len(values) else ""
            for index, header in enumerate(region.detected_headers)
        }
        records.append(record)
        source_rows.append(row_index + 1)
    return records, source_rows


def _generic_structured_input(
    df: pd.DataFrame,
    *,
    warnings: list[str],
    sheet_name: str | None,
) -> StructuredInput:
    records: list[list[str]] = []
    source_row_numbers: list[int] = []
    max_width = 0
    for row_index in range(len(df)):
        values = _row_values(df, row_index)
        if not _non_empty(values):
            continue
        max_width = max(max_width, len(values))
        records.append(values)
        source_row_numbers.append(row_index + 1)

    columns = [f"column_{index}" for index in range(1, max_width + 1)]
    padded_records = [
        values + [""] * (max_width - len(values))
        for values in records
    ]
    return StructuredInput(
        dataframe=pd.DataFrame(padded_records, columns=columns).fillna(""),
        selected_regions=[],
        skipped_regions=[],
        warnings=warnings,
        source_row_numbers=source_row_numbers,
        table_indices=[1] * len(padded_records),
        sheet_name=sheet_name,
    )
