from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .models import RawRow
from .normalize import normalize_size
from .table_detect import (
    StructuredInput,
    TableRegion,
    _field_for_header,
    detect_table_regions,
    extract_table_regions,
)

DELIMITER_CANDIDATES = ",;\t|"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".heic"}
TEXT_SUFFIXES = {".txt", ".text", ".md"}
TABLE_SUFFIXES = {".csv", ".tsv", ".txt", ""}

COUNTRY_VALUES = {
    "argentina",
    "australia",
    "austria",
    "canada",
    "chile",
    "france",
    "germany",
    "italy",
    "new zealand",
    "portugal",
    "south africa",
    "spain",
    "switzerland",
    "us",
    "usa",
    "united states",
}
VARIETAL_TOKENS = {
    "barolo",
    "bordeaux",
    "cab",
    "cabernet",
    "cab-sauv",
    "chardonnay",
    "cuvee",
    "grenache",
    "meritage",
    "merlot",
    "pinot",
    "riesling",
    "sauvignon",
    "syrah",
    "shiraz",
    "zinfandel",
}
CORE_FIELDS = {"producer", "name", "vintage", "quantity", "size"}
SUPPORT_FIELDS = {"country", "region", "subregion", "appellation", "varietal"}


@dataclass
class DetectedRegion:
    region_type: str
    extraction_method: str
    source_name: str | None
    sheet_name: str | None = None
    source_page: int | None = None
    header_row_index: int | None = None
    data_start_row_index: int | None = None
    data_end_row_index: int | None = None
    confidence: float = 0.0
    detected_headers: list[str] | None = None
    row_count: int = 0
    field_evidence: dict[str, Any] | None = None
    skip_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.header_row_index is not None:
            result["header_row_number"] = self.header_row_index + 1
        if self.data_start_row_index is not None:
            result["data_start_row_number"] = self.data_start_row_index + 1
        if self.data_end_row_index is not None and self.data_end_row_index >= 0:
            result["data_end_row_number"] = self.data_end_row_index + 1
        return result


@dataclass
class QuarantineItem:
    kind: str
    reason: str
    source_name: str | None
    row_number: int | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    table_index: int | None = None
    confidence: float = 0.0
    data: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IngestionResult:
    dataframe: pd.DataFrame
    detected_regions: list[DetectedRegion]
    quarantine_items: list[QuarantineItem]
    warnings: list[str]
    source_row_numbers: list[int]
    table_indices: list[int]
    field_evidence: dict[str, dict[str, Any]]
    sheet_name: str | None = None

    @property
    def selected_regions(self) -> list[DetectedRegion]:
        return [region for region in self.detected_regions if not region.skip_reason]

    @property
    def skipped_regions(self) -> list[DetectedRegion]:
        return [region for region in self.detected_regions if region.skip_reason]

    @property
    def confidence(self) -> float:
        selected = self.selected_regions
        if selected:
            return round(sum(region.confidence for region in selected) / len(selected), 4)
        return 0.0

    def to_report(self) -> dict[str, Any]:
        return {
            "sheet_name": self.sheet_name,
            "rows": len(self.dataframe),
            "columns": [str(column) for column in self.dataframe.columns],
            "confidence": self.confidence,
            "extraction_methods": sorted(
                {region.extraction_method for region in self.detected_regions}
            ),
            "selected_regions": [
                region.to_dict() for region in self.detected_regions if not region.skip_reason
            ],
            "skipped_regions": [
                region.to_dict() for region in self.detected_regions if region.skip_reason
            ],
            "field_evidence": self.field_evidence,
            "quarantine_count": len(self.quarantine_items),
            "warnings": self.warnings,
        }

    def to_structured_input(self) -> StructuredInput:
        selected: list[TableRegion] = []
        skipped: list[TableRegion] = []
        for region in self.detected_regions:
            if region.header_row_index is None or region.data_start_row_index is None:
                continue
            table_region = TableRegion(
                source_name=region.source_name,
                header_row_index=region.header_row_index,
                data_start_row_index=region.data_start_row_index,
                data_end_row_index=region.data_end_row_index or -1,
                confidence=region.confidence,
                detected_headers=region.detected_headers or [],
                row_count=region.row_count,
                skip_reason=region.skip_reason,
            )
            if region.skip_reason:
                skipped.append(table_region)
            else:
                selected.append(table_region)
        return StructuredInput(
            dataframe=self.dataframe,
            selected_regions=selected,
            skipped_regions=skipped,
            warnings=self.warnings,
            source_row_numbers=self.source_row_numbers,
            table_indices=self.table_indices,
            sheet_name=self.sheet_name,
        )


