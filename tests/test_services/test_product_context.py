from types import SimpleNamespace
from uuid import uuid4

from src.services.product_context import build_product_snapshot, format_product_context
from src.api.tasks import owned_task
from fastapi import HTTPException
from unittest.mock import AsyncMock
import pytest


def test_snapshot_is_deterministic_and_contains_active_ordered_attributes():
    category = SimpleNamespace(id=uuid4(), name="Cups", template_version=2, attributes=[
        SimpleNamespace(key="weight", label="Weight", type="number", sort_order=2),
        SimpleNamespace(key="color", label="Color", type="single_select", sort_order=1),
    ])
    product = SimpleNamespace(id=uuid4(), name="Cup", description="Ceramic", selling_points=["Strong"], scenarios=["Home"], main_image_asset_id=uuid4(), main_image_source="asset", attributes={"color": "red", "unknown": "x"})
    snapshot = build_product_snapshot(product, category)
    assert snapshot["version"] == 1 and snapshot["category"]["name"] == "Cups"
    assert [item["key"] for item in snapshot["attributes"]] == ["color"]
    assert "Color: red" in format_product_context(snapshot)

    product.name = "Edited"
    product.attributes["color"] = "blue"
    assert snapshot["name"] == "Cup" and snapshot["attributes"][0]["value"] == "red"


def test_snapshot_preserves_ordered_packaging_image_references():
    category = SimpleNamespace(id=uuid4(), name="Cups", template_version=1, attributes=[])
    first, second = uuid4(), uuid4()
    product = SimpleNamespace(
        id=uuid4(), name="Cup", description=None, selling_points=[], scenarios=[],
        main_image_asset_id=uuid4(), main_image_source="asset", attributes={},
        packaging_images=[
            SimpleNamespace(asset_id=second, sort_order=1, source="upload", prompt="side"),
            SimpleNamespace(asset_id=first, sort_order=0, source="ai", prompt="front"),
        ],
    )

    snapshot = build_product_snapshot(product, category)

    assert snapshot["packaging_images"] == [
        {"asset_id": str(first), "sort_order": 0, "source": "ai", "prompt": "front"},
        {"asset_id": str(second), "sort_order": 1, "source": "upload", "prompt": "side"},
    ]


@pytest.mark.asyncio
async def test_owned_task_hides_cross_tenant_task():
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)))
    with pytest.raises(HTTPException) as exc:
        await owned_task(db, SimpleNamespace(id=uuid4()), uuid4())
    assert exc.value.status_code == 404
    assert "video_tasks.user_id" in str(db.execute.call_args.args[0])
