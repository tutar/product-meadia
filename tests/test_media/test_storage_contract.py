import pytest

from src.media.storage import ObjectNotFound, memory_storage


@pytest.mark.asyncio
async def test_private_object_storage_round_trip():
    storage = memory_storage()
    await storage.upload("product-media", "users/u/file.txt", b"private", "text/plain")
    assert await storage.exists("product-media", "users/u/file.txt")
    assert await storage.download("product-media", "users/u/file.txt") == b"private"
    assert "users/u/file.txt" in await storage.presign_get("product-media", "users/u/file.txt", 3600)
    await storage.delete("product-media", "users/u/file.txt")
    with pytest.raises(ObjectNotFound):
        await storage.download("product-media", "users/u/file.txt")
