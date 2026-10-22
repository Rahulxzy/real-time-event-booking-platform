
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


@pytest.fixture
def venue_payload():
    return {
        "name": "Grand Arena",
        "address": "123 Main Street",
        "city": "Delhi",
    }


@pytest.fixture
def event_payload():
    starts_at = datetime.now(timezone.utc) + timedelta(days=2)

    return {
        "title": "Python Conference",
        "description": "A developer conference",
        "starts_at": starts_at.isoformat(),
        "ends_at": (starts_at + timedelta(hours=3)).isoformat(),
        "price": "499.99",
        "capacity": 100,
    }


@pytest.fixture
def created_venue(client, auth_headers, venue_payload):
    response = client.post(
        "/venues",
        json=venue_payload,
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def created_event(client, auth_headers, created_venue, event_payload):
    payload = {
        **event_payload,
        "venue_id": created_venue["id"],
    }

    response = client.post(
        "/events",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


def test_create_event_success(client, auth_headers, created_venue, event_payload):
    payload = {**event_payload, "venue_id": created_venue["id"]}

    response = client.post(
        "/events",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 201

    data = response.json()
    assert data["title"] == event_payload["title"]
    assert data["venue_id"] == created_venue["id"]
    assert data["price"] == "499.99"
    assert data["capacity"] == 100
    assert isinstance(data["id"], int)
    assert "created_at" in data
    assert "updated_at" in data


def test_create_event_without_token(client, created_venue, event_payload):
    payload = {**event_payload, "venue_id": created_venue["id"]}

    response = client.post("/events", json=payload)

    assert response.status_code == 401


def test_create_event_with_nonexistent_venue(client, auth_headers, event_payload):
    payload = {**event_payload, "venue_id": 99999}

    response = client.post(
        "/events",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "invalid_fields",
    [
        {"price": "-1.00"},
        {"capacity": 0},
        {"title": ""},
    ],
)
def test_create_event_invalid_data(
    client, auth_headers, created_venue, event_payload, invalid_fields
):
    payload = {
        **event_payload,
        "venue_id": created_venue["id"],
        **invalid_fields,
    }

    response = client.post(
        "/events",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_list_events(client, created_event):
    response = client.get("/events")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == created_event["id"]


def test_list_events_pagination(client, auth_headers, created_venue, event_payload):
    for title in ["Event A", "Event B", "Event C"]:
        payload = {
            **event_payload,
            "venue_id": created_venue["id"],
            "title": title,
        }
        response = client.post(
            "/events",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 201

    response = client.get("/events?skip=1&limit=1")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Event B"


def test_list_events_by_venue(client, auth_headers, created_venue, event_payload):
    payload = {**event_payload, "venue_id": created_venue["id"]}
    create_response = client.post(
        "/events",
        json=payload,
        headers=auth_headers,
    )
    assert create_response.status_code == 201

    response = client.get(f"/events?venue_id={created_venue['id']}")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["venue_id"] == created_venue["id"]


@pytest.mark.parametrize(
    "query",
    ["?skip=-1", "?limit=0", "?limit=101", "?venue_id=0"],
)
def test_list_events_invalid_query(client, query):
    response = client.get(f"/events{query}")

    assert response.status_code == 422


def test_get_event(client, created_event):
    response = client.get(f"/events/{created_event['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created_event["id"]
    assert response.json()["title"] == created_event["title"]


def test_get_nonexistent_event(client):
    response = client.get("/events/99999")

    assert response.status_code == 404


def test_update_event(client, auth_headers, created_event):
    response = client.patch(
        f"/events/{created_event['id']}",
        json={"title": "Updated Conference"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Conference"
    assert response.json()["capacity"] == created_event["capacity"]


def test_update_event_clear_description(client, auth_headers, created_event):
    response = client.patch(
        f"/events/{created_event['id']}",
        json={"description": None},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["description"] is None


def test_update_event_reject_null_title(client, auth_headers, created_event):
    response = client.patch(
        f"/events/{created_event['id']}",
        json={"title": None},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_update_event_without_token(client, created_event):
    response = client.patch(
        f"/events/{created_event['id']}",
        json={"title": "Updated Conference"},
    )

    assert response.status_code == 401


def test_update_event_empty_payload(client, auth_headers, created_event):
    response = client.patch(
        f"/events/{created_event['id']}",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_update_event_invalid_final_time_range(client, auth_headers, created_event):
    response = client.patch(
        f"/events/{created_event['id']}",
        json={"ends_at": created_event["starts_at"]},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_update_event_with_nonexistent_venue(client, auth_headers, created_event):
    response = client.patch(
        f"/events/{created_event['id']}",
        json={"venue_id": 99999},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_update_nonexistent_event(client, auth_headers):
    response = client.patch(
        "/events/99999",
        json={"title": "Updated Conference"},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_delete_event(client, auth_headers, created_event):
    event_id = created_event["id"]

    response = client.delete(
        f"/events/{event_id}",
        headers=auth_headers,
    )

    assert response.status_code == 204
    assert response.content == b""

    get_response = client.get(f"/events/{event_id}")
    assert get_response.status_code == 404


def test_delete_event_without_token(client, created_event):
    response = client.delete(f"/events/{created_event['id']}")

    assert response.status_code == 401


def test_delete_nonexistent_event(client, auth_headers):
    response = client.delete(
        "/events/99999",
        headers=auth_headers,
    )

    assert response.status_code == 404
