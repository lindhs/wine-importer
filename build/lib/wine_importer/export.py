from pathlib import Path

import pandas as pd


def export_reviewed_matches(reviewed_matches: list[dict], output_path: str | Path) -> None:
    rows = []
    for record in reviewed_matches:
        user_row = record.get("user_row", {})
        notes = record.get("reason", "")

        rows.append(
            {
                "Vintage": user_row.get("vintage", ""),
                "UserWine1": user_row.get("producer", ""),
                "UserWine2": user_row.get("name", ""),
                "Quantity": user_row.get("quantity", ""),
                "BottleSize": user_row.get("size", ""),
                "Location": user_row.get("location", ""),
                "Bin": user_row.get("bin", ""),
                "Notes": notes,
            }
        )
    df = pd.DataFrame(rows)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False)
