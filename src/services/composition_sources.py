"""Canonical Composition Source Snapshot storage and replay helpers."""

import hashlib
import re
from dataclasses import dataclass
from uuid import UUID

from src.services.media_service import MediaService


_VIDEO_SRC = re.compile(r'(<video\b[^>]*?\bsrc=")[^"]+("[^>]*>)', re.IGNORECASE)
_AUDIO_SRC = re.compile(r'(<audio\b[^>]*?\bsrc=")[^"]+("[^>]*>)', re.IGNORECASE)
_ASSET_SRC = re.compile(r'asset://([0-9a-fA-F-]{36})')


@dataclass(frozen=True)
class CompositionSource:
    canonical_html: str
    input_asset_ids: list[str]


def canonicalize_html(html: str, video_asset_ids: list[str], audio_asset_id: str | None) -> CompositionSource:
    """Replace transient URLs with durable Media Asset references in DOM order."""
    video_index = 0

    def video(match: re.Match) -> str:
        nonlocal video_index
        if video_index >= len(video_asset_ids):
            raise ValueError("composition HTML has more video sources than input Media Assets")
        asset_id = video_asset_ids[video_index]
        video_index += 1
        return f'{match.group(1)}asset://{asset_id}{match.group(2)}'

    canonical = _VIDEO_SRC.sub(video, html)
    if video_index != len(video_asset_ids):
        raise ValueError("composition input Media Assets have no matching video source")
    if audio_asset_id:
        canonical, count = _AUDIO_SRC.subn(
            lambda match: f'{match.group(1)}asset://{audio_asset_id}{match.group(2)}', canonical, count=1
        )
        if count != 1:
            raise ValueError("composition HTML has no audio source for its audio Media Asset")
    if "X-Amz-Signature" in canonical or "X-Amz-Credential" in canonical:
        raise ValueError("canonical composition source must not retain Media Access URLs")
    return CompositionSource(canonical_html=canonical, input_asset_ids=video_asset_ids + ([audio_asset_id] if audio_asset_id else []))


async def materialize_html(canonical_html: str, media: MediaService, owner_user_id: UUID) -> str:
    """Resolve stable asset references only for this authorized render/preview request."""
    asset_ids = [UUID(value) for value in _ASSET_SRC.findall(canonical_html)]
    urls = {str(asset_id): await media.access_url(asset_id, owner_user_id) for asset_id in set(asset_ids)}
    return _ASSET_SRC.sub(lambda match: urls[match.group(1)], canonical_html)


def html_checksum(canonical_html: str) -> str:
    return hashlib.sha256(canonical_html.encode("utf-8")).hexdigest()
