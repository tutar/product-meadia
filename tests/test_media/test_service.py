import hashlib
import uuid

from src.services.media_service import MediaService, build_object_key


def test_media_service_uses_user_scoped_object_keys_and_sha256():
    user_id = uuid.uuid4()
    key = build_object_key(user_id, "product-image", "image.png")
    assert key.startswith(f"users/{user_id}/product-image/")
    assert key.endswith(".png")
    assert MediaService.checksum(b"hello") == hashlib.sha256(b"hello").hexdigest()
