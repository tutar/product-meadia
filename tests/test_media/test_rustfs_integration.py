import os
import uuid

import pytest

from src.config import Settings
from src.media.rustfs import create_rustfs_storage


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_RUSTFS_INTEGRATION") != "1",
        reason="set RUN_RUSTFS_INTEGRATION=1 to test configured RustFS",
    ),
]


@pytest.mark.asyncio
async def test_private_rustfs_object_round_trip():
    settings = Settings()
    storage = create_rustfs_storage(settings)
    object_key = f"integration/{uuid.uuid4()}.txt"

    await storage.upload(
        settings.media_bucket,
        object_key,
        b"private-media",
        "text/plain",
    )
    try:
        assert await storage.download(settings.media_bucket, object_key) == b"private-media"
        access_url = await storage.presign_get(
            settings.media_bucket,
            object_key,
            settings.media_access_ttl_seconds,
        )
        assert object_key in access_url
    finally:
        await storage.delete(settings.media_bucket, object_key)
