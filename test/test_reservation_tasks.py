
from datetime import timedelta

from sqlalchemy import func, select

from app.models import EventSeat, Reservation
from app.tasks import reservation_tasks


def setup_task_test_inventory(client, auth_headers):
    venue_response = client.post(
        "/venues",
        json={
            "name": "Celery Test Cinema",
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
            "title": "Celery Test Event",
            "description": "Testing Celery reservation expiry",
            "starts_at": "2027-01-15T18:00:00+05:30",
            "ends_at": "2027-01-15T21:00:00+05:30",
            "price": "250.00",
            "capacity": 1,
        },
        headers=auth_headers,
    )
    assert event_response.status_code == 201
    event_id = event_response.json()["id"]

    seat_response = client.post(
        f"/venues/{venue_id}/seats",
        json={
            "row_label": "A",
            "seat_number": 1,
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

    return event_id, seats_response.json()[0]["id"]


def make_reservation(client, auth_headers, event_id, event_seat_id):
    response = client.post(
        "/reservations",
        json={
            "event_id": event_id,
            "event_seat_ids": [event_seat_id],
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    return response.json()["id"]


def make_reservation_overdue(session_factory, reservation_id):
    db = session_factory()

    try:
        database_now = db.scalar(select(func.now()))

        reservation = db.get(Reservation, reservation_id)
        assert reservation is not None

        reservation.expires_at = database_now - timedelta(minutes=1)
        reservation.checkout_deadline_at = None

        db.commit()
    finally:
        db.close()


def verify_expired_reservation(
    session_factory,
    reservation_id,
    event_seat_id,
):
    db = session_factory()

    try:
        reservation = db.get(Reservation, reservation_id)
        event_seat = db.get(EventSeat, event_seat_id)

        assert reservation is not None
        assert event_seat is not None

        assert reservation.status == "expired"
        assert event_seat.status == "available"
    finally:
        db.close()


def test_celery_task_expires_reservation_and_releases_seat(
    client,
    auth_headers,
    monkeypatch,
):
    event_id, event_seat_id = setup_task_test_inventory(
        client,
        auth_headers,
    )

    reservation_id = make_reservation(
        client,
        auth_headers,
        event_id,
        event_seat_id,
    )

    testing_session_local = client.app.state.testing_session_local

    monkeypatch.setattr(
        reservation_tasks,
        "SessionLocal",
        testing_session_local,
    )

    make_reservation_overdue(
        testing_session_local,
        reservation_id,
    )

    expired_count = reservation_tasks.expire_due_reservations_task.run()

    assert expired_count == 1

    verify_expired_reservation(
        testing_session_local,
        reservation_id,
        event_seat_id,
    )


def test_celery_task_expires_reservation_in_postgresql(
    postgres_client,
    postgres_auth_headers,
    monkeypatch,
):
    event_id, event_seat_id = setup_task_test_inventory(
        postgres_client,
        postgres_auth_headers,
    )

    reservation_id = make_reservation(
        postgres_client,
        postgres_auth_headers,
        event_id,
        event_seat_id,
    )

    testing_session_local = (
        postgres_client.app.state.testing_session_local
    )

    monkeypatch.setattr(
        reservation_tasks,
        "SessionLocal",
        testing_session_local,
    )

    make_reservation_overdue(
        testing_session_local,
        reservation_id,
    )

    expired_count = reservation_tasks.expire_due_reservations_task.run()

    assert expired_count == 1

    verify_expired_reservation(
        testing_session_local,
        reservation_id,
        event_seat_id,
    )
