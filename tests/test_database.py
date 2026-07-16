import inspect

from src.database import ensure_schema


def test_database_exposes_idempotent_schema_initialization():
    assert inspect.iscoroutinefunction(ensure_schema)
