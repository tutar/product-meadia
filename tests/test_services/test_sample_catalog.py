from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.services.outbox import record_event
from src.services.sample_catalog import SAMPLE_CATEGORIES, SAMPLE_VERSION, SampleCatalogInitializer
from src.auth.routes import persist_registered_user


def test_samples_are_versioned_stable_and_cover_three_domains():
    assert SAMPLE_VERSION >= 1
    assert {item["key"] for item in SAMPLE_CATEGORIES} >= {
        "sample-perfume", "sample-electronics", "sample-food"
    }
    assert all("main_image_url" not in item["products"][0] for item in SAMPLE_CATEGORIES)


@pytest.mark.asyncio
async def test_record_event_adds_one_user_registered_event():
    db = SimpleNamespace(add=Mock())
    user_id = uuid4()
    event = await record_event(db, "user.registered", user_id, {"user_id": str(user_id)})
    assert event.event_type == "user.registered" and event.payload["user_id"] == str(user_id)
    db.add.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_initializer_returns_completed_existing_version_without_duplicates():
    existing = SimpleNamespace(status="completed", attempts=1)
    result = SimpleNamespace(scalar_one_or_none=lambda: existing)
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    assert await SampleCatalogInitializer().initialize(db, uuid4(), SAMPLE_VERSION) is existing
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_registration_helper_records_event_before_single_commit(monkeypatch):
    calls = []
    db = SimpleNamespace(
        add=Mock(side_effect=lambda value: calls.append("user")),
        flush=AsyncMock(side_effect=lambda: calls.append("flush")),
        commit=AsyncMock(side_effect=lambda: calls.append("commit")),
        refresh=AsyncMock(),
    )
    event = AsyncMock(side_effect=lambda *args: calls.append("event"))
    monkeypatch.setattr("src.auth.routes.record_event", event)
    user = SimpleNamespace(id=uuid4())
    assert await persist_registered_user(db, user) is user
    event.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert calls.index("event") < calls.index("commit")
