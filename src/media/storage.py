from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from urllib.parse import quote


class StorageError(RuntimeError):
    """Base error raised by object-storage adapters."""


class ObjectNotFound(StorageError):
    """Raised when an object does not exist."""


@runtime_checkable
class ObjectStorage(Protocol):
    async def upload(
        self,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str,
    ) -> None: ...

    async def download(self, bucket: str, object_key: str) -> bytes: ...

    async def exists(self, bucket: str, object_key: str) -> bool: ...

    async def delete(self, bucket: str, object_key: str) -> None: ...

    async def presign_get(
        self,
        bucket: str,
        object_key: str,
        expires_seconds: int,
    ) -> str: ...


@dataclass
class InMemoryObjectStorage:
    """Small private-object adapter for tests and local service composition."""

    objects: dict[tuple[str, str], tuple[bytes, str]] = field(default_factory=dict)

    async def upload(
        self,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str,
    ) -> None:
        self.objects[(bucket, object_key)] = (bytes(data), content_type)

    async def download(self, bucket: str, object_key: str) -> bytes:
        try:
            return self.objects[(bucket, object_key)][0]
        except KeyError as exc:
            raise ObjectNotFound(f"{bucket}/{object_key}") from exc

    async def exists(self, bucket: str, object_key: str) -> bool:
        return (bucket, object_key) in self.objects

    async def delete(self, bucket: str, object_key: str) -> None:
        self.objects.pop((bucket, object_key), None)

    async def presign_get(
        self,
        bucket: str,
        object_key: str,
        expires_seconds: int,
    ) -> str:
        if not await self.exists(bucket, object_key):
            raise ObjectNotFound(f"{bucket}/{object_key}")
        return (
            f"memory://{quote(bucket, safe='')}/{quote(object_key, safe='/')}"
            f"?expires={expires_seconds}"
        )


def memory_storage() -> InMemoryObjectStorage:
    return InMemoryObjectStorage()
