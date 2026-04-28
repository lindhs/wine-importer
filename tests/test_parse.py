from pathlib import Path

import pandas as pd

from wine_importer.parse import read_input_file


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


def test_read_input_file_excel_default_sheet(tmp_path: Path) -> None:
    path = tmp_path / "sample_input.xlsx"
    df = pd.DataFrame({"producer": ["Chateau"], "name": ["Test"], "vintage": ["2020"]})
    df.to_excel(path, index=False, sheet_name="Sheet1", engine="openpyxl")

    result = read_input_file(path)

    assert list(result.columns) == ["producer", "name", "vintage"]
    assert result.iloc[0]["producer"] == "Chateau"
    assert result.iloc[0]["name"] == "Test"
    assert result.iloc[0]["vintage"] == "2020"
