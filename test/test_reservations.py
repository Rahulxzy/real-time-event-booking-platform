
import psycopg

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from sqlalchemy import func, select

from app.database import settings
from app.models import Reservation
from app.routers import reservations as reservations_router


def setup_inventory(client, auth_headers, seat_count=2):
    venue_response = client.post(
        "/venues",
        json={
            "name": "Reservation Test Cinema",
            "address": "123 Test Street",
            "city": "Delhi",
        },
        headers=auth_headers,
    )
    assert venue_response.status_code == 201
    venue_id = venue_response.json()["id"]

    event_response = client.post(
        "/events",
        json={
            "venue_id": venue_id,
            "title": "Reservation Test Event",
            "description": "Testing reservations",
            "starts_at": "2027-01-15T18:00:00+05:30",
            "ends_at": "2027-01-15T21:00:00+05:30",
            "price": "250.00",
            "capacity": seat_count,
        },
        headers=auth_headers,
    )
    assert event_response.status_code == 201
    event_id = event_response.json()["id"]

    for number in range(1, seat_count + 1):
        seat_response = client.post(
            f"/venues/{venue_id}/seats",
            json={
                "row_label": "A",
                "seat_number": number,
            },
            headers=auth_headers,
        )
        assert seat_response.status_code == 201

    inventory_response = client.post(
        f"/events/{event_id}/inventory",
        headers=auth_headers,
    )
    assert inventory_response.status_code == 201

    seats_response = client.get(f"/events/{event_id}/seats")
    assert seats_response.status_code == 200

    return event_id, seats_response.json()


def reserve_seats(client, auth_headers, event_id, seat_ids):
    return client.post(
        "/reservations",
        json={
            "event_id": event_id,
            "event_seat_ids": seat_ids,
        },
        headers=auth_headers,
    )


def create_second_user(client):
    email = "reservation-user@example.com"
    password = "StrongPass123"

    register_response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert login_response.status_code == 200

    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_reservation(client, auth_headers):
    event_id, seats = setup_inventory(client, auth_headers)

    response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[0]["id"]],
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert len(response.json()["seats"]) == 1
    assert response.json()["total_amount"] == "250.00"

    updated_seats = client.get(
        f"/events/{event_id}/seats"
    ).json()

    assert updated_seats[0]["status"] == "reserved"


def test_create_reservation_for_multiple_seats(client, auth_headers):
    event_id, seats = setup_inventory(
        client,
        auth_headers,
        seat_count=3,
    )

    response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[0]["id"], seats[1]["id"]],
    )

    assert response.status_code == 201
    assert len(response.json()["seats"]) == 2
    assert response.json()["total_amount"] == "500.00"


def test_cannot_reserve_already_reserved_seat(client, auth_headers):
    event_id, seats = setup_inventory(client, auth_headers)
    seat_id = seats[0]["id"]

    first_response = reserve_seats(
        client, auth_headers, event_id, [seat_id]
    )
    assert first_response.status_code == 201

    second_response = reserve_seats(
        client, auth_headers, event_id, [seat_id]
    )

    assert second_response.status_code == 409


def test_direct_confirmation_endpoint_is_disabled(
    client,
    auth_headers,
):
    event_id, seats = setup_inventory(client, auth_headers)

    reservation_response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[0]["id"]],
    )
    assert reservation_response.status_code == 201

    reservation_id = reservation_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/confirm",
        headers=auth_headers,
    )

    # The public confirmation endpoint has been removed.
    assert response.status_code == 404

    # Reservation must remain pending.
    reservation_details = client.get(
        f"/reservations/{reservation_id}",
        headers=auth_headers,
    )

    assert reservation_details.status_code == 200
    assert reservation_details.json()["status"] == "pending"

    # Its seat must remain reserved, not booked.
    updated_seats = client.get(
        f"/events/{event_id}/seats"
    ).json()

    assert updated_seats[0]["status"] == "reserved"


