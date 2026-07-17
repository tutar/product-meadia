from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def test_openapi_exposes_catalog_contract():
    doc = yaml.safe_load((ROOT / "api/openapi.yaml").read_text())
    assert "/categories" in doc["paths"]
    assert "/products/main-image/generate" in doc["paths"]
    assert "/initialization-status" in doc["paths"]
    assert set(doc["components"]["schemas"]["AttributeType"]["enum"]) == {
        "text",
        "number",
        "single_select",
        "multi_select",
        "boolean",
    }


def test_schema_contains_generic_catalog_and_snapshot():
    ddl = (ROOT / "db/schema.sql").read_text()
    for table in (
        "categories",
        "category_attributes",
        "main_image_candidates",
        "outbox_events",
        "catalog_initializations",
    ):
        assert f"CREATE TABLE {table}" in ddl
    assert "product_snapshot JSONB" in ddl
    assert "video_review" in ddl
    assert "composition_review" in ddl
    assert "top_note" not in ddl