def ingest_file(
    path: str | Path,
    *,
    delimiter: str | None = None,
    sheet_name: str | None = None,
    use_ai: bool = False,
    all_sheets: bool = False,
    ocr: bool = False,
) -> IngestionResult:
    path = Path(path)
    suffix = path.suffix.lower()
    source_name = path.name

    if suffix in {".xlsx", ".xls", ".xlsm"}:
        return _ingest_excel(
            path,
            sheet_name=sheet_name,
            source_name=source_name,
            all_sheets=all_sheets,
        )
    if suffix == ".json":
        return _ingest_dataframe(
            pd.read_json(path),
            source_name=source_name,
            method="json_dataframe",
            warning="structure detection skipped for JSON input",
        )
    if suffix == ".pdf":
        return _ingest_pdf(path, source_name=source_name, ocr=ocr)
    if suffix in IMAGE_SUFFIXES:
        return _ingest_image(path, source_name=source_name, ocr=ocr)
    if use_ai and suffix not in TABLE_SUFFIXES | {".json"}:
        from .ai_parser import ai_parse_file

        return _ingest_dataframe(
            ai_parse_file(path),
            source_name=source_name,
            method="ai_fallback_parser",
            warning="structure detection skipped for AI fallback parser output",
            partition_rows=False,
        )

    if delimiter is None and suffix in TABLE_SUFFIXES:
        default_delimiter = "\t" if suffix == ".tsv" else ","
        delimiter = _detect_delimiter(path, default_delimiter)
    raw_df = _read_delimited_raw(path, delimiter or ",")
    if len(raw_df.columns) <= 1 and suffix in {".txt", ".text", ".md"}:
        return _ingest_text_lines(path.read_text(encoding="utf-8", errors="ignore"), source_name=source_name)
    return _ingest_raw_matrix(raw_df, source_name=source_name)


def raw_rows_from_ingestion(result: IngestionResult, source_file: str) -> list[RawRow]:
    df = result.dataframe.fillna("")
    rows: list[RawRow] = []
    for index, record in enumerate(df.to_dict(orient="records"), start=1):
        record_str = {str(key): str(value).strip() for key, value in record.items()}
        source_index = index - 1
        source_row_number = (
            result.source_row_numbers[source_index]
            if source_index < len(result.source_row_numbers)
            else None
        )
        table_index = (
            result.table_indices[source_index]
            if source_index < len(result.table_indices)
            else None
        )
        rows.append(
            RawRow(
                source_file=source_file,
                row_number=index,
                data=record_str,
                source_row_number=source_row_number,
                table_index=table_index,
                sheet_name=result.sheet_name,
            )
        )
    return rows


def quarantine_to_dataframe(items: list[QuarantineItem]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        row = item.to_dict()
        data = row.pop("data") or {}
        row["data"] = " | ".join(f"{key}={value}" for key, value in data.items() if value)
        rows.append(row)
    return pd.DataFrame(
        rows,
        columns=[
            "kind",
            "reason",
            "source_name",
            "sheet_name",
            "page_number",
            "row_number",
            "table_index",
            "confidence",
            "data",
        ],
    )


def _detect_delimiter(path: Path, default: str) -> str:
    try:
        sample = path.read_text(encoding="utf-8", errors="ignore")[:8192]
    except OSError:
        return default
    if not sample.strip():
        return default
    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITER_CANDIDATES).delimiter
    except csv.Error:
        return default


def _read_delimited_raw(path: Path, delimiter: str) -> pd.DataFrame:
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as source:
        rows = list(csv.reader(source, delimiter=delimiter))
    if not rows:
        return pd.DataFrame()
    max_width = max(len(row) for row in rows)
    padded_rows = [row + [""] * (max_width - len(row)) for row in rows]
    return pd.DataFrame(padded_rows).fillna("")


