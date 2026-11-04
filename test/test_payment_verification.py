
import hashlib
import hmac

import pytest

from sqlalchemy import select

from app.database import settings
from app.models import Payment, Reservation
from app.services import payment_service


@pytest.fixture
def razorpay_configured(monkeypatch):
    monkeypatch.setattr(
        settings,
        "razorpay_key_id",
        "rzp_test_public_key",
    )
    monkeypatch.setattr(
        settings,
        "razorpay_key_secret",
        "test_secret",
    )
    monkeypatch.setattr(
        settings,
        "razorpay_currency",
        "INR",
    )


def create_reservation(client, auth_headers):
    venue_response = client.post(
        "/venues",
        json={
            "name": "Verification Test Cinema",
            "address": "123 Payment Street",
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
            "title": "Verification Test Event",
            "description": "Payment verification testing",
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

    seats_response = client.get(
        f"/events/{event_id}/seats"
    )
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

    return reservation_response.json()["id"]


def create_local_payment(
    client,
    auth_headers,
    reservation_id,
    monkeypatch,
):
    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        lambda **kwargs: {"id": "order_test_123"},
    )

    response = client.post(
        "/payments/orders",
        json={"reservation_id": reservation_id},
        headers={
            **auth_headers,
            "Idempotency-Key": "verification-test-key",
        },
    )

    assert response.status_code == 201

    return response.json()


def generate_signature(
    order_id,
    payment_id,
    secret="test_secret",
):
    message = f"{order_id}|{payment_id}"

    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verification_request(
    client,
    auth_headers,
    order_id="order_test_123",
    payment_id="pay_test_123",
    signature=None,
):
    if signature is None:
        signature = generate_signature(
            order_id,
            payment_id,
        )

    return client.post(
        "/payments/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        },
        headers=auth_headers,
    )


def get_payment(client, reservation_id):
    db = client.app.state.testing_session_local()

    try:
        return db.scalar(
            select(Payment).where(
                Payment.reservation_id == reservation_id
            )
        )
    finally:
        db.close()


def get_reservation(client, reservation_id):
    db = client.app.state.testing_session_local()

    try:
        return db.get(Reservation, reservation_id)
    finally:
        db.close()


def test_valid_signature_verifies_authorized_payment(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(
        client,
        auth_headers,
    )

    create_local_payment(
        client,
        auth_headers,
        reservation_id,
        monkeypatch,
    )

    provider_calls = []

    def fake_fetch(payment_id):
        provider_calls.append(payment_id)

        return {
            "id": "pay_test_123",
            "order_id": "order_test_123",
            "amount": 25000,
            "currency": "INR",
            "status": "authorized",
        }

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_payment",
        fake_fetch,
    )

    response = verification_request(
        client,
        auth_headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["reservation_id"] == reservation_id
    assert body["payment_status"] == "authorized"
    assert body["reservation_status"] == "pending"

    assert provider_calls == ["pay_test_123"]

    payment = get_payment(client, reservation_id)

    assert payment.provider_payment_id == "pay_test_123"
    assert payment.status == "authorized"

    reservation = get_reservation(client, reservation_id)

    assert reservation.status == "pending"


def test_invalid_signature_is_rejected_before_provider_fetch(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(
        client,
        auth_headers,
    )

    create_local_payment(
        client,
        auth_headers,
        reservation_id,
        monkeypatch,
    )

    provider_calls = []

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_payment",
        lambda payment_id: provider_calls.append(payment_id),
    )

    response = verification_request(
        client,
        auth_headers,
        signature="f" * 64,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Invalid Razorpay payment signature"
    )

    assert provider_calls == []

    payment = get_payment(client, reservation_id)

    assert payment.status == "created"
    assert payment.provider_payment_id is None


def test_provider_amount_mismatch_is_rejected(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(
        client,
        auth_headers,
    )

    create_local_payment(
        client,
        auth_headers,
        reservation_id,
        monkeypatch,
    )

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_payment",
        lambda payment_id: {
            "id": "pay_test_123",
            "order_id": "order_test_123",
            "amount": 24999,
            "currency": "INR",
            "status": "authorized",
        },
    )

    response = verification_request(
        client,
        auth_headers,
    )

    assert response.status_code == 409
    assert "do not match" in response.json()["detail"]

    payment = get_payment(client, reservation_id)

    assert payment.status == "created"
    assert payment.provider_payment_id is None


def test_provider_order_mismatch_is_rejected(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(
        client,
        auth_headers,
    )

    create_local_payment(
        client,
        auth_headers,
        reservation_id,
        monkeypatch,
    )

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_payment",
        lambda payment_id: {
            "id": "pay_test_123",
            "order_id": "order_wrong_123",
            "amount": 25000,
            "currency": "INR",
            "status": "authorized",
        },
    )

    response = verification_request(
        client,
        auth_headers,
    )

    assert response.status_code == 409

    payment = get_payment(client, reservation_id)

    assert payment.status == "created"
    assert payment.provider_payment_id is None


def test_captured_payment_does_not_directly_confirm_reservation(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(
        client,
        auth_headers,
    )

    create_local_payment(
        client,
        auth_headers,
        reservation_id,
        monkeypatch,
    )

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_payment",
        lambda payment_id: {
            "id": "pay_test_123",
            "order_id": "order_test_123",
            "amount": 25000,
            "currency": "INR",
            "status": "captured",
        },
    )

    response = verification_request(
        client,
        auth_headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["payment_status"] == "captured"
    assert body["reservation_status"] == "pending"

    payment = get_payment(client, reservation_id)

    assert payment.status == "captured"
    assert payment.provider_payment_id == "pay_test_123"
    assert payment.captured_at is not None

    reservation = get_reservation(client, reservation_id)

    assert reservation.status == "pending"
    assert reservation.confirmed_at is None


def test_payment_verification_requires_authentication(client):
    response = client.post(
        "/payments/verify",
        json={
            "razorpay_order_id": "order_test_123",
            "razorpay_payment_id": "pay_test_123",
            "razorpay_signature": "f" * 64,
        },
    )

    assert response.status_code == 401


def test_unsupported_provider_payment_status_is_rejected(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(
        client,
        auth_headers,
    )

    create_local_payment(
        client,
        auth_headers,
        reservation_id,
        monkeypatch,
    )

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_payment",
        lambda payment_id: {
            "id": "pay_test_123",
            "order_id": "order_test_123",
            "amount": 25000,
            "currency": "INR",
            "status": "created",
        },
    )

    response = verification_request(
        client,
        auth_headers,
    )

    assert response.status_code == 409

    payment = get_payment(client, reservation_id)

    assert payment.status == "created"
    assert payment.provider_payment_id is None
