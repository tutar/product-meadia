from io import BytesIO
from unittest.mock import MagicMock

import pytest

from src.media.rustfs import RustFSObjectStorage
from src.media.storage import ObjectNotFound, StorageError


class MissingObject(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


@pytest.mark.asyncio
async def test_rustfs_adapter_maps_s3_operations():
    client = MagicMock()
    client.get_object.return_value = {"Body": BytesIO(b"stored")}
    client.generate_presigned_url.return_value = "https://storage/private"
    storage = RustFSObjectStorage(client)

    await storage.upload("media", "users/u/image.png", b"stored", "image/png")
    assert await storage.download("media", "users/u/image.png") == b"stored"
    assert await storage.exists("media", "users/u/image.png")
    assert await storage.presign_get("media", "users/u/image.png", 3600) == (
        "https://storage/private"
    )
    await storage.delete("media", "users/u/image.png")

    client.put_object.assert_called_once_with(
        Bucket="media",
        Key="users/u/image.png",
        Body=b"stored",
        ContentType="image/png",
    )
    client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "media", "Key": "users/u/image.png"},
        ExpiresIn=3600,
    )


@pytest.mark.asyncio
async def test_rustfs_adapter_maps_missing_and_storage_failures():
    client = MagicMock()
    storage = RustFSObjectStorage(client)

    client.head_object.side_effect = MissingObject()
    assert not await storage.exists("media", "missing")

    client.get_object.side_effect = MissingObject()
    with pytest.raises(ObjectNotFound):
        await storage.download("media", "missing")

    client.put_object.side_effect = RuntimeError("offline")
    with pytest.raises(StorageError):
        await storage.upload("media", "file", b"x", "text/plain")
