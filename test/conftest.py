
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, settings
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

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
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


@pytest.fixture
def postgres_client():
    test_url = URL.create(
        drivername="postgresql+psycopg",
        username=settings.database_user,
        password=settings.database_password,
        host=settings.database_host,
        port=settings.database_port,
        database="event_booking_test_db",
    )

    test_engine = create_engine(
        test_url,
        pool_pre_ping=True,
    )

    # Safety check: never run destructive cleanup on another database.
    with test_engine.connect() as connection:
        database_name = connection.exec_driver_sql(
            "SELECT current_database()"
        ).scalar_one()

    if database_name != "event_booking_test_db":
        test_engine.dispose()
        raise RuntimeError(
            f"Unsafe test database: {database_name}"
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

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


@pytest.fixture
def postgres_auth_headers(postgres_client):
    response = postgres_client.post(
        "/auth/register",
        json={
            "email": "postgres-test@example.com",
            "password": "StrongPass123",
        },
    )
    assert response.status_code == 201

    response = postgres_client.post(
        "/auth/login",
        json={
            "email": "postgres-test@example.com",
            "password": "StrongPass123",
        },
    )
    assert response.status_code == 200

    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}