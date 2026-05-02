from pathlib import Path

import pandas as pd

from wine_importer.parse import (
    read_ingested_input_file,
    read_input_file,
    read_structured_input_file,
)


def test_read_input_file_tsv(tmp_path: Path) -> None:
    path = tmp_path / "sample_input.tsv"
    path.write_text("producer\tname\tvintage\nChateau\tTest\t2020\n", encoding="utf-8")

    df = read_input_file(path)

    assert list(df.columns) == ["producer", "name", "vintage"]
    assert df.iloc[0]["producer"] == "Chateau"
    assert df.iloc[0]["name"] == "Test"
    assert df.iloc[0]["vintage"] == "2020"


def test_read_input_file_with_custom_delimiter(tmp_path: Path) -> None:
    path = tmp_path / "sample_input.txt"
    path.write_text("producer|name|vintage\nFoo|Bar|2021\n", encoding="utf-8")

    df = read_input_file(path, delimiter="|")

    assert list(df.columns) == ["producer", "name", "vintage"]
    assert df.iloc[0]["producer"] == "Foo"
    assert df.iloc[0]["name"] == "Bar"
    assert df.iloc[0]["vintage"] == "2021"


def test_read_input_file_detects_semicolon_delimiter(tmp_path: Path) -> None:
    path = tmp_path / "sample_input.csv"
    path.write_text("producer;name;vintage\nAlpha;Beta;2019\n", encoding="utf-8")

    df = read_input_file(path)

    assert list(df.columns) == ["producer", "name", "vintage"]
    assert df.iloc[0]["producer"] == "Alpha"
    assert df.iloc[0]["name"] == "Beta"
    assert df.iloc[0]["vintage"] == "2019"


def test_read_input_file_unknown_extension_with_ai(tmp_path: Path) -> None:
    path = tmp_path / "sample_input.foo"
    path.write_text("This is not a normal table format.", encoding="utf-8")

    df = read_input_file(path, use_ai=True)

    assert list(df.columns) == ["raw_text"]
    assert "not a normal table" in df.iloc[0]["raw_text"]


def test_read_input_file_unknown_extension_with_ai_parses_text_table(tmp_path: Path) -> None:
    path = tmp_path / "sample_input.foo"
    path.write_text("producer|name|vintage\nFoo|Bar|2021\n", encoding="utf-8")

    df = read_input_file(path, use_ai=True)

    assert list(df.columns) == ["producer", "name", "vintage"]
    assert df.iloc[0]["producer"] == "Foo"
    assert df.iloc[0]["name"] == "Bar"
    assert df.iloc[0]["vintage"] == "2021"


def test_read_input_file_excel_default_sheet(tmp_path: Path) -> None:
    path = tmp_path / "sample_input.xlsx"
    df = pd.DataFrame({"producer": ["Chateau"], "name": ["Test"], "vintage": ["2020"]})
    df.to_excel(path, index=False, sheet_name="Sheet1", engine="openpyxl")

    result = read_input_file(path)

    assert list(result.columns) == ["producer", "name", "vintage"]
    assert result.iloc[0]["producer"] == "Chateau"
    assert result.iloc[0]["name"] == "Test"
    assert result.iloc[0]["vintage"] == "2020"


def test_read_input_file_detects_header_after_preamble(tmp_path: Path) -> None:
    path = tmp_path / "preamble.csv"
    path.write_text(
        "My Cellar Inventory\n"
        "Updated 2024\n"
        "\n"
        "Producer,Name,Vintage,Quantity\n"
        "Ridge,Lytton Springs,1993,2\n",
        encoding="utf-8",
    )

    df = read_input_file(path)

    assert list(df.columns) == ["Producer", "Name", "Vintage", "Quantity"]
    assert len(df) == 1
    assert df.iloc[0]["Producer"] == "Ridge"


def test_read_input_file_detects_header_after_blank_rows(tmp_path: Path) -> None:
    path = tmp_path / "blank_rows.csv"
    path.write_text(
        "\n\nProducer,Name,Vintage,Quantity\nShafer,Hillside Select,1990,1\n",
        encoding="utf-8",
    )

    df = read_input_file(path)

    assert list(df.columns) == ["Producer", "Name", "Vintage", "Quantity"]
    assert df.iloc[0]["Name"] == "Hillside Select"


def test_read_input_file_detects_excel_header_after_title(tmp_path: Path) -> None:
    path = tmp_path / "title.xlsx"
    df = pd.DataFrame(
        [
            ["My Collection", "", "", ""],
            ["", "", "", ""],
            ["Producer", "Name", "Vintage", "Quantity"],
            ["Ridge", "Lytton Springs", "1993", "2"],
        ]
    )
    df.to_excel(path, index=False, header=False, sheet_name="Sheet1", engine="openpyxl")

    result = read_input_file(path)

    assert list(result.columns) == ["Producer", "Name", "Vintage", "Quantity"]
    assert result.iloc[0]["Producer"] == "Ridge"


