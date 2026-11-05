import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, inspect, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.base import Base

APP_TABLES = {"schools", "users", "goals", "accommodations", "worksheets"}


def _table_names(url: str) -> set[str]:
    async def read() -> set[str]:
        engine = create_async_engine(url, poolclass=pool.NullPool)
        async with engine.connect() as connection:
            names = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        await engine.dispose()
        return set(names)

    return asyncio.run(read())


def _database_check_constraints(url: str) -> set[tuple[str, str]]:
    def read_sync(connection: Connection) -> set[tuple[str, str]]:
        inspector = inspect(connection)
        return {
            (table, str(check["name"]))
            for table in Base.metadata.tables
            for check in inspector.get_check_constraints(table)
        }

    async def read() -> set[tuple[str, str]]:
        engine = create_async_engine(url, poolclass=pool.NullPool)
        async with engine.connect() as connection:
            checks = await connection.run_sync(read_sync)
        await engine.dispose()
        return checks

    return asyncio.run(read())


def test_migrations_downgrade_and_upgrade_cleanly(
    alembic_config: Config, migrated_database_url: str
) -> None:
    command.downgrade(alembic_config, "base")
    assert not APP_TABLES & _table_names(migrated_database_url)

    command.upgrade(alembic_config, "head")
    assert APP_TABLES <= _table_names(migrated_database_url)


def test_models_match_latest_migration(alembic_config: Config, migrated_database_url: str) -> None:
    # Fails if a model changed without a matching migration.
    command.check(alembic_config)


def test_check_constraints_match_models(migrated_database_url: str) -> None:
    # `alembic check` ignores CHECK constraints, so compare them directly by name.
    model_checks = {
        (table.name, str(constraint.name))
        for table in Base.metadata.sorted_tables
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert model_checks == _database_check_constraints(migrated_database_url)
