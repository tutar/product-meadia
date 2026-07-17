from io import BytesIO
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.config import Settings
from src.media.rustfs import RustFSObjectStorage, create_rustfs_storage
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


@pytest.mark.asyncio
async def test_rustfs_adapter_creates_missing_bucket_then_retries():
    client = MagicMock()
    missing = MissingObject()
    missing.response = {"Error": {"Code": "NoSuchBucket"}}
    client.put_object.side_effect = [missing, None]
    storage = RustFSObjectStorage(client)

    await storage.upload("media", "users/u/image.png", b"stored", "image/png")

    client.create_bucket.assert_called_once_with(Bucket="media")
    assert client.put_object.call_count == 2


def test_rustfs_storage_forces_sigv4_presigned_urls(monkeypatch):
    boto3 = SimpleNamespace(client=MagicMock(return_value=MagicMock()))
    monkeypatch.setitem(sys.modules, "boto3", boto3)

    create_rustfs_storage(Settings())

    config = boto3.client.call_args.kwargs["config"]
    assert config.signature_version == "s3v4"