def test_read_ingested_input_file_can_scan_all_excel_sheets(tmp_path: Path) -> None:
    path = tmp_path / "multi_sheet.xlsx"
    red = pd.DataFrame([["Producer", "Name", "Vintage"], ["Ridge", "Lytton", "1993"]])
    white = pd.DataFrame([["Producer", "Name", "Vintage"], ["Raveneau", "Chablis", "2017"]])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        red.to_excel(writer, index=False, header=False, sheet_name="Red")
        white.to_excel(writer, index=False, header=False, sheet_name="White")

    ingested = read_ingested_input_file(path, all_sheets=True)

    assert len(ingested.dataframe) == 2
    assert set(ingested.dataframe["Producer"]) == {"Ridge", "Raveneau"}
    assert {region.sheet_name for region in ingested.detected_regions} == {"Red", "White"}


def test_read_input_file_combines_compatible_tables(tmp_path: Path) -> None:
    path = tmp_path / "multiple_tables.csv"
    path.write_text(
        "Red Wines\n"
        "Producer,Name,Vintage\n"
        "Ridge,Lytton Springs,1993\n"
        "\n"
        "White Wines\n"
        "Producer,Name,Vintage\n"
        "Raveneau,Chablis,2017\n",
        encoding="utf-8",
    )

    structured = read_structured_input_file(path)

    assert len(structured.dataframe) == 2
    assert len(structured.selected_regions) == 2
    assert structured.dataframe.iloc[1]["Producer"] == "Raveneau"


def test_read_input_file_skips_incompatible_table(tmp_path: Path) -> None:
    path = tmp_path / "incompatible_tables.csv"
    path.write_text(
        "Producer,Name,Vintage\n"
        "Ridge,Lytton Springs,1993\n"
        "\n"
        "Accessories\n"
        "Item,Count,Price\n"
        "Corkscrew,1,10\n",
        encoding="utf-8",
    )

    structured = read_structured_input_file(path)

    assert len(structured.dataframe) == 1
    assert structured.dataframe.iloc[0]["Producer"] == "Ridge"
    assert len(structured.skipped_regions) == 1
    assert structured.skipped_regions[0].skip_reason == "incompatible headers"


def test_read_input_file_without_header_uses_generic_columns(tmp_path: Path) -> None:
    path = tmp_path / "no_header.csv"
    path.write_text(
        "Ridge,1993,Lytton Springs,2\n"
        "Shafer,1990,Hillside Select,1\n",
        encoding="utf-8",
    )

    structured = read_structured_input_file(path)

    assert list(structured.dataframe.columns) == ["column_1", "column_2", "column_3", "column_4"]
    assert structured.dataframe.iloc[0]["column_1"] == "Ridge"
    assert "no clear header row detected" in structured.warnings[0]


def test_read_input_file_detects_spreadsheetman_inventory() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "data" / "raw" / "testinv1.csv"

    structured = read_structured_input_file(path)

    assert len(structured.dataframe) == 195
    assert structured.skipped_regions == []
    assert structured.selected_regions[0].header_row_index == 2
    assert structured.selected_regions[0].data_start_row_index == 3
    assert list(structured.dataframe.columns[:5]) == [
        "column_1",
        "Producer",
        "Type / Varietal",
        "Vintage",
        "Name",
    ]
    assert all(not str(column).startswith("Unnamed") for column in structured.dataframe.columns)
    assert structured.dataframe.iloc[0]["Producer"] == "A. Rafanelli"

    ingested = read_ingested_input_file(path)
    assert len(ingested.quarantine_items) == 1
    assert ingested.quarantine_items[0].row_number == 151


def test_read_ingested_input_file_parses_line_based_text_inventory(tmp_path: Path) -> None:
    path = tmp_path / "inventory.txt"
    path.write_text(
        "Ridge Lytton Springs 1993 - 2 bottles\n"
        "This is just a note\n"
        "Shafer Hillside Select 1990 - cellar B\n",
        encoding="utf-8",
    )

    ingested = read_ingested_input_file(path)

    assert list(ingested.dataframe.columns) == [
        "producer",
        "name",
        "vintage",
        "quantity",
        "size",
        "location",
        "raw_text",
    ]
    assert len(ingested.dataframe) == 2
    assert ingested.dataframe.iloc[0]["producer"] == "Ridge"
    assert ingested.dataframe.iloc[0]["vintage"] == "1993"
    assert ingested.dataframe.iloc[0]["quantity"] == "2"
    assert len(ingested.quarantine_items) == 1
    assert ingested.quarantine_items[0].reason == "line did not contain enough wine evidence"


def test_read_ingested_input_file_quarantines_pdf_without_dependency(tmp_path: Path) -> None:
    path = tmp_path / "inventory.pdf"
    path.write_text("not really a pdf", encoding="utf-8")

    ingested = read_ingested_input_file(path)

    assert ingested.dataframe.empty
    assert len(ingested.quarantine_items) == 1
    assert "PDF text extraction" in ingested.quarantine_items[0].reason


def test_read_ingested_input_file_quarantines_image_without_ocr(tmp_path: Path) -> None:
    path = tmp_path / "inventory.png"
    path.write_bytes(b"not really an image")

    ingested = read_ingested_input_file(path)

    assert ingested.dataframe.empty
    assert len(ingested.quarantine_items) == 1
    assert "OCR disabled" in ingested.quarantine_items[0].reason
