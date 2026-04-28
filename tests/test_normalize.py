from wine_importer.normalize import normalize_text, normalize_mapped_rows
from wine_importer.models import MappedWineRow


def test_normalize_text_rules_apply():
    assert normalize_text("Ch. Cab-Sauv 750ml") == "chateau cabernet sauvignon 750 ml"
    assert normalize_text("St. Emilion") == "saint emilion"
    assert normalize_text("Paulliac") == "pauillac"
    assert normalize_text("Maraux") == "margaux"


def test_normalize_mapped_rows_populates_comparison_fields():
    row = MappedWineRow(
        row_number=1,
        producer="Ch. Margaux",
        name="Ch. Margaux Grand Vin",
        vintage="2015",
        region="Bordeaux",
        appellation="Medoc",
        varietal="Cab-Sauv",
        quantity=2,
        size="750ml",
        location="Cellar A",
        bin="1A",
        notes="Excellent vintage",
        original={"Producer": "Ch. Margaux"},
    )
    normalized = normalize_mapped_rows([row])[0]
    assert normalized.normalized_producer == "chateau margaux"
    assert normalized.normalized_name == "chateau margaux grand vin"
    assert normalized.normalized_varietal == "cabernet sauvignon"
    assert normalized.normalized_size == "750 ml"
