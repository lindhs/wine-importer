from wine_importer.schema_map import infer_schema_mapping


def test_infer_schema_mapping_handles_cuvee_header() -> None:
    headers = ["Producer", "Cuvée", "Vintage", "Appellation", "Country", "Varietal"]
    mapping = infer_schema_mapping(headers)

    assert mapping["producer"] == "Producer"
    assert mapping["name"] == "Cuvée"
    assert mapping["vintage"] == "Vintage"
    assert mapping["appellation"] == "Appellation"
    assert mapping["country"] == "Country"
    assert mapping["varietal"] == "Varietal"


def test_infer_schema_mapping_handles_cellartracker_style_headers() -> None:
    headers = ["UserWine1", "UserWine2", "BottleSize", "Qty", "Cellar", "Bin"]
    mapping = infer_schema_mapping(headers)

    assert mapping["producer"] == "UserWine1"
    assert mapping["name"] == "UserWine2"
    assert mapping["size"] == "BottleSize"
    assert mapping["quantity"] == "Qty"
    assert mapping["location"] == "Cellar"
    assert mapping["bin"] == "Bin"
