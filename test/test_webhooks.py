
import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.database import settings
from app.main import app
from app.models import (
    EventSeat,
    Payment,
    PaymentWebhookEvent,
    Reservation,
)


@pytest.fixture
def webhook_configured(monkeypatch):
    monkeypatch.setattr(
        settings,
        "razorpay_webhook_secret",
        "webhook_test_secret",
    )


def create_reservation(client, auth_headers):
    venue_response = client.post(
        "/venues",
        json={
            "name": "Webhook Test Cinema",
            "address": "123 Webhook Street",
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
            "title": "Webhook Test Event",
            "description": "Testing Razorpay webhooks",
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

    return reservation_id, event_seat_id


def create_payment(client, reservation_id):
    db = client.app.state.testing_session_local()

    try:
        payment = Payment(
            reservation_id=reservation_id,
            provider="razorpay",
            provider_order_id="order_webhook_test",
            amount_paise=25000,
            currency="INR",
            status="created",
            idempotency_key=f"webhook-test-{reservation_id}",
        )

        db.add(payment)
        db.commit()
        db.refresh(payment)

        return payment.id

    finally:
        db.close()


def create_webhook_payload(
    event_type="payment.captured",
    payment_id="pay_webhook_test",
    order_id="order_webhook_test",
    amount=25000,
    currency="INR",
    payment_status="captured",
):
    return {
        "entity": "event",
        "event": event_type,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": amount,
                    "currency": currency,
                    "status": payment_status,
                }
            }
        },
    }


def sign_payload(payload):
    raw_body = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    signature = hmac.new(
        b"webhook_test_secret",
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return raw_body, signature


def send_webhook(
    client,
    payload,
    event_id="event_webhook_001",
    signature_override=None,
):
    raw_body, signature = sign_payload(payload)

    if signature_override is not None:
        signature = signature_override

    return client.post(
        "/webhooks/razorpay",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
            "x-razorpay-event-id": event_id,
        },
    )


def get_payment(client, payment_id):
    db = client.app.state.testing_session_local()

    try:
        return db.get(Payment, payment_id)
    finally:
        db.close()


def get_reservation(client, reservation_id):
    db = client.app.state.testing_session_local()

    try:
        return db.get(Reservation, reservation_id)
    finally:
        db.close()


def get_event_seat(client, event_seat_id):
    db = client.app.state.testing_session_local()

    try:
        return db.get(EventSeat, event_seat_id)
    finally:
        db.close()


def get_webhook_event(client, event_id):
    db = client.app.state.testing_session_local()

    try:
        return db.scalar(
            select(PaymentWebhookEvent).where(
                PaymentWebhookEvent.provider_event_id == event_id
            )
        )
    finally:
        db.close()


def test_captured_webhook_confirms_reservation(
    client,
    auth_headers,
    webhook_configured,
):
    reservation_id, event_seat_id = create_reservation(
        client,
        auth_headers,
    )
    payment_id = create_payment(client, reservation_id)

    response = send_webhook(
        client,
        create_webhook_payload(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "processed"

    payment = get_payment(client, payment_id)
    reservation = get_reservation(client, reservation_id)
    event_seat = get_event_seat(client, event_seat_id)

    assert payment.status == "captured"
    assert payment.provider_payment_id == "pay_webhook_test"
    assert payment.captured_at is not None

    assert reservation.status == "confirmed"
    assert reservation.confirmed_payment_id == payment_id
    assert reservation.confirmed_at is not None

    assert event_seat.status == "booked"

    webhook_event = get_webhook_event(
        client,
        "event_webhook_001",
    )
    assert webhook_event.status == "processed"
    assert webhook_event.processed_at is not None


def test_duplicate_webhook_delivery_is_idempotent(
    client,
    auth_headers,
    webhook_configured,
):
    reservation_id, event_seat_id = create_reservation(
        client,
        auth_headers,
    )
    payment_id = create_payment(client, reservation_id)

    payload = create_webhook_payload()

    first_response = send_webhook(
        client,
        payload,
        event_id="event_duplicate_test",
    )

    second_response = send_webhook(
        client,
        payload,
        event_id="event_duplicate_test",
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["status"] == "already_processed"

    payment = get_payment(client, payment_id)
    reservation = get_reservation(client, reservation_id)
    event_seat = get_event_seat(client, event_seat_id)

    assert payment.status == "captured"
    assert reservation.status == "confirmed"
    assert reservation.confirmed_payment_id == payment_id
    assert event_seat.status == "booked"


def test_out_of_order_authorized_event_does_not_downgrade_capture(
    client,
    auth_headers,
    webhook_configured,
):
    reservation_id, _ = create_reservation(
        client,
        auth_headers,
    )
    payment_id = create_payment(client, reservation_id)

    captured_response = send_webhook(
        client,
        create_webhook_payload(),
        event_id="event_captured_first",
    )

    authorized_payload = create_webhook_payload(
        event_type="payment.authorized",
        payment_status="authorized",
    )

    authorized_response = send_webhook(
        client,
        authorized_payload,
        event_id="event_authorized_later",
    )

    assert captured_response.status_code == 200
    assert authorized_response.status_code == 200

    payment = get_payment(client, payment_id)
    reservation = get_reservation(client, reservation_id)

    assert payment.status == "captured"
    assert reservation.status == "confirmed"

    assert get_webhook_event(
        client,
        "event_authorized_later",
    ).status == "processed"


def test_invalid_webhook_signature_is_rejected(
    client,
    webhook_configured,
):
    response = send_webhook(
        client,
        create_webhook_payload(),
        signature_override="invalid-signature",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Invalid Razorpay webhook signature"
    )

    assert get_webhook_event(
        client,
        "event_webhook_001",
    ) is None


def test_webhook_amount_mismatch_is_retryable(
    client,
    auth_headers,
    webhook_configured,
):
    reservation_id, event_seat_id = create_reservation(
        client,
        auth_headers,
    )
    payment_id = create_payment(client, reservation_id)

    payload = create_webhook_payload(amount=24999)

    response = send_webhook(
        client,
        payload,
        event_id="event_amount_mismatch",
    )

    assert response.status_code == 503

    payment = get_payment(client, payment_id)
    reservation = get_reservation(client, reservation_id)
    event_seat = get_event_seat(client, event_seat_id)

    assert payment.status == "created"
    assert reservation.status == "pending"
    assert event_seat.status == "reserved"

    webhook_event = get_webhook_event(
        client,
        "event_amount_mismatch",
    )

    assert webhook_event.status == "failed"
    assert webhook_event.error_message is not None


def test_unknown_webhook_event_is_acknowledged(
    client,
    webhook_configured,
):
    payload = {
        "entity": "event",
        "event": "some.future.event",
        "payload": {},
    }

    response = send_webhook(
        client,
        payload,
        event_id="event_unknown_type",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "processed"

    webhook_event = get_webhook_event(
        client,
        "event_unknown_type",
    )

    assert webhook_event.status == "processed"


def test_missing_webhook_secret_returns_service_unavailable(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "razorpay_webhook_secret",
        None,
    )

    response = client.post(
        "/webhooks/razorpay",
        content=b'{"event":"payment.captured"}',
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": "a" * 64,
            "x-razorpay-event-id": "event_missing_secret",
        },
    )

    assert response.status_code == 503