def _ingest_excel(
    path: Path,
    *,
    sheet_name: str | None,
    source_name: str,
    all_sheets: bool,
) -> IngestionResult:
    if all_sheets:
        workbook = pd.ExcelFile(path, engine="openpyxl")
        results = [
            _ingest_raw_matrix(
                pd.read_excel(path, dtype=str, engine="openpyxl", header=None, sheet_name=name),
                source_name=source_name,
                sheet_name=name,
            )
            for name in workbook.sheet_names
        ]
        return _combine_results(results, sheet_name=None)

    selected_sheet = sheet_name or 0
    raw_df = pd.read_excel(
        path,
        dtype=str,
        engine="openpyxl",
        header=None,
        sheet_name=selected_sheet,
    )
    return _ingest_raw_matrix(
        raw_df,
        source_name=source_name,
        sheet_name=str(sheet_name) if sheet_name is not None else None,
    )


def _ingest_raw_matrix(
    raw_df: pd.DataFrame,
    *,
    source_name: str,
    sheet_name: str | None = None,
) -> IngestionResult:
    regions = detect_table_regions(raw_df, source_name=source_name)
    structured = extract_table_regions(raw_df, regions, sheet_name=sheet_name)
    result = _from_structured_input(
        structured,
        source_name=source_name,
        method="table_region",
    )
    if not structured.selected_regions and _looks_like_line_inventory(raw_df):
        text = "\n".join(
            " ".join(str(value).strip() for value in raw_df.iloc[index].tolist() if str(value).strip())
            for index in range(len(raw_df))
        )
        return _ingest_text_lines(text, source_name=source_name)
    return result


def _ingest_dataframe(
    df: pd.DataFrame,
    *,
    source_name: str,
    method: str,
    warning: str | None = None,
    partition_rows: bool = True,
) -> IngestionResult:
    dataframe = df.fillna("").copy()
    dataframe.columns = [str(column) for column in dataframe.columns]
    initial_evidence = build_field_evidence(dataframe)
    source_row_numbers = list(range(1, len(dataframe) + 1))
    table_indices = [1] * len(dataframe)
    quarantine_items: list[QuarantineItem] = []
    if partition_rows:
        dataframe, source_row_numbers, table_indices, quarantine_items = (
            _partition_rows_by_wine_evidence(
                dataframe,
                source_row_numbers=source_row_numbers,
                table_indices=table_indices,
                field_evidence=initial_evidence,
                source_name=source_name,
                sheet_name=None,
            )
        )
    field_evidence = build_field_evidence(dataframe)
    warnings = [warning] if warning else []
    return IngestionResult(
        dataframe=dataframe,
        detected_regions=[
            DetectedRegion(
                region_type="dataframe",
                extraction_method=method,
                source_name=source_name,
                confidence=1.0,
                detected_headers=[str(column) for column in dataframe.columns],
                row_count=len(dataframe),
                field_evidence=field_evidence,
            )
        ],
        quarantine_items=quarantine_items,
        warnings=warnings,
        source_row_numbers=source_row_numbers,
        table_indices=table_indices,
        field_evidence=field_evidence,
    )


def _from_structured_input(
    structured: StructuredInput,
    *,
    source_name: str,
    method: str,
) -> IngestionResult:
    initial_evidence = build_field_evidence(structured.dataframe)
    dataframe, source_row_numbers, table_indices, row_quarantine = (
        _partition_rows_by_wine_evidence(
            structured.dataframe,
            source_row_numbers=structured.source_row_numbers,
            table_indices=structured.table_indices,
            field_evidence=initial_evidence,
            source_name=source_name,
            sheet_name=structured.sheet_name,
        )
    )
    field_evidence = build_field_evidence(dataframe)
    detected_regions: list[DetectedRegion] = []
    for region in structured.selected_regions:
        detected_regions.append(
            _detected_region_from_table(
                region,
                method,
                field_evidence,
                sheet_name=structured.sheet_name,
            )
        )
    for region in structured.skipped_regions:
        detected_regions.append(
            _detected_region_from_table(
                region,
                method,
                field_evidence,
                sheet_name=structured.sheet_name,
            )
        )

    quarantine_items = [
        QuarantineItem(
            kind="region",
            reason=region.skip_reason or "skipped table region",
            source_name=source_name,
            sheet_name=structured.sheet_name,
            row_number=region.header_row_index + 1,
            confidence=region.confidence,
            data={"headers": ", ".join(region.detected_headers)},
        )
        for region in structured.skipped_regions
    ]
    quarantine_items.extend(row_quarantine)

    return IngestionResult(
        dataframe=dataframe,
        detected_regions=detected_regions,
        quarantine_items=quarantine_items,
        warnings=structured.warnings,
        source_row_numbers=source_row_numbers,
        table_indices=table_indices,
        field_evidence=field_evidence,
        sheet_name=structured.sheet_name,
    )


