
from fastapi import status
from sqlalchemy import select

from app.dependencies import get_db
from app.models import EventSeat


def create_venue(client, auth_headers):
    response = client.post(
        "/venues",
        json={
            "name": "Test Cinema",
            "address": "123 Test Street",
            "city": "Delhi",
        },
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def create_event(client, auth_headers, venue_id):
    response = client.post(
        "/events",
        json={
            "venue_id": venue_id,
            "title": "Test Movie",
            "description": "Inventory test event",
            "starts_at": "2027-01-15T18:00:00+05:30",
            "ends_at": "2027-01-15T21:00:00+05:30",
            "price": "250.00",
            "capacity": 2,
        },
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def create_seat(client, auth_headers, venue_id, seat_number):
    response = client.post(
        f"/venues/{venue_id}/seats",
        json={"row_label": "A", "seat_number": seat_number},
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def initialize_inventory(client, auth_headers, event_id):
    return client.post(
        f"/events/{event_id}/inventory",
        headers=auth_headers,
    )


def get_test_db(client):
    generator = client.app.dependency_overrides[get_db]()
    return next(generator), generator


def close_test_db(db, generator):
    db.close()
    try:
        next(generator)
    except StopIteration:
        pass


def test_initialize_event_inventory(client, auth_headers):
    venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])

    create_seat(client, auth_headers, venue["id"], 1)
    create_seat(client, auth_headers, venue["id"], 2)

    response = initialize_inventory(client, auth_headers, event["id"])

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["event_id"] == event["id"]
    assert response.json()["created_count"] == 2
    assert response.json()["total_count"] == 2


def test_initialize_inventory_twice_does_not_duplicate_seats(
    client, auth_headers
):
    venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])

    create_seat(client, auth_headers, venue["id"], 1)
    create_seat(client, auth_headers, venue["id"], 2)

    first = initialize_inventory(client, auth_headers, event["id"])
    second = initialize_inventory(client, auth_headers, event["id"])

    assert first.status_code == status.HTTP_201_CREATED
    assert first.json()["created_count"] == 2
    assert second.status_code == status.HTTP_201_CREATED
    assert second.json()["created_count"] == 0
    assert second.json()["total_count"] == 2


def test_reinitialization_preserves_existing_seat_status(
    client, auth_headers
):
    venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])
    seat = create_seat(client, auth_headers, venue["id"], 1)

    assert initialize_inventory(
        client, auth_headers, event["id"]
    ).status_code == status.HTTP_201_CREATED

    db, generator = get_test_db(client)
    try:
        event_seat = db.scalar(
            select(EventSeat).where(
                EventSeat.event_id == event["id"],
                EventSeat.seat_id == seat["id"],
            )
        )
        assert event_seat is not None
        event_seat.status = "reserved"
        db.commit()
    finally:
        close_test_db(db, generator)

    response = initialize_inventory(client, auth_headers, event["id"])
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["created_count"] == 0

    db, generator = get_test_db(client)
    try:
        event_seat = db.scalar(
            select(EventSeat).where(
                EventSeat.event_id == event["id"],
                EventSeat.seat_id == seat["id"],
            )
        )
        assert event_seat.status == "reserved"
    finally:
        close_test_db(db, generator)


def test_list_event_seats(client, auth_headers):
    venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])

    create_seat(client, auth_headers, venue["id"], 2)
    create_seat(client, auth_headers, venue["id"], 1)

    assert initialize_inventory(
        client, auth_headers, event["id"]
    ).status_code == status.HTTP_201_CREATED

    response = client.get(f"/events/{event['id']}/seats")

    assert response.status_code == status.HTTP_200_OK
    seats = response.json()
    assert len(seats) == 2
    assert [seat["seat_number"] for seat in seats] == [1, 2]
    assert all(seat["row_label"] == "A" for seat in seats)
    assert all(seat["status"] == "available" for seat in seats)


def test_get_single_event_seat(client, auth_headers):
    venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])
    seat = create_seat(client, auth_headers, venue["id"], 1)

    assert initialize_inventory(
        client, auth_headers, event["id"]
    ).status_code == status.HTTP_201_CREATED

    response = client.get(
        f"/events/{event['id']}/seats/{seat['id']}"
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["event_id"] == event["id"]
    assert data["seat_id"] == seat["id"]
    assert data["row_label"] == "A"
    assert data["seat_number"] == 1
    assert data["status"] == "available"


def test_list_event_seats_before_inventory_returns_empty_list(
    client, auth_headers
):
    venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])

    response = client.get(f"/events/{event['id']}/seats")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == []


def test_initialize_inventory_for_event_without_seats_returns_409(
    client, auth_headers
):
    venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])

    response = initialize_inventory(client, auth_headers, event["id"])

    assert response.status_code == status.HTTP_409_CONFLICT


def test_initialize_inventory_for_missing_event_returns_404(
    client, auth_headers
):
    response = initialize_inventory(client, auth_headers, 99999)
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_list_seats_for_missing_event_returns_404(client):
    response = client.get("/events/99999/seats")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_seat_not_in_inventory_returns_404(client, auth_headers):
    venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])

    response = client.get(f"/events/{event['id']}/seats/99999")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_initialize_inventory_requires_authentication(client):
    response = client.post("/events/1/inventory")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    


def test_update_seat_after_inventory_returns_409(client, auth_headers):
    venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])
    seat = create_seat(client, auth_headers, venue["id"], 1)

    inventory_response = initialize_inventory(
        client, auth_headers, event["id"]
    )
    assert inventory_response.status_code == status.HTTP_201_CREATED

    response = client.patch(
        f"/venues/{venue['id']}/seats/{seat['id']}",
        json={"seat_number": 5},
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "event inventory" in response.json()["detail"]


def test_delete_seat_after_inventory_returns_409(client, auth_headers):
    venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])
    seat = create_seat(client, auth_headers, venue["id"], 1)

    inventory_response = initialize_inventory(
        client, auth_headers, event["id"]
    )
    assert inventory_response.status_code == status.HTTP_201_CREATED

    response = client.delete(
        f"/venues/{venue['id']}/seats/{seat['id']}",
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT


def test_change_event_venue_after_inventory_returns_409(
    client, auth_headers
):
    venue = create_venue(client, auth_headers)
    another_venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])

    create_seat(client, auth_headers, venue["id"], 1)

    inventory_response = initialize_inventory(
        client, auth_headers, event["id"]
    )
    assert inventory_response.status_code == status.HTTP_201_CREATED

    response = client.patch(
        f"/events/{event['id']}",
        json={"venue_id": another_venue["id"]},
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert "venue" in response.json()["detail"].lower()


def test_delete_event_after_inventory_returns_409(client, auth_headers):
    venue = create_venue(client, auth_headers)
    event = create_event(client, auth_headers, venue["id"])

    create_seat(client, auth_headers, venue["id"], 1)

    inventory_response = initialize_inventory(
        client, auth_headers, event["id"]
    )
    assert inventory_response.status_code == status.HTTP_201_CREATED

    response = client.delete(
        f"/events/{event['id']}",
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_409_CONFLICT
