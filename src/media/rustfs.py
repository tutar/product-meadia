from __future__ import annotations

from typing import Any

from src.config import Settings
from src.media.storage import ObjectNotFound, StorageError


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    error = response.get("Error")
    if not isinstance(error, dict):
        return None
    code = error.get("Code")
    return str(code) if code is not None else None


def _is_not_found(exc: Exception) -> bool:
    return _error_code(exc) in {"404", "NoSuchKey", "NotFound"}


class RustFSObjectStorage:
    """ObjectStorage adapter for RustFS' S3-compatible API."""

    def __init__(self, client: Any):
        self._client = client

    async def upload(
        self,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str,
    ) -> None:
        try:
            self._client.put_object(
                Bucket=bucket,
                Key=object_key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as exc:
            raise StorageError(f"failed to upload {bucket}/{object_key}") from exc

    async def download(self, bucket: str, object_key: str) -> bytes:
        try:
            response = self._client.get_object(
                Bucket=bucket,
                Key=object_key,
            )
            # botocore's StreamingBody performs network I/O in get_object; reading
            # the already-returned body is safe here and avoids executor quirks
            # with file-like test doubles.
            return response["Body"].read()
        except Exception as exc:
            if _is_not_found(exc):
                raise ObjectNotFound(f"{bucket}/{object_key}") from exc
            raise StorageError(f"failed to download {bucket}/{object_key}") from exc

    async def exists(self, bucket: str, object_key: str) -> bool:
        try:
            self._client.head_object(
                Bucket=bucket,
                Key=object_key,
            )
            return True
        except Exception as exc:
            if _is_not_found(exc):
                return False
            raise StorageError(f"failed to inspect {bucket}/{object_key}") from exc

    async def delete(self, bucket: str, object_key: str) -> None:
        try:
            self._client.delete_object(
                Bucket=bucket,
                Key=object_key,
            )
        except Exception as exc:
            raise StorageError(f"failed to delete {bucket}/{object_key}") from exc

    async def presign_get(
        self,
        bucket: str,
        object_key: str,
        expires_seconds: int,
    ) -> str:
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": object_key},
                ExpiresIn=expires_seconds,
            )
        except Exception as exc:
            raise StorageError(f"failed to sign {bucket}/{object_key}") from exc


def create_rustfs_storage(settings: Settings) -> RustFSObjectStorage:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required to connect to RustFS") from exc

    client = boto3.client(
        "s3",
        endpoint_url=settings.rustfs_base_url,
        aws_access_key_id=settings.rustfs_access_key,
        aws_secret_access_key=settings.rustfs_secret_key,
        region_name=settings.rustfs_region,
    )
    return RustFSObjectStorage(client)
