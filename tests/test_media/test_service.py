import hashlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.media.storage import memory_storage
from src.services.media_service import MediaService, build_object_key


def test_media_service_uses_user_scoped_object_keys_and_sha256():
    user_id = uuid.uuid4()
    key = build_object_key(user_id, "product-image", "image.png")
    assert key.startswith(f"users/{user_id}/product-image/")
    assert key.endswith(".png")
    assert MediaService.checksum(b"hello") == hashlib.sha256(b"hello").hexdigest()


@pytest.mark.asyncio
async def test_media_service_reads_owned_image_as_data_uri():
    storage = memory_storage()
    await storage.upload("media", "product/image.png", b"product", "image/png")
    service = MediaService(None, storage, bucket="media")
    service.get_owned_asset = AsyncMock(return_value=SimpleNamespace(
        bucket="media", object_key="product/image.png", content_type="image/png"
    ))

    value = await service.data_uri(uuid.uuid4(), uuid.uuid4())

    assert value == "data:image/png;base64,cHJvZHVjdA=="
