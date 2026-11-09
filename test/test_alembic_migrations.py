from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"

EXPECTED_HEAD = "c8ae5a8ca40f"
RESERVATION_MIGRATION_PARENT = "311fcb345c93"

EXPECTED_TABLES = {
    "users",
    "venues",
    "events",
    "seats",
    "event_seats",
    "reservations",
    "reservation_seats",
    "payments",
    "payment_webhook_events",
    "alembic_version",
}

TABLES_REMOVED_AFTER_RESERVATION_DOWNGRADE = {
    "reservations",
    "reservation_seats",
    "payments",
    "payment_webhook_events",
}


def run_alembic(connection, operation, revision):
    config = Config(str(ALEMBIC_INI))
    config.attributes["connection"] = connection

    if operation == "upgrade":
        command.upgrade(config, revision)
    elif operation == "downgrade":
        command.downgrade(config, revision)
    else:
        raise ValueError(f"Unsupported Alembic operation: {operation}")


@pytest.fixture
def migrated_postgres(testcontainers_postgres):
    database_url = testcontainers_postgres.get_connection_url()

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    try:
        with engine.begin() as connection:
            run_alembic(connection, "upgrade", "head")

        yield engine

    finally:
        # This database belongs to the disposable Testcontainers instance.
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))

        engine.dispose()


def get_current_revision(engine):
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()


def test_alembic_upgrade_creates_expected_schema(migrated_postgres):
    inspector = inspect(migrated_postgres)

    actual_tables = set(inspector.get_table_names())

    assert EXPECTED_TABLES.issubset(actual_tables)


def test_alembic_upgrade_reaches_expected_head(migrated_postgres):
    revision = get_current_revision(migrated_postgres)

    assert revision == EXPECTED_HEAD


def test_alembic_downgrade_and_upgrade_cycle(migrated_postgres):
    # Downgrade all migrations after the event seat inventory revision.
    with migrated_postgres.begin() as connection:
        run_alembic(
            connection,
            "downgrade",
            RESERVATION_MIGRATION_PARENT,
        )

    assert get_current_revision(migrated_postgres) == (
        RESERVATION_MIGRATION_PARENT
    )

    # Verify reservation and payment tables were removed.
    tables_after_downgrade = set(
        inspect(migrated_postgres).get_table_names()
    )

    assert TABLES_REMOVED_AFTER_RESERVATION_DOWNGRADE.isdisjoint(
        tables_after_downgrade
    )

    # Upgrade everything again.
    with migrated_postgres.begin() as connection:
        run_alembic(connection, "upgrade", "head")

    assert get_current_revision(migrated_postgres) == EXPECTED_HEAD

    # Verify the complete schema has been restored.
    tables_after_upgrade = set(
        inspect(migrated_postgres).get_table_names()
    )

    assert EXPECTED_TABLES.issubset(tables_after_upgrade)