def test_cancel_reservation_releases_seat(client, auth_headers):
    event_id, seats = setup_inventory(client, auth_headers)

    reservation_response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[0]["id"]],
    )
    reservation_id = reservation_response.json()["id"]

    response = client.post(
        f"/reservations/{reservation_id}/cancel",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    updated_seats = client.get(
        f"/events/{event_id}/seats"
    ).json()

    assert updated_seats[0]["status"] == "available"


def test_user_cannot_access_another_users_reservation(
    client,
    auth_headers,
):
    event_id, seats = setup_inventory(client, auth_headers)

    reservation_response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[0]["id"]],
    )
    reservation_id = reservation_response.json()["id"]

    second_user_headers = create_second_user(client)

    response = client.get(
        f"/reservations/{reservation_id}",
        headers=second_user_headers,
    )

    assert response.status_code == 404


def test_duplicate_seat_ids_return_422(client, auth_headers):
    event_id, seats = setup_inventory(client, auth_headers)
    seat_id = seats[0]["id"]

    response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seat_id, seat_id],
    )

    assert response.status_code == 422


def test_invalid_event_seat_id_returns_404(client, auth_headers):
    event_id, _ = setup_inventory(client, auth_headers)

    response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [999999],
    )

    assert response.status_code == 404


def test_expired_reservation_releases_seats(
    client,
    auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(
        reservations_router,
        "HOLD_MINUTES",
        -1,
    )

    event_id, seats = setup_inventory(
        client,
        auth_headers,
        seat_count=2,
    )

    first_response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[0]["id"]],
    )
    assert first_response.status_code == 201
    first_reservation_id = first_response.json()["id"]

    # First reservation is already expired.
    # Give the second reservation a normal 5-minute hold.
    monkeypatch.setattr(
        reservations_router,
        "HOLD_MINUTES",
        5,
    )

    # Creating another reservation triggers lazy expiry
    # for overdue reservations belonging to this event.
    second_response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[1]["id"]],
    )
    assert second_response.status_code == 201

    expired_response = client.get(
        f"/reservations/{first_reservation_id}",
        headers=auth_headers,
    )

    assert expired_response.status_code == 200
    assert expired_response.json()["status"] == "expired"

    updated_seats = client.get(
        f"/events/{event_id}/seats"
    ).json()

    assert updated_seats[0]["status"] == "available"
    assert updated_seats[1]["status"] == "reserved"


