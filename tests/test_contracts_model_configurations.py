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
    assert contract["components"]["schemas"]["ModelConfigurationCreate"]["properties"]["credential"]["writeOnly"] is True
