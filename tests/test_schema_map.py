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


def test_infer_schema_mapping_uses_column_profiles_for_generic_headers() -> None:
    headers = ["column_1", "column_2", "column_3", "column_4"]
    profiles = {
        "column_1": {"best_field": "producer", "confidence": 0.7, "text_score": 0.7},
        "column_2": {"best_field": "vintage", "confidence": 1.0, "text_score": 0.0},
        "column_3": {"best_field": "name", "confidence": 0.7, "text_score": 0.7},
        "column_4": {"best_field": "quantity", "confidence": 1.0, "text_score": 0.0},
    }

    mapping = infer_schema_mapping(headers, column_profiles=profiles)

    assert mapping["producer"] == "column_1"
    assert mapping["vintage"] == "column_2"
    assert mapping["name"] == "column_3"
    assert mapping["quantity"] == "column_4"