def test_concurrent_reservations_for_same_seat(
    postgres_client,
    postgres_auth_headers,
):
    # Arrange: create one event with exactly one available seat.
    event_id, seats = setup_inventory(
        postgres_client,
        postgres_auth_headers,
        seat_count=1,
    )

    event_seat_id = seats[0]["id"]

    # Create a second, independent user.
    second_user_headers = create_second_user(postgres_client)

    # Synchronize both requests so they start together.
    barrier = Barrier(2)

    def make_reservation(headers):
        barrier.wait(timeout=10)

        return reserve_seats(
            postgres_client,
            headers,
            event_id,
            [event_seat_id],
        )

    # Act: both users attempt to reserve the same seat.
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_one = executor.submit(
            make_reservation,
            postgres_auth_headers,
        )
        future_two = executor.submit(
            make_reservation,
            second_user_headers,
        )

        response_one = future_one.result(timeout=20)
        response_two = future_two.result(timeout=20)

    # Assert: exactly one succeeds and one gets a conflict.
    statuses = sorted([
        response_one.status_code,
        response_two.status_code,
    ])

    assert statuses == [201, 409]

    # Verify the seat has only been reserved, not double-booked.
    updated_seats = postgres_client.get(
        f"/events/{event_id}/seats"
    ).json()

    assert len(updated_seats) == 1
    assert updated_seats[0]["status"] == "reserved"

    # Verify exactly one reservation-seat record exists in PostgreSQL.
    with psycopg.connect(
        host=settings.database_host,
        port=settings.database_port,
        dbname="event_booking_test_db",
        user=settings.database_user,
        password=settings.database_password,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM reservation_seats
                WHERE event_seat_id = %s
                """,
                (event_seat_id,),
            )

            reservation_count = cursor.fetchone()[0]

    assert reservation_count == 1


def set_reservation_deadlines(
    client,
    reservation_id,
    expires_in_minutes,
    checkout_in_minutes=None,
):
    """Set test deadlines relative to the database clock."""
    testing_session_local = client.app.state.testing_session_local
    db = testing_session_local()

    try:
        now = db.scalar(select(func.now()))
        reservation = db.get(Reservation, reservation_id)

        assert reservation is not None

        reservation.expires_at = now + timedelta(
            minutes=expires_in_minutes
        )

        if checkout_in_minutes is not None:
            reservation.checkout_deadline_at = now + timedelta(
                minutes=checkout_in_minutes
            )

        db.commit()
    finally:
        db.close()


def test_checkout_deadline_prevents_premature_expiry(
    client,
    auth_headers,
):
    event_id, seats = setup_inventory(client, auth_headers)

    first_response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[0]["id"]],
    )
    assert first_response.status_code == 201
    first_reservation_id = first_response.json()["id"]

    # The original hold has elapsed, but checkout is still active.
    set_reservation_deadlines(
        client,
        first_reservation_id,
        expires_in_minutes=-1,
        checkout_in_minutes=5,
    )

    second_response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[1]["id"]],
    )
    assert second_response.status_code == 201

    first_details = client.get(
        f"/reservations/{first_reservation_id}",
        headers=auth_headers,
    )

    assert first_details.status_code == 200
    assert first_details.json()["status"] == "pending"

    updated_seats = client.get(
        f"/events/{event_id}/seats"
    ).json()

    assert updated_seats[0]["status"] == "reserved"
    assert updated_seats[1]["status"] == "reserved"


def test_expired_checkout_deadline_releases_seats(
    client,
    auth_headers,
):
    event_id, seats = setup_inventory(client, auth_headers)

    first_response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[0]["id"]],
    )
    assert first_response.status_code == 201
    first_reservation_id = first_response.json()["id"]

    # The original hold is still active, but checkout has expired.
    set_reservation_deadlines(
        client,
        first_reservation_id,
        expires_in_minutes=5,
        checkout_in_minutes=-1,
    )

    second_response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[1]["id"]],
    )
    assert second_response.status_code == 201

    first_details = client.get(
        f"/reservations/{first_reservation_id}",
        headers=auth_headers,
    )

    assert first_details.status_code == 200
    assert first_details.json()["status"] == "expired"

    updated_seats = client.get(
        f"/events/{event_id}/seats"
    ).json()

    assert updated_seats[0]["status"] == "available"
    assert updated_seats[1]["status"] == "reserved"


def test_user_reservation_expiry_uses_checkout_deadline(
    client,
    auth_headers,
):
    event_id, seats = setup_inventory(client, auth_headers)

    reservation_response = reserve_seats(
        client,
        auth_headers,
        event_id,
        [seats[0]["id"]],
    )
    assert reservation_response.status_code == 201
    reservation_id = reservation_response.json()["id"]

    # /reservations/me must not expire a reservation whose
    # checkout deadline is still in the future.
    set_reservation_deadlines(
        client,
        reservation_id,
        expires_in_minutes=-1,
        checkout_in_minutes=5,
    )

    response = client.get(
        "/reservations/me",
        headers=auth_headers,
    )

    assert response.status_code == 200

    reservation = next(
        item
        for item in response.json()
        if item["id"] == reservation_id
    )
    assert reservation["status"] == "pending"

    updated_seats = client.get(
        f"/events/{event_id}/seats"
    ).json()

    assert updated_seats[0]["status"] == "reserved"