def _detected_region_from_table(
    region: TableRegion,
    method: str,
    field_evidence: dict[str, dict[str, Any]],
    *,
    sheet_name: str | None = None,
) -> DetectedRegion:
    return DetectedRegion(
        region_type="table",
        extraction_method=method,
        source_name=region.source_name,
        sheet_name=sheet_name,
        header_row_index=region.header_row_index,
        data_start_row_index=region.data_start_row_index,
        data_end_row_index=region.data_end_row_index,
        confidence=region.confidence,
        detected_headers=region.detected_headers,
        row_count=region.row_count,
        field_evidence=field_evidence,
        skip_reason=region.skip_reason,
    )


def _ingest_text_lines(text: str, *, source_name: str, page_number: int | None = None) -> IngestionResult:
    rows: list[dict[str, str]] = []
    source_rows: list[int] = []
    quarantine: list[QuarantineItem] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parsed = _parse_wine_text_line(line)
        if parsed is None:
            quarantine.append(
                QuarantineItem(
                    kind="line",
                    reason="line did not contain enough wine evidence",
                    source_name=source_name,
                    row_number=line_number,
                    page_number=page_number,
                    data={"raw_text": line},
                )
            )
            continue
        rows.append(parsed)
        source_rows.append(line_number)

    dataframe = pd.DataFrame(
        rows,
        columns=["producer", "name", "vintage", "quantity", "size", "location", "raw_text"],
    ).fillna("")
    field_evidence = build_field_evidence(dataframe)
    return IngestionResult(
        dataframe=dataframe,
        detected_regions=[
            DetectedRegion(
                region_type="text",
                extraction_method="line_text",
                source_name=source_name,
                source_page=page_number,
                confidence=0.65 if rows else 0.0,
                detected_headers=[str(column) for column in dataframe.columns],
                row_count=len(dataframe),
                field_evidence=field_evidence,
            )
        ],
        quarantine_items=quarantine,
        warnings=[] if rows else ["no structured wine lines were detected"],
        source_row_numbers=source_rows,
        table_indices=[1] * len(rows),
        field_evidence=field_evidence,
    )


