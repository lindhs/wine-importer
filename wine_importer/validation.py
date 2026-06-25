"""Input validation and data quality checks for the wine-importer pipeline."""

import logging
import re
from pathlib import Path

from .models import MappedWineRow
from .normalize import normalize_size, normalize_vintage
from .search import load_canonical_wines

logger = logging.getLogger(__name__)

_YEAR_PATTERN = re.compile(r"^(?:18|19|20)\d{2}$")
_INTEGER_PATTERN = re.compile(r"^\d+$")
_COUNTRY_NAMES = {
    "argentina",
    "australia",
    "austria",
    "canada",
    "chile",
    "france",
    "germany",
    "greece",
    "hungary",
    "italy",
    "new zealand",
    "portugal",
    "south africa",
    "spain",
    "switzerland",
    "united kingdom",
    "united states",
    "usa",
    "us",
}


def _looks_like_year(value: str | None) -> bool:
    if value is None:
        return False
    return bool(_YEAR_PATTERN.fullmatch(str(value).strip()))


def _looks_like_quantity(value: str | None) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(_INTEGER_PATTERN.fullmatch(text)) and not _looks_like_year(text)


def _looks_like_size(value: str | None) -> bool:
    return normalize_size(value) in {"375 ml", "500 ml", "750 ml", "1500 ml", "3000 ml"}


