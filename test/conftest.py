import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from testcontainers.community.postgres import PostgresContainer

from app.database import Base
from app.dependencies import get_db
from app.main import app


@pytest.fixture
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.state.testing_session_local = TestingSessionLocal

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.state.testing_session_local = None
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


@pytest.fixture
def auth_headers(client):
    register_response = client.post(
        "/auth/register",
        json={
            "email": "venueowner@example.com",
            "password": "StrongPass123",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={
            "email": "venueowner@example.com",
            "password": "StrongPass123",
        },
    )
    assert login_response.status_code == 200

    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def testcontainers_postgres():
    """
    Start one disposable PostgreSQL container for this pytest session.
    The container is automatically removed after the session.
    """
    with PostgresContainer(
        "postgres:18-alpine",
        driver="psycopg",
    ) as postgres:
        yield postgres


@pytest.fixture
def testcontainers_postgres_engine(testcontainers_postgres):
    """
    Create an isolated SQLAlchemy engine for the test container.
    """
    connection_url = testcontainers_postgres.get_connection_url()

    test_engine = create_engine(
        connection_url,
        pool_pre_ping=True,
    )

    try:
        with test_engine.connect() as connection:
            database_name = connection.exec_driver_sql(
                "SELECT current_database()"
            ).scalar_one()

            assert database_name == "test"

        yield test_engine

    finally:
        test_engine.dispose()


@pytest.fixture
def testcontainers_postgres_session_local(
    testcontainers_postgres_engine,
):
    TestingSessionLocal = sessionmaker(
        bind=testcontainers_postgres_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=testcontainers_postgres_engine)

    try:
        yield TestingSessionLocal
    finally:
        Base.metadata.drop_all(bind=testcontainers_postgres_engine)


@pytest.fixture
def testcontainers_postgres_client(
    testcontainers_postgres_session_local,
):
    TestingSessionLocal = testcontainers_postgres_session_local

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.state.testing_session_local = TestingSessionLocal

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.state.testing_session_local = None


@pytest.fixture
def testcontainers_postgres_auth_headers(testcontainers_postgres_client):
    response = testcontainers_postgres_client.post(
        "/auth/register",
        json={
            "email": "container-test@example.com",
            "password": "StrongPass123",
        },
    )
    assert response.status_code == 201

    response = testcontainers_postgres_client.post(
        "/auth/login",
        json={
            "email": "container-test@example.com",
            "password": "StrongPass123",
        },
    )
    assert response.status_code == 200

    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}