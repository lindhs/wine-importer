import pandas as pd

from wine_importer.table_detect import detect_table_regions, extract_table_regions


def _matrix(rows: list[list[str]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_blank_row_inside_data_region_does_not_truncate_table() -> None:
    df = _matrix(
        [
            ["Producer", "Name", "Vintage", "Quantity"],
            ["Ridge", "Lytton Springs", "1993", "2"],
            ["", "", "", ""],
            ["Shafer", "Hillside Select", "1990", "1"],
        ]
    )

    regions = detect_table_regions(df)
    structured = extract_table_regions(df, regions)

    assert len(regions) == 1
    assert len(structured.dataframe) == 2
    assert structured.dataframe.iloc[1]["Producer"] == "Shafer"
    assert structured.source_row_numbers == [2, 4]


def test_merged_header_cell_becomes_placeholder_column_and_keeps_data() -> None:
    # Excel merged header cells export as empty strings in the spilled columns.
    df = _matrix(
        [
            ["Producer", "Name", "", "Quantity"],
            ["Ridge", "Lytton Springs", "Dry Creek", "2"],
        ]
    )

    regions = detect_table_regions(df)
    structured = extract_table_regions(df, regions)

    assert len(regions) == 1
    assert regions[0].detected_headers == ["Producer", "Name", "column_3", "Quantity"]
    assert structured.dataframe.iloc[0]["column_3"] == "Dry Creek"


def test_vertically_merged_first_column_keeps_continuation_rows() -> None:
    # A vertically merged "Region" cell leaves the cell empty on later rows.
    df = _matrix(
        [
            ["Region", "Producer", "Name", "Vintage"],
            ["Sonoma", "Ridge", "Lytton Springs", "1993"],
            ["", "Seghesio", "Old Vine Zinfandel", "2018"],
        ]
    )

    regions = detect_table_regions(df)
    structured = extract_table_regions(df, regions)

    assert len(structured.dataframe) == 2
    assert structured.dataframe.iloc[1]["Region"] == ""
    assert structured.dataframe.iloc[1]["Producer"] == "Seghesio"


def test_headerless_data_matrix_yields_no_regions() -> None:
    df = _matrix(
        [
            ["Ridge", "Lytton Springs", "1993", "2"],
            ["Shafer", "Hillside Select", "1990", "1"],
        ]
    )

    assert detect_table_regions(df) == []


def test_repeated_header_row_inside_data_merges_into_one_table() -> None:
    # Pasting two table chunks together repeats the header mid-file.
    df = _matrix(
        [
            ["Producer", "Name", "Vintage"],
            ["Ridge", "Lytton Springs", "1993"],
            ["Producer", "Name", "Vintage"],
            ["Raveneau", "Chablis", "2017"],
        ]
    )

    regions = detect_table_regions(df)
    structured = extract_table_regions(df, regions)

    assert len(regions) == 2
    assert len(structured.selected_regions) == 2
    assert len(structured.dataframe) == 2
    assert list(structured.dataframe["Producer"]) == ["Ridge", "Raveneau"]
    assert structured.table_indices == [1, 2]
