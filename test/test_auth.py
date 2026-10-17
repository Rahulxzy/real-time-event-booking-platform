
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def test_register_user_success(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "StrongPass123",
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "hashed_password" not in data


def test_register_duplicate_email(client):
    payload = {
        "email": "duplicate@example.com",
        "password": "StrongPass123",
    }

    first_response = client.post("/auth/register", json=payload)
    second_response = client.post("/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Email is already registered"


def test_register_invalid_email(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "not-an-email",
            "password": "StrongPass123",
        },
    )

    assert response.status_code == 422


def test_register_short_password(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "shortpass@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422


def test_register_database_integrity_error(client):
    mock_db = Mock()
    mock_db.scalar.return_value = None
    mock_db.commit.side_effect = IntegrityError(
        "INSERT",
        {},
        Exception("simulated database integrity error"),
    )

    def override_get_db_with_integrity_error():
        try:
            yield mock_db
        finally:
            pass

    app.dependency_overrides[get_db] = (
        override_get_db_with_integrity_error
    )

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/auth/register",
                json={
                    "email": "race@example.com",
                    "password": "StrongPass123",
                },
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 409
    assert response.json()["detail"] == "Email is already registered"
    mock_db.rollback.assert_called_once()
