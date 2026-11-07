
from sqlalchemy import text


def test_testcontainers_postgresql_connection(
    testcontainers_postgres_engine,
):
    with testcontainers_postgres_engine.connect() as connection:
        version = connection.execute(
            text("SELECT version()")
        ).scalar_one()

        database_name = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

    assert "PostgreSQL 18" in version
    assert database_name == "test"