def _parse_wine_text_line(line: str) -> dict[str, str] | None:
    vintage_match = re.search(r"\b(?:18|19|20)\d{2}\b|\bNV\b", line, flags=re.IGNORECASE)
    quantity_match = re.search(r"\b(\d+)\s*(?:x|bottles?|btls?)\b", line, flags=re.IGNORECASE)
    size_match = re.search(r"\b(?:375|500|750|1500|3000)\s*ml\b|\b1\s*l(?:iter|itre)?\b", line, flags=re.IGNORECASE)
    location_match = re.search(r"\b(?:cellar|rack|bin)\s+[A-Za-z0-9-]+\b", line, flags=re.IGNORECASE)

    evidence = sum(bool(match) for match in (vintage_match, quantity_match, size_match))
    alpha_words = re.findall(r"[A-Za-z][A-Za-z.'-]+", line)
    if evidence < 1 or len(alpha_words) < 2:
        return None

    cleaned = line
    for match in (quantity_match, size_match, location_match):
        if match:
            cleaned = cleaned.replace(match.group(0), " ")
    if vintage_match:
        cleaned = cleaned.replace(vintage_match.group(0), " ")
    cleaned = re.sub(r"[-–—:,;()]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = cleaned.split()
    if len(words) < 2:
        return None

    producer = words[0]
    name = " ".join(words[1:])
    return {
        "producer": producer,
        "name": name,
        "vintage": vintage_match.group(0).upper() if vintage_match else "",
        "quantity": quantity_match.group(1) if quantity_match else "",
        "size": normalize_size(size_match.group(0)) if size_match else "",
        "location": location_match.group(0) if location_match else "",
        "raw_text": line,
    }


def _ingest_pdf(path: Path, *, source_name: str, ocr: bool) -> IngestionResult:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except Exception:
        return _unsupported_result(
            source_name=source_name,
            reason="PDF text extraction dependency is not installed",
            suffix="pdf",
        )

    try:
        reader = PdfReader(str(path))
        page_results: list[IngestionResult] = []
        empty_page_items: list[QuarantineItem] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                page_results.append(
                    _ingest_text_lines(text, source_name=source_name, page_number=index)
                )
                continue
            empty_page_items.append(
                QuarantineItem(
                    kind="page",
                    reason=_pdf_no_text_reason(ocr),
                    source_name=source_name,
                    page_number=index,
                    data={"file_type": "pdf"},
                )
            )
        result = _combine_results(page_results)
        result.quarantine_items.extend(empty_page_items)
        if empty_page_items:
            result.warnings.append(_pdf_no_text_reason(ocr))
        return result
    except Exception as exc:
        return _unsupported_result(
            source_name=source_name,
            reason=f"PDF text extraction failed: {exc}",
            suffix="pdf",
        )


def _pdf_no_text_reason(ocr: bool) -> str:
    if ocr:
        return "PDF page contained no extractable text; scanned-PDF OCR is not available"
    return "PDF page contained no extractable text; rerun with --ocr only after OCR support is available"


def _ingest_image(path: Path, *, source_name: str, ocr: bool) -> IngestionResult:
    if not ocr:
        return _unsupported_result(
            source_name=source_name,
            reason="OCR disabled; rerun with --ocr after installing OCR dependencies",
            suffix=path.suffix.lower().lstrip("."),
        )
    try:
        from PIL import Image  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except Exception:
        return _unsupported_result(
            source_name=source_name,
            reason="OCR dependencies are not installed",
            suffix=path.suffix.lower().lstrip("."),
        )
    try:
        text = pytesseract.image_to_string(Image.open(path))
        return _ingest_text_lines(text, source_name=source_name)
    except Exception as exc:
        return _unsupported_result(
            source_name=source_name,
            reason=f"OCR failed: {exc}",
            suffix=path.suffix.lower().lstrip("."),
        )


def _unsupported_result(*, source_name: str, reason: str, suffix: str) -> IngestionResult:
    item = QuarantineItem(
        kind="document",
        reason=reason,
        source_name=source_name,
        data={"file_type": suffix},
    )
    return IngestionResult(
        dataframe=pd.DataFrame(),
        detected_regions=[
            DetectedRegion(
                region_type="document",
                extraction_method="unsupported",
                source_name=source_name,
                confidence=0.0,
                row_count=0,
                skip_reason=reason,
            )
        ],
        quarantine_items=[item],
        warnings=[reason],
        source_row_numbers=[],
        table_indices=[],
        field_evidence={},
    )


def _combine_results(results: list[IngestionResult], sheet_name: str | None = None) -> IngestionResult:
    if not results:
        return IngestionResult(
            dataframe=pd.DataFrame(),
            detected_regions=[],
            quarantine_items=[],
            warnings=["no inputs were available to combine"],
            source_row_numbers=[],
            table_indices=[],
            field_evidence={},
            sheet_name=sheet_name,
        )

    columns: list[str] = []
    for result in results:
        for column in result.dataframe.columns:
            if column not in columns:
                columns.append(str(column))
    dataframe = pd.concat(
        [result.dataframe.reindex(columns=columns).fillna("") for result in results],
        ignore_index=True,
    ) if columns else pd.DataFrame()
    field_evidence = build_field_evidence(dataframe)
    source_rows: list[int] = []
    table_indices: list[int] = []
    for index, result in enumerate(results, start=1):
        source_rows.extend(result.source_row_numbers)
        table_indices.extend([index] * len(result.source_row_numbers))
    return IngestionResult(
        dataframe=dataframe,
        detected_regions=[region for result in results for region in result.detected_regions],
        quarantine_items=[item for result in results for item in result.quarantine_items],
        warnings=[warning for result in results for warning in result.warnings],
        source_row_numbers=source_rows,
        table_indices=table_indices,
        field_evidence=field_evidence,
        sheet_name=sheet_name,
    )


def build_field_evidence(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    text_candidates: list[tuple[str, float]] = []
    for column in df.columns:
        values = [str(value).strip() for value in df[column].tolist() if str(value).strip()]
        header_field = _field_for_header(str(column))
        value_scores = _value_field_scores(values)
        best_field = header_field
        confidence = 0.95 if header_field else 0.0
        if value_scores:
            value_field, value_confidence = max(value_scores.items(), key=lambda item: item[1])
            if value_confidence > confidence:
                best_field = value_field
                confidence = value_confidence
        text_score = _text_column_score(values)
        if text_score >= 0.45 and not best_field:
            text_candidates.append((str(column), text_score))
        evidence[str(column)] = {
            "best_field": best_field,
            "confidence": round(confidence, 4),
            "header_field": header_field,
            "value_scores": {key: round(value, 4) for key, value in value_scores.items()},
            "text_score": round(text_score, 4),
            "non_empty_count": len(values),
            "sample_values": values[:5],
        }

    for ordinal, (column, score) in enumerate(text_candidates[:2], start=1):
        inferred = "producer" if ordinal == 1 else "name"
        if not any(item["best_field"] == inferred for item in evidence.values()):
            evidence[column]["best_field"] = inferred
            evidence[column]["confidence"] = round(min(score, 0.7), 4)
            evidence[column]["inferred_from_text_position"] = True
    return evidence


def _partition_rows_by_wine_evidence(
    dataframe: pd.DataFrame,
    *,
    source_row_numbers: list[int],
    table_indices: list[int],
    field_evidence: dict[str, dict[str, Any]],
    source_name: str,
    sheet_name: str | None,
) -> tuple[pd.DataFrame, list[int], list[int], list[QuarantineItem]]:
    if dataframe.empty:
        return dataframe, source_row_numbers, table_indices, []

    accepted_records: list[dict[str, str]] = []
    accepted_source_rows: list[int] = []
    accepted_table_indices: list[int] = []
    quarantine_items: list[QuarantineItem] = []
    columns = [str(column) for column in dataframe.columns]
    records = dataframe.fillna("").to_dict(orient="records")

    for index, record in enumerate(records):
        record_str = {str(key): str(value).strip() for key, value in record.items()}
        score, core_fields = _row_wine_score(record_str, field_evidence)
        source_row_number = (
            source_row_numbers[index] if index < len(source_row_numbers) else index + 1
        )
        table_index = table_indices[index] if index < len(table_indices) else 1
        if len(core_fields) >= 2:
            accepted_records.append(record_str)
            accepted_source_rows.append(source_row_number)
            accepted_table_indices.append(table_index)
            continue

        reason = "row did not contain enough wine evidence"
        if core_fields:
            reason += f" (found core fields: {', '.join(sorted(core_fields))})"
        quarantine_items.append(
            QuarantineItem(
                kind="row",
                reason=reason,
                source_name=source_name,
                row_number=source_row_number,
                sheet_name=sheet_name,
                table_index=table_index,
                confidence=round(score, 4),
                data=record_str,
            )
        )

    return (
        pd.DataFrame(accepted_records, columns=columns).fillna(""),
        accepted_source_rows,
        accepted_table_indices,
        quarantine_items,
    )


def _row_wine_score(
    record: dict[str, str],
    field_evidence: dict[str, dict[str, Any]],
) -> tuple[float, set[str]]:
    core_fields: set[str] = set()
    support_fields: set[str] = set()

    for header, value in record.items():
        if not value:
            continue
        field = _field_for_row_value(header, value, field_evidence)
        if field in CORE_FIELDS:
            core_fields.add(field)
        elif field in SUPPORT_FIELDS:
            support_fields.add(field)

    score = min(1.0, (0.42 * len(core_fields)) + (0.08 * len(support_fields)))
    return score, core_fields


def _field_for_row_value(
    header: str,
    value: str,
    field_evidence: dict[str, dict[str, Any]],
) -> str | None:
    profile = field_evidence.get(header) or {}
    field = profile.get("best_field") or profile.get("header_field")
    if _value_supports_field(value, field):
        return field

    if _looks_like_vintage(value):
        return "vintage"
    if _looks_like_size(value):
        return "size"
    if _looks_like_quantity(value):
        return "quantity"
    if value.strip().lower() in COUNTRY_VALUES:
        return "country"
    if _looks_like_varietal(value):
        return "varietal"
    if field in {"producer", "name"} and _looks_like_identity_text(value):
        return field
    return None


def _value_supports_field(value: str, field: str | None) -> bool:
    if field in {"producer", "name"}:
        return _looks_like_identity_text(value)
    if field == "vintage":
        return _looks_like_vintage(value)
    if field == "size":
        return _looks_like_size(value)
    if field == "quantity":
        return _looks_like_quantity(value)
    if field == "country":
        return value.strip().lower() in COUNTRY_VALUES
    if field in {"region", "subregion", "appellation"}:
        return _looks_like_identity_text(value)
    if field == "varietal":
        return _looks_like_varietal(value) or _looks_like_identity_text(value)
    return False


def _looks_like_identity_text(value: str) -> bool:
    text = value.strip()
    if not re.search(r"[A-Za-z]", text):
        return False
    if _looks_like_vintage(text) or _looks_like_size(text) or _looks_like_date(text):
        return False
    return len(re.findall(r"[A-Za-z][A-Za-z.'-]*", text)) >= 1


def _value_field_scores(values: list[str]) -> dict[str, float]:
    if not values:
        return {}
    total = len(values)
    scores = {
        "vintage": sum(1 for value in values if _looks_like_vintage(value)) / total,
        "size": sum(1 for value in values if _looks_like_size(value)) / total,
        "quantity": sum(1 for value in values if _looks_like_quantity(value)) / total,
        "country": sum(1 for value in values if value.strip().lower() in COUNTRY_VALUES) / total,
        "purchase_date": sum(1 for value in values if _looks_like_date(value)) / total,
        "varietal": sum(1 for value in values if _looks_like_varietal(value)) / total,
    }
    return {field: score for field, score in scores.items() if score >= 0.55}


def _text_column_score(values: list[str]) -> float:
    if not values:
        return 0.0
    text_like = 0
    for value in values:
        if re.search(r"[A-Za-z]", value) and not _looks_like_size(value) and not _looks_like_date(value):
            text_like += 1
    return text_like / len(values)


def _looks_like_vintage(value: str) -> bool:
    text = value.strip().lower()
    return text in {"nv", "n/v", "n/a"} or bool(re.fullmatch(r"(?:18|19|20)\d{2}", text))


def _looks_like_size(value: str) -> bool:
    return normalize_size(value) in {"375 ml", "500 ml", "750 ml", "1500 ml", "3000 ml"}


def _looks_like_quantity(value: str) -> bool:
    text = value.strip()
    if not re.fullmatch(r"\d+(?:\.0)?", text):
        return False
    try:
        number = float(text)
    except ValueError:
        return False
    return 0 <= number <= 500 and not _looks_like_vintage(text)


def _looks_like_date(value: str) -> bool:
    text = value.strip()
    return bool(
        re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", text)
        or re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", text)
    )


def _looks_like_varietal(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9-]+", " ", value.lower())
    tokens = set(normalized.split())
    return bool(tokens & VARIETAL_TOKENS)


def _looks_like_line_inventory(raw_df: pd.DataFrame) -> bool:
    if raw_df.empty or len(raw_df.columns) != 1:
        return False
    values = [str(value).strip() for value in raw_df.iloc[:, 0].tolist() if str(value).strip()]
    if not values:
        return False
    evidence_rows = sum(1 for value in values if _parse_wine_text_line(value) is not None)
    return evidence_rows / len(values) >= 0.4
