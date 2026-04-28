from pathlib import Path

import pandas as pd


def ai_parse_file(path: str | Path) -> pd.DataFrame:
    """Fallback parser for unsupported or unstructured files.

    This is a scaffold for AI-assisted extraction. For now it returns the
    raw file content as a single-column DataFrame, which can later be replaced
    with a real AI extraction pipeline.
    """
    path = Path(path)
    file_text = path.read_text(encoding="utf-8", errors="ignore")
    return pd.DataFrame([{"raw_text": file_text}])
