from pathlib import Path

import yaml

from src.models.generated_image import GeneratedImage
from src.models.product import Product
from src.models.task import VideoTask


ROOT = Path(__file__).parents[2]


def test_media_asset_contract_replaces_persistent_urls():
    ddl = (ROOT / "db/schema.sql").read_text()
    api = yaml.safe_load((ROOT / "api/openapi.yaml").read_text())

    assert "CREATE TABLE media_assets" in ddl
    assert "main_image_asset_id" in ddl
    assert "result_video_asset_id" in ddl
    assert "asset_id" in ddl
    assert "/media/{asset_id}/access" in api["paths"]
    assert "MediaAsset" in api["components"]["schemas"]

    assert hasattr(Product, "main_image_asset_id")
    assert hasattr(GeneratedImage, "asset_id")
    assert hasattr(VideoTask, "result_video_asset_id")
