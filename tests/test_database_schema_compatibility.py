import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_model_configuration_compatibility_adds_fields_to_a_pre_release_database(db_session):
    from src.database import ensure_model_configuration_compatibility

    connection = await db_session.connection()
    for column in ("revision", "constraints", "capabilities", "display_name", "model_id", "api_base", "adapter"):
        await connection.execute(text(f"ALTER TABLE model_configurations DROP COLUMN {column}"))
    await connection.execute(text("""
        ALTER TABLE model_configurations ADD CONSTRAINT legacy_credential_requirement
        CHECK ((uses_platform_default AND credential_ciphertext IS NULL)
            OR (NOT uses_platform_default AND credential_ciphertext IS NOT NULL))
    """))

    await ensure_model_configuration_compatibility(connection)
    columns = (await connection.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'model_configurations'"
    ))).scalars().all()

    assert {"adapter", "api_base", "model_id", "display_name", "capabilities", "constraints", "revision"} <= set(columns)
    constraints = (await connection.execute(text("""
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'model_configurations'::regclass AND contype = 'c'
    """))).scalars().all()
    assert "legacy_credential_requirement" not in constraints
