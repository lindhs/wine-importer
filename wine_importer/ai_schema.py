"""AI-powered schema mapping using OpenAI for intelligent header inference."""

import json
import logging
from typing import Any

from .ai_runtime import create_json_completion
from .config import (
    AI_SCORE_CONFIDENCE_WEIGHT,
    AI_SCORE_FUZZY_WEIGHT,
    is_ai_scoring_candidate,
)

logger = logging.getLogger(__name__)

# Standard wine fields
WINE_FIELDS = [
    "producer",
    "name",
    "vineyard",
    "vintage",
    "country",
    "region",
    "subregion",
    "appellation",
    "varietal",
    "quantity",
    "size",
    "purchase_date",
    "location",
    "bin",
    "notes",
]


def infer_schema_mapping_with_ai(
    headers: list[str],
    sample_values: dict[str, str] | None = None,
    api_key: str | None = None,
) -> dict[str, str]:
    """
    Use OpenAI to intelligently infer schema mapping from headers.
    
    Handles non-English headers, abbreviations, and domain-specific naming.
    Falls back gracefully if API unavailable.
    
    Args:
        headers: CSV column headers
        sample_values: Optional dict with sample values for each header
        api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
        
    Returns:
        Dict mapping wine field names to CSV headers
    """
    wine_fields_str = ", ".join(WINE_FIELDS)
    sample_str = ""
    if sample_values:
        sample_str = f"\n\nSample values:\n{json.dumps(sample_values, indent=2)}"

    prompt = f"""You are a wine data expert. Given CSV column headers, map them to wine fields.

CSV Headers: {headers}
{sample_str}

Available wine fields: {wine_fields_str}

Your task:
1. Map ONLY headers with clear, high-confidence matches
2. Skip ambiguous or unclear headers
3. Understand domain abbreviations (e.g., "Prod" = producer, "Var" = varietal, "App" = appellation)
4. Handle non-English headers (Spanish, French, Italian, etc.)

Return ONLY a valid JSON object with no other text:
{{"header_name": "wine_field", ...}}

Examples:
- {{"Producer": "producer", "Vintage Year": "vintage", "Grape": "varietal"}}
- {{"Productor": "producer", "Denominación": "appellation", "Año": "vintage"}}

Remember: Return ONLY the JSON object, nothing else."""

    try:
        logger.info("Querying OpenAI for semantic schema mapping...")
        mapping = create_json_completion(
            prompt,
            api_key=api_key,
            max_output_tokens=500,
        )

        # Validate mapping
        if not isinstance(mapping, dict):
            logger.warning(f"OpenAI mapping is not a dict: {mapping}")
            return {}

        # Ensure all values are valid wine fields
        valid_mapping = {}
        for header, field in mapping.items():
            if field in WINE_FIELDS:
                valid_mapping[field] = header
                logger.debug(f"AI mapping: {header} → {field}")
            else:
                logger.debug(f"AI mapped invalid field '{field}' for header '{header}', skipping")

        logger.info(f"✓ AI schema mapping found {len(valid_mapping)} fields")
        return valid_mapping

    except Exception as e:
        logger.warning(f"OpenAI API call failed: {e}")
        return {}


def score_candidate_with_ai(
    user_producer: str | None,
    user_name: str | None,
    user_vintage: str | None,
    user_region: str | None,
    canonical_producer: str,
    canonical_name: str,
    canonical_vintage: str,
    canonical_region: str,
    fuzzy_score: float,
    api_key: str | None = None,
) -> float:
    """
    Use OpenAI to semantically verify wine matches in ambiguous cases.
    
    Only calls API for scores in the configured ambiguous zone.
    Blends fuzzy matching with semantic understanding.
    
    Args:
        user_producer: User-provided producer
        user_name: User-provided wine name
        user_vintage: User-provided vintage
        user_region: User-provided region
        canonical_producer: Reference producer
        canonical_name: Reference name
        canonical_vintage: Reference vintage
        canonical_region: Reference region
        fuzzy_score: Fuzzy matching score (0-1)
        api_key: OpenAI API key
        
    Returns:
        Blended score (0-1)
    """
    # Only use AI for ambiguous cases
    if not is_ai_scoring_candidate(fuzzy_score):
        return fuzzy_score

    prompt = f"""Are these the same wine? Respond with confidence 0-1.

User input:
  Producer: {user_producer or 'unknown'}
  Name: {user_name or 'unknown'}
  Vintage: {user_vintage or 'unknown'}
  Region: {user_region or 'unknown'}

Canonical reference:
  Producer: {canonical_producer}
  Name: {canonical_name}
  Vintage: {canonical_vintage}
  Region: {canonical_region}

Respond ONLY with JSON: {{"confidence": 0.95}}

Consider:
- Producer/name typos and abbreviations
- Regional synonyms (e.g., Bordeaux = Gironde)
- Vintage variations (e.g., NV vs specific year)
- Name variations (e.g., "Grand Vin" suffix)"""

    try:
        result = create_json_completion(
            prompt,
            api_key=api_key,
            max_output_tokens=100,
        )

        if "confidence" not in result:
            logger.debug(f"Invalid semantic score response: {result}")
            return fuzzy_score

        ai_confidence = float(result["confidence"])
        if not 0 <= ai_confidence <= 1:
            logger.debug(f"Invalid confidence value: {ai_confidence}")
            return fuzzy_score

        blended = (
            AI_SCORE_FUZZY_WEIGHT * fuzzy_score
            + AI_SCORE_CONFIDENCE_WEIGHT * ai_confidence
        )
        logger.debug(
            f"Semantic score: fuzzy={fuzzy_score:.2f}, ai={ai_confidence:.2f}, "
            f"blended={blended:.2f}"
        )
        return blended

    except Exception as e:
        logger.debug(f"Semantic scoring failed: {e}")
        return fuzzy_score


def assess_input_quality_with_ai(
    sample_data: list[dict[str, str]],
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    Quick AI assessment of input data quality before processing.
    
    Args:
        sample_data: List of sample rows (first 3-5)
        api_key: OpenAI API key
        
    Returns:
        Assessment dict with quality metrics and recommendations
    """
    if not sample_data:
        return {"skipped": True, "reason": "No sample data"}

    sample_json = json.dumps(sample_data[:3], indent=2)

    prompt = f"""Analyze this wine data sample for quality issues.

Sample data (first 3 rows):
{sample_json}

Rate on scale 1-10:
- Completeness (how many fields filled)
- Consistency (format consistency, naming patterns)
- Format standards (abbreviations, date formats, etc.)

Flag specific issues:
- Missing critical fields (producer, name, vintage)
- Mangled or corrupted data
- Inconsistent formatting

Suggest ONE preprocessing step.

Respond with JSON:
{{"completeness": 7, "consistency": 6, "standards": 5, "issues": ["..."], "recommendation": "..."}}"""

    try:
        assessment = create_json_completion(
            prompt,
            api_key=api_key,
            max_output_tokens=400,
        )

        logger.info(f"Data quality assessment: {assessment.get('completeness', '?')}/10 completeness")
        if assessment.get("issues"):
            logger.warning(f"Quality issues detected: {assessment['issues']}")
        if assessment.get("recommendation"):
            logger.info(f"Recommendation: {assessment['recommendation']}")

        return assessment

    except Exception as e:
        logger.debug(f"Quality assessment failed: {e}")
        return {"error": str(e)}
