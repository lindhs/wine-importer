from pathlib import Path

import pytest

from wine_importer.validation import validate_canonical_file


def test_validate_canonical_file_rejects_shifted_identity_columns(tmp_path: Path) -> None:
    path = tmp_path / "canonical.csv"
    path.write_text(
        "producer,name,vintage,region,appellation,varietal,quantity,size,notes\n"
        "2020,France,Canopy,Mentrida,Spanish Grenache,Spanish Grenache,1,750ml,\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="column-shifted"):
        validate_canonical_file(path)


def test_validate_canonical_file_rejects_varietal_shifted_to_size(tmp_path: Path) -> None:
    path = tmp_path / "canonical.csv"
    path.write_text(
        "Producer,Name,Vintage,Country,Region,Appellation,Varietal,Quantity,Bottle Size,Notes\n"
        "Canopy,Tres Patas Garnacha,2018,Spain,Mentrida,Mentrida,750ml,1,,\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="varietal looks like a shifted bottle size"):
        validate_canonical_file(path)


def test_validate_canonical_file_rejects_quantity_shifted_to_appellation(tmp_path: Path) -> None:
    path = tmp_path / "canonical.csv"
    path.write_text(
        "Producer,Name,Vintage,Country,Region,Appellation,Varietal,Quantity,Bottle Size,Notes\n"
        "Canopy,Tres Patas Garnacha,2018,Spain,Mentrida,12,Grenache,1,750ml,\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="appellation looks like a shifted quantity"):
        validate_canonical_file(path)


def test_validate_canonical_file_rejects_wine_name_shifted_to_country(tmp_path: Path) -> None:
    path = tmp_path / "canonical.csv"
    path.write_text(
        "Producer,Name,Vintage,Country,Region,Appellation,Varietal,Quantity,Bottle Size,Notes\n"
        "Canopy,Tres Patas Garnacha,2018,Chateau Margaux,Mentrida,Mentrida,Grenache,1,750ml,\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="country looks like a shifted wine name"):
        validate_canonical_file(path)
