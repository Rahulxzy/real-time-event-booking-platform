
import pytest

from fastapi import HTTPException

from app.main import app
from app.models import EventSeat, Payment, Reservation
from app.services.reservation_service import (
    confirm_reservation_from_captured_payment,
)


def create_pending_reservation(client, auth_headers):
    venue_response = client.post(
        "/venues",
        json={
            "name": "Payment Test Cinema",
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
            "title": "Payment Test Event",
            "description": "Testing payment confirmation",
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

    event_seat_id = seats_response.json()[0]["id"]

    reservation_response = client.post(
        "/reservations",
        json={
            "event_id": event_id,
            "event_seat_ids": [event_seat_id],
        },
        headers=auth_headers,
    )
    assert reservation_response.status_code == 201

    reservation_id = reservation_response.json()["id"]

    return reservation_id, event_id, event_seat_id


def create_payment(
    reservation_id,
    status,
    amount_paise=25000,
    currency="INR",
):
    TestingSessionLocal = app.state.testing_session_local
    db = TestingSessionLocal()

    try:
        payment = Payment(
            reservation_id=reservation_id,
            amount_paise=amount_paise,
            currency=currency,
            status=status,
            idempotency_key=f"test-payment-{reservation_id}",
        )

        db.add(payment)
        db.commit()
        db.refresh(payment)

        return payment.id

    finally:
        db.close()


def test_confirmation_requires_captured_payment(
    client,
    auth_headers,
):
    reservation_id, _, event_seat_id = (
        create_pending_reservation(client, auth_headers)
    )

    payment_id = create_payment(
        reservation_id,
        status="created",
    )

    db = app.state.testing_session_local()

    try:
        with pytest.raises(HTTPException) as exc_info:
            confirm_reservation_from_captured_payment(
                db,
                reservation_id,
                payment_id,
            )

        assert exc_info.value.status_code == 409

        reservation = db.get(Reservation, reservation_id)
        event_seat = db.get(EventSeat, event_seat_id)

        assert reservation.status == "pending"
        assert event_seat.status == "reserved"

    finally:
        db.close()


def test_confirmation_rejects_mismatched_payment_amount(
    client,
    auth_headers,
):
    reservation_id, _, event_seat_id = (
        create_pending_reservation(client, auth_headers)
    )

    # Expected amount is 25000 paise, but payment has 24999 paise.
    payment_id = create_payment(
        reservation_id,
        status="captured",
        amount_paise=24999,
    )

    db = app.state.testing_session_local()

    try:
        with pytest.raises(HTTPException) as exc_info:
            confirm_reservation_from_captured_payment(
                db,
                reservation_id,
                payment_id,
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == (
            "Payment amount does not match reservation total"
        )

        reservation = db.get(Reservation, reservation_id)
        event_seat = db.get(EventSeat, event_seat_id)

        assert reservation.status == "pending"
        assert event_seat.status == "reserved"

    finally:
        db.close()


def test_captured_payment_confirms_reservation(
    client,
    auth_headers,
):
    reservation_id, _, event_seat_id = (
        create_pending_reservation(client, auth_headers)
    )

    payment_id = create_payment(
        reservation_id,
        status="captured",
        amount_paise=25000,
    )

    db = app.state.testing_session_local()

    try:
        reservation = confirm_reservation_from_captured_payment(
            db,
            reservation_id,
            payment_id,
        )

        assert reservation.status == "confirmed"
        assert reservation.confirmed_at is not None

        event_seat = db.get(EventSeat, event_seat_id)
        assert event_seat.status == "booked"

    finally:
        db.close()
