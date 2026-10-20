
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



def test_login_success(client):
    registration = client.post(
        "/auth/register",
        json={
            "email": "login@example.com",
            "password": "StrongPass123",
        },
    )
    assert registration.status_code == 201

    response = client.post(
        "/auth/login",
        json={
            "email": "login@example.com",
            "password": "StrongPass123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 0
    assert "hashed_password" not in data


def test_login_wrong_password(client):
    client.post(
        "/auth/register",
        json={
            "email": "loginwrong@example.com",
            "password": "StrongPass123",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "loginwrong@example.com",
            "password": "WrongPassword123",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_unknown_email(client):
    response = client.post(
        "/auth/login",
        json={
            "email": "unknown@example.com",
            "password": "StrongPass123",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_inactive_user_cannot_login(client):
    from sqlalchemy import select
    from app.dependencies import get_db
    from app.models import User

    registration = client.post(
        "/auth/register",
        json={
            "email": "inactive@example.com",
            "password": "StrongPass123",
        },
    )
    assert registration.status_code == 201

    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)

    try:
        user = db.scalar(
            select(User).where(User.email == "inactive@example.com")
        )
        assert user is not None
        user.is_active = False
        db.commit()
    finally:
        db_generator.close()

    response = client.post(
        "/auth/login",
        json={
            "email": "inactive@example.com",
            "password": "StrongPass123",
        },
    )

    assert response.status_code == 401



def test_auth_me_without_token(client):
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_auth_me_with_valid_token(client):
    client.post(
        "/auth/register",
        json={
            "email": "me@example.com",
            "password": "StrongPass123",
        },
    )

    login_response = client.post(
        "/auth/login",
        json={
            "email": "me@example.com",
            "password": "StrongPass123",
        },
    )
    assert login_response.status_code == 200

    token = login_response.json()["access_token"]

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"
    assert "hashed_password" not in response.json()


def test_auth_me_with_invalid_token(client):
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.token.value"},
    )

    assert response.status_code == 401
