from pathlib import Path

import yaml


def test_openapi_declares_private_model_configuration_and_stage_default_contracts():
    contract = yaml.safe_load(Path("api/openapi.yaml").read_text())

    assert "/provider-model-catalog" in contract["paths"]
    assert "/model-configurations" in contract["paths"]
    assert "/model-configurations/{configuration_id}/verify" in contract["paths"]
    assert "/stage-model-defaults/{stage}" in contract["paths"]
    configuration = contract["components"]["schemas"]["ModelConfiguration"]["properties"]
    assert "credential" not in configuration
    assert {"adapter", "api_base", "model_id", "capabilities", "constraints", "revision", "first_use_eligible"} <= set(configuration)
    create = contract["components"]["schemas"]["ModelConfigurationCreate"]
    assert create["properties"]["credential"]["writeOnly"] is True
    assert create["properties"]["catalog_model_id"]["nullable"] is True
    assert any(
        set(option["required"]) == {"display_name", "adapter", "model_id", "capabilities", "credential"}
        for option in create["anyOf"]
    )


def test_schema_declares_a_user_owned_model_configuration_without_platform_defaults():
    schema = Path("db/schema.sql").read_text()

    configuration = schema.split("CREATE TABLE model_configurations", 1)[1].split("CREATE TABLE stage_model_defaults", 1)[0]
    assert "catalog_model_id UUID REFERENCES" in configuration
    assert "adapter VARCHAR(80) NOT NULL" in configuration
    assert "api_base VARCHAR(1000)" in configuration
    assert "revision INTEGER NOT NULL DEFAULT 1" in configuration
    assert "CHECK (credential_ciphertext IS NOT NULL)" in configuration
