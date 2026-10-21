
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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


@pytest.fixture
def auth_headers(client):
    client.post(
        "/auth/register",
        json={
            "email": "venueowner@example.com",
            "password": "StrongPass123",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "venueowner@example.com",
            "password": "StrongPass123",
        },
    )

    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def venue_payload():
    return {
        "name": "Grand Arena",
        "address": "123 Main Street",
        "city": "Delhi",
    }


def test_create_venue_success(client, auth_headers, venue_payload):
    response = client.post(
        "/venues",
        json=venue_payload,
        headers=auth_headers,
    )

    assert response.status_code == 201

    data = response.json()
    assert data["name"] == venue_payload["name"]
    assert data["address"] == venue_payload["address"]
    assert data["city"] == venue_payload["city"]
    assert isinstance(data["id"], int)
    assert "created_at" in data
    assert "updated_at" in data


def test_create_venue_without_token(client, venue_payload):
    response = client.post("/venues", json=venue_payload)

    assert response.status_code == 401


def test_create_venue_invalid_data(client, auth_headers):
    response = client.post(
        "/venues",
        json={
            "name": "",
            "address": "123 Main Street",
            "city": "Delhi",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_list_venues(client, auth_headers, venue_payload):
    create_response = client.post(
        "/venues",
        json=venue_payload,
        headers=auth_headers,
    )
    assert create_response.status_code == 201

    response = client.get("/venues")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Grand Arena"


def test_list_venues_pagination(client, auth_headers, venue_payload):
    for name in ["Arena A", "Arena B", "Arena C"]:
        payload = {**venue_payload, "name": name}
        response = client.post(
            "/venues",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 201

    response = client.get("/venues?skip=1&limit=1")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Arena B"


@pytest.mark.parametrize(
    "query",
    ["?skip=-1", "?limit=0", "?limit=101"],
)
def test_list_venues_invalid_pagination(client, query):
    response = client.get(f"/venues{query}")

    assert response.status_code == 422


def test_get_venue(client, auth_headers, venue_payload):
    create_response = client.post(
        "/venues",
        json=venue_payload,
        headers=auth_headers,
    )
    venue_id = create_response.json()["id"]

    response = client.get(f"/venues/{venue_id}")

    assert response.status_code == 200
    assert response.json()["id"] == venue_id
    assert response.json()["name"] == "Grand Arena"


def test_get_nonexistent_venue(client):
    response = client.get("/venues/99999")

    assert response.status_code == 404


def test_update_venue(client, auth_headers, venue_payload):
    create_response = client.post(
        "/venues",
        json=venue_payload,
        headers=auth_headers,
    )
    venue_id = create_response.json()["id"]

    response = client.patch(
        f"/venues/{venue_id}",
        json={"city": "Mumbai"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["city"] == "Mumbai"
    assert response.json()["name"] == "Grand Arena"


def test_update_venue_without_token(client, venue_payload):
    create_response = client.post(
        "/auth/register",
        json={
            "email": "anotheruser@example.com",
            "password": "StrongPass123",
        },
    )
    assert create_response.status_code == 201

    # Venue creation requires authentication, so test PATCH against
    # a missing venue to verify auth is checked before endpoint logic.
    response = client.patch(
        "/venues/1",
        json={"city": "Mumbai"},
    )

    assert response.status_code == 401


def test_update_venue_empty_payload(client, auth_headers, venue_payload):
    create_response = client.post(
        "/venues",
        json=venue_payload,
        headers=auth_headers,
    )
    venue_id = create_response.json()["id"]

    response = client.patch(
        f"/venues/{venue_id}",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_update_nonexistent_venue(client, auth_headers):
    response = client.patch(
        "/venues/99999",
        json={"city": "Mumbai"},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_delete_venue(client, auth_headers, venue_payload):
    create_response = client.post(
        "/venues",
        json=venue_payload,
        headers=auth_headers,
    )
    venue_id = create_response.json()["id"]

    response = client.delete(
        f"/venues/{venue_id}",
        headers=auth_headers,
    )

    assert response.status_code == 204
    assert response.content == b""

    get_response = client.get(f"/venues/{venue_id}")
    assert get_response.status_code == 404


def test_delete_venue_without_token(client):
    response = client.delete("/venues/1")

    assert response.status_code == 401


def test_delete_nonexistent_venue(client, auth_headers):
    response = client.delete(
        "/venues/99999",
        headers=auth_headers,
    )

    assert response.status_code == 404
