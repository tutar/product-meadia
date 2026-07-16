import uuid

import pytest

from src.media.storage import memory_storage
from src.services.media_service import MediaService


@pytest.mark.asyncio
async def test_remote_result_is_stored_as_asset_metadata():
    class Session:
        def add(self, value): self.value = value
        async def flush(self): self.value.id = uuid.uuid4()
        async def scalar(self, query): return None

    async def fetch(url):
        assert url == "https://provider/result"
        return b"result", "video/mp4"

    asset = await MediaService(Session(), memory_storage()).create_from_remote(
        owner_user_id=uuid.uuid4(),
        category="final_video",
        source_url="https://provider/result",
        filename="result.mp4",
        fetch=fetch,
    )
    assert asset.content_type == "video/mp4"
    assert asset.size_bytes == 6
