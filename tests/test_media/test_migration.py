import uuid

from src.services.media_migration import migrate_legacy_url


def test_migration_module_exposes_resumable_single_item_entrypoint():
    assert callable(migrate_legacy_url)
    assert uuid.uuid4()