def _looks_like_country(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in _COUNTRY_NAMES


def _looks_like_wine_name_in_country(value: str | None) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text or _looks_like_country(text):
        return False
    normalized = text.lower()
    wine_markers = {
        "chateau",
        "domaine",
        "estate",
        "grand",
        "reserve",
        "riserva",
        "vineyard",
        "winery",
    }
    return len(text.split()) > 1 or any(marker in normalized for marker in wine_markers)


def _mapped_row_integrity_issues(row: MappedWineRow, label: str) -> list[str]:
    issues: list[str] = []
    if (
        _looks_like_year(row.producer)
        or _looks_like_quantity(row.producer)
        or _looks_like_size(row.producer)
    ):
        issues.append(
            f"{label}: producer looks like a shifted non-producer value "
            f"({row.producer!r})"
        )
    if _looks_like_size(row.varietal):
        issues.append(f"{label}: varietal looks like a shifted bottle size ({row.varietal!r})")
    if _looks_like_quantity(row.appellation):
        issues.append(
            f"{label}: appellation looks like a shifted quantity ({row.appellation!r})"
        )
    if _looks_like_wine_name_in_country(row.country):
        issues.append(f"{label}: country looks like a shifted wine name ({row.country!r})")
    return issues


def validate_canonical_records(records) -> list[str]:
    issues: list[str] = []
    for wine in records:
        label = f"canonical row {wine.id}"
        if (
            _looks_like_year(wine.producer)
            or _looks_like_quantity(wine.producer)
            or _looks_like_size(wine.producer)
        ):
            issues.append(
                f"{label}: producer looks like a shifted non-producer value "
                f"({wine.producer!r})"
            )
        if _looks_like_quantity(wine.name) or _looks_like_size(wine.name):
            issues.append(
                f"{label}: name looks like a shifted non-name value ({wine.name!r})"
            )
        if _looks_like_size(wine.varietal):
            issues.append(
                f"{label}: varietal looks like a shifted bottle size ({wine.varietal!r})"
            )
        if _looks_like_quantity(wine.appellation):
            issues.append(
                f"{label}: appellation looks like a shifted quantity ({wine.appellation!r})"
            )
        if _looks_like_wine_name_in_country(wine.country):
            issues.append(
                f"{label}: country looks like a shifted wine name ({wine.country!r})"
            )

        normalized_vintage = normalize_vintage(wine.vintage)
        if (
            normalized_vintage
            and normalized_vintage != "nv"
            and not _looks_like_year(normalized_vintage)
        ):
            issues.append(
                f"{label}: vintage is not a recognized vintage value ({wine.vintage!r})"
            )

        if wine.quantity is not None and wine.quantity < 0:
            issues.append(f"{label}: quantity cannot be negative ({wine.quantity})")

    return issues


def validate_mapped_records(rows: list[MappedWineRow]) -> list[str]:
    issues: list[str] = []
    for row in rows:
        issues.extend(_mapped_row_integrity_issues(row, f"input row {row.row_number}"))
    return issues


def assert_mapped_records_valid(rows: list[MappedWineRow]) -> None:
    issues = validate_mapped_records(rows)
    if not issues:
        return
    preview = "; ".join(issues[:5])
    if len(issues) > 5:
        preview += f"; ... {len(issues) - 5} more"
    raise ValueError(f"Mapped rows appear corrupted or column-shifted: {preview}")


def validate_canonical_file(path: str | Path) -> bool:
    """
    Validate canonical file exists, is readable, and contains valid wine records.
    
    Args:
        path: Path to canonical CSV file
        
    Returns:
        True if valid
        
    Raises:
        FileNotFoundError: File doesn't exist
        ValueError: File is empty, unreadable, or contains no valid wines
    """
    p = Path(path)

    if not p.exists():
        logger.error(f"Canonical file not found: {path}")
        raise FileNotFoundError(f"Canonical file not found: {path}")

    if p.stat().st_size == 0:
        logger.error(f"Canonical file is empty: {path}")
        raise ValueError(f"Canonical file is empty: {path}")

    logger.info(f"Validating canonical file: {path}")

    try:
        wines = load_canonical_wines(path)
        if not wines:
            logger.error(f"Canonical file loaded but contains no valid wine records: {path}")
            raise ValueError(f"Canonical file contains no valid wine records: {path}")

        issues = validate_canonical_records(wines)
        if issues:
            preview = "; ".join(issues[:5])
            if len(issues) > 5:
                preview += f"; ... {len(issues) - 5} more"
            raise ValueError(f"Canonical file appears corrupted or column-shifted: {preview}")

        logger.info(f"✓ Canonical file valid: {len(wines)} wines loaded")
        return True

    except Exception as e:
        logger.error(f"Invalid canonical file format: {e}")
        raise ValueError(f"Failed to parse canonical file: {e}")


def validate_input_file(path: str | Path) -> bool:
    """
    Validate input file exists and is readable.
    
    Args:
        path: Path to input file
        
    Returns:
        True if valid
        
    Raises:
        FileNotFoundError: File doesn't exist
        ValueError: File is empty or unreadable
    """
    p = Path(path)

    if not p.exists():
        logger.error(f"Input file not found: {path}")
        raise FileNotFoundError(f"Input file not found: {path}")

    if p.stat().st_size == 0:
        logger.error(f"Input file is empty: {path}")
        raise ValueError(f"Input file is empty: {path}")

    logger.info(f"✓ Input file valid: {p.stat().st_size} bytes")
    return True


def validate_schema_mapping(
    mapping: dict[str, str],
    headers: list[str],
) -> dict[str, str]:
    """
    Validate that schema mapping has acceptable quality.
    
    Args:
        mapping: Inferred schema mapping
        headers: Original CSV headers
        
    Returns:
        The mapping if valid
        
    Raises:
        ValueError: Mapping is inadequate
    """
    if not mapping:
        logger.warning(
            f"No schema mapping found. Headers: {headers}. "
            "Consider providing a manual mapping YAML file."
        )
        raise ValueError(f"No schema mapping found in headers: {headers}")

    essential_fields = {"producer", "name", "vintage"}
    found = set(mapping.keys()) & essential_fields

    if len(found) < 2:
        logger.warning(
            f"Missing essential wine fields. Only found: {found}. "
            f"Mapping: {mapping}"
        )
        raise ValueError(
            f"Missing essential fields. Only found: {found}. "
            "Need at least producer, name, or vintage."
        )

    logger.info(f"✓ Schema mapping valid: {len(mapping)} fields mapped")
    logger.debug(f"Mapping: {mapping}")
    return mapping


def validate_row_has_data(row: MappedWineRow) -> bool:
    """
    Check if row has meaningful wine fields (not just metadata).
    
    Args:
        row: MappedWineRow to validate
        
    Returns:
        True if row has at least one wine field
    """
    wine_fields = [
        row.producer,
        row.name,
        row.vintage,
        row.region,
        row.appellation,
        row.varietal,
    ]
    has_data = any(field for field in wine_fields)

    if not has_data:
        logger.debug(f"Row {row.row_number}: No meaningful wine data (all fields empty)")

    return has_data


def filter_empty_rows(rows: list[MappedWineRow]) -> tuple[list[MappedWineRow], int]:
    """
    Filter out rows with no meaningful wine data.
    
    Args:
        rows: List of mapped rows
        
    Returns:
        Tuple of (filtered_rows, count_removed)
    """
    valid_rows = [r for r in rows if validate_row_has_data(r)]
    removed = len(rows) - len(valid_rows)

    if removed > 0:
        logger.warning(
            f"Filtered out {removed}/{len(rows)} rows with no meaningful wine data"
        )

    return valid_rows, removed


def log_pipeline_start(
    input_path: str,
    out_dir: str,
    ct_cache: str | None = None,
) -> None:
    """Log pipeline initialization."""
    logger.info("=" * 70)
    logger.info("Starting wine-importer pipeline")
    logger.info("=" * 70)
    logger.info(f"Input: {input_path}")
    logger.info(f"Resolution cache: {ct_cache}")
    logger.info(f"Output: {out_dir}")


def log_stage_start(stage_num: int, stage_name: str) -> None:
    """Log stage transition."""
    logger.info(f"\n[Stage {stage_num}] {stage_name}...")


def log_stage_complete(stage_num: int, row_count: int) -> None:
    """Log stage completion."""
    logger.info(f"[Stage {stage_num}] ✓ Complete ({row_count} rows)")


def configure_logging(level: str = "INFO") -> None:
    """
    Configure logging for wine-importer.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    logger_root = logging.getLogger("wine_importer")
    if not logger_root.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger_root.addHandler(handler)
    logger_root.setLevel(level)
