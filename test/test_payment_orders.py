from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.database import settings
from app.models import Payment, Reservation
from app.services import payment_service


def create_reservation(client, auth_headers, price="250.00"):
    venue_response = client.post(
        "/venues",
        json={
            "name": "Payment Test Cinema",
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
            "title": "Payment Test Event",
            "description": "Testing payment orders",
            "starts_at": "2027-01-15T18:00:00+05:30",
            "ends_at": "2027-01-15T21:00:00+05:30",
            "price": price,
            "capacity": 1,
        },
        headers=auth_headers,
    )
    assert event_response.status_code == 201
    event_id = event_response.json()["id"]

    seat_response = client.post(
        f"/venues/{venue_id}/seats",
        json={"row_label": "A", "seat_number": 1},
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

    return reservation_response.json()["id"]


@pytest.fixture
def razorpay_configured(monkeypatch):
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_public_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "test_secret")
    monkeypatch.setattr(settings, "razorpay_currency", "INR")


def order_request(
    client,
    auth_headers,
    reservation_id,
    key="checkout-key-001",
):
    return client.post(
        "/payments/orders",
        json={"reservation_id": reservation_id},
        headers={
            **auth_headers,
            "Idempotency-Key": key,
        },
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


def make_provider_order(payment):
    return {
        "id": f"order_recovered_{payment.id}",
        "receipt": f"eventpay-{payment.id}",
        "amount": payment.amount_paise,
        "currency": payment.currency,
        "status": "created",
        "amount_paid": 0,
        "notes": {
            "payment_id": str(payment.id),
            "reservation_id": str(payment.reservation_id),
        },
    }


def test_create_payment_order_success(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)
    provider_calls = []

    def fake_create_order(**kwargs):
        provider_calls.append(kwargs)
        return {"id": "order_test_123"}

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        fake_create_order,
    )

    response = order_request(
        client,
        auth_headers,
        reservation_id,
    )

    assert response.status_code == 201
    body = response.json()

    assert body["reservation_id"] == reservation_id
    assert body["order_id"] == "order_test_123"
    assert body["amount"] == 25000
    assert body["currency"] == "INR"
    assert body["key_id"] == "rzp_test_public_key"

    assert len(provider_calls) == 1
    assert provider_calls[0]["amount_paise"] == 25000
    assert provider_calls[0]["currency"] == "INR"
    assert provider_calls[0]["receipt"].startswith("eventpay-")

    db = client.app.state.testing_session_local()
    try:
        payment = db.scalar(
            select(Payment).where(
                Payment.reservation_id == reservation_id
            )
        )
        reservation = db.get(Reservation, reservation_id)

        assert payment is not None
        assert payment.status == "created"
        assert payment.provider_order_id == "order_test_123"
        assert payment.amount_paise == 25000
        assert payment.idempotency_key == "checkout-key-001"
        assert reservation.checkout_deadline_at is not None
    finally:
        db.close()


def test_same_idempotency_key_reuses_existing_order(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)
    provider_calls = []

    def fake_create_order(**kwargs):
        provider_calls.append(kwargs)
        return {"id": "order_reused_123"}

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        fake_create_order,
    )

    first = order_request(
        client,
        auth_headers,
        reservation_id,
        key="same-key",
    )
    second = order_request(
        client,
        auth_headers,
        reservation_id,
        key="same-key",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["order_id"] == second.json()["order_id"]
    assert len(provider_calls) == 1


def test_different_key_cannot_create_second_active_order(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        lambda **kwargs: {"id": "order_active_123"},
    )

    first = order_request(
        client,
        auth_headers,
        reservation_id,
        key="first-key",
    )
    second = order_request(
        client,
        auth_headers,
        reservation_id,
        key="second-key",
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert "existing payment attempt is active" in second.json()["detail"]


def test_payment_order_requires_authentication(client):
    response = client.post(
        "/payments/orders",
        json={"reservation_id": 1},
        headers={"Idempotency-Key": "no-auth"},
    )

    assert response.status_code == 401


def test_user_cannot_create_order_for_another_users_reservation(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)

    register = client.post(
        "/auth/register",
        json={
            "email": "other-payment-user@example.com",
            "password": "StrongPass123",
        },
    )
    assert register.status_code == 201

    login = client.post(
        "/auth/login",
        json={
            "email": "other-payment-user@example.com",
            "password": "StrongPass123",
        },
    )
    assert login.status_code == 200

    other_headers = {
        "Authorization": f"Bearer {login.json()['access_token']}"
    }

    provider_calls = []

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        lambda **kwargs: provider_calls.append(kwargs),
    )

    response = order_request(
        client,
        other_headers,
        reservation_id,
    )

    assert response.status_code == 404
    assert provider_calls == []


def test_missing_provider_credentials_returns_503(
    client,
    auth_headers,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)

    monkeypatch.setattr(settings, "razorpay_key_id", None)
    monkeypatch.setattr(settings, "razorpay_key_secret", None)

    response = order_request(
        client,
        auth_headers,
        reservation_id,
    )

    assert response.status_code == 503


def test_provider_error_keeps_attempt_in_creating_state(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)

    def provider_timeout(**kwargs):
        raise TimeoutError("simulated provider timeout")

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        provider_timeout,
    )

    response = order_request(
        client,
        auth_headers,
        reservation_id,
        key="uncertain-key",
    )

    assert response.status_code == 502

    payment = get_payment(client, reservation_id)

    assert payment is not None
    assert payment.status == "creating"
    assert payment.provider_order_id is None


def test_recovery_finds_existing_razorpay_order(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        lambda **kwargs: (_ for _ in ()).throw(
            TimeoutError("simulated timeout")
        ),
    )

    first = order_request(
        client,
        auth_headers,
        reservation_id,
        key="recovery-key",
    )

    assert first.status_code == 502

    payment = get_payment(client, reservation_id)
    assert payment.status == "creating"

    provider_order = make_provider_order(payment)

    lookup_calls = []

    def fake_fetch(receipt):
        lookup_calls.append(receipt)
        return {"items": [provider_order]}

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_orders_by_receipt",
        fake_fetch,
    )

    retry = order_request(
        client,
        auth_headers,
        reservation_id,
        key="recovery-key",
    )

    assert retry.status_code == 201
    assert retry.json()["order_id"] == provider_order["id"]
    assert lookup_calls == [f"eventpay-{payment.id}"]

    recovered = get_payment(client, reservation_id)

    assert recovered.status == "created"
    assert recovered.provider_order_id == provider_order["id"]


def test_recovery_with_no_matching_order_keeps_creating_state(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        lambda **kwargs: (_ for _ in ()).throw(
            TimeoutError("simulated timeout")
        ),
    )

    first = order_request(
        client,
        auth_headers,
        reservation_id,
        key="missing-order-key",
    )

    assert first.status_code == 502

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_orders_by_receipt",
        lambda receipt: {"items": []},
    )

    retry = order_request(
        client,
        auth_headers,
        reservation_id,
        key="missing-order-key",
    )

    assert retry.status_code == 409
    assert "No matching Razorpay order" in retry.json()["detail"]

    payment = get_payment(client, reservation_id)

    assert payment.status == "creating"
    assert payment.provider_order_id is None


def test_recovery_rejects_mismatched_amount(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        lambda **kwargs: (_ for _ in ()).throw(TimeoutError()),
    )

    order_request(
        client,
        auth_headers,
        reservation_id,
        key="mismatch-key",
    )

    payment = get_payment(client, reservation_id)
    provider_order = make_provider_order(payment)
    provider_order["amount"] = 100

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_orders_by_receipt",
        lambda receipt: {"items": [provider_order]},
    )

    retry = order_request(
        client,
        auth_headers,
        reservation_id,
        key="mismatch-key",
    )

    assert retry.status_code == 409
    assert "do not match" in retry.json()["detail"]

    recovered = get_payment(client, reservation_id)

    assert recovered.status == "creating"
    assert recovered.provider_order_id is None


def test_recovery_rejects_multiple_matching_orders(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        lambda **kwargs: (_ for _ in ()).throw(TimeoutError()),
    )

    order_request(
        client,
        auth_headers,
        reservation_id,
        key="duplicate-receipt-key",
    )

    payment = get_payment(client, reservation_id)
    provider_order = make_provider_order(payment)

    second_order = {
        **provider_order,
        "id": "order_duplicate",
    }

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_orders_by_receipt",
        lambda receipt: {
            "items": [provider_order, second_order]
        },
    )

    retry = order_request(
        client,
        auth_headers,
        reservation_id,
        key="duplicate-receipt-key",
    )

    assert retry.status_code == 409
    assert "Multiple Razorpay orders" in retry.json()["detail"]


def test_recovery_provider_lookup_failure_keeps_attempt(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        lambda **kwargs: (_ for _ in ()).throw(TimeoutError()),
    )

    order_request(
        client,
        auth_headers,
        reservation_id,
        key="lookup-failure-key",
    )

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_orders_by_receipt",
        lambda receipt: (_ for _ in ()).throw(
            TimeoutError("Razorpay lookup timeout")
        ),
    )

    retry = order_request(
        client,
        auth_headers,
        reservation_id,
        key="lookup-failure-key",
    )

    assert retry.status_code == 502

    payment = get_payment(client, reservation_id)

    assert payment.status == "creating"
    assert payment.provider_order_id is None


def test_recovery_rejects_paid_order_for_checkout(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        lambda **kwargs: (_ for _ in ()).throw(TimeoutError()),
    )

    order_request(
        client,
        auth_headers,
        reservation_id,
        key="paid-order-key",
    )

    payment = get_payment(client, reservation_id)
    provider_order = make_provider_order(payment)

    provider_order["status"] = "paid"
    provider_order["amount_paid"] = payment.amount_paise

    monkeypatch.setattr(
        payment_service,
        "fetch_razorpay_orders_by_receipt",
        lambda receipt: {"items": [provider_order]},
    )

    retry = order_request(
        client,
        auth_headers,
        reservation_id,
        key="paid-order-key",
    )

    assert retry.status_code == 409

    recovered = get_payment(client, reservation_id)

    # The order is linked locally, but checkout is not restarted.
    assert recovered.provider_order_id == provider_order["id"]
    assert recovered.status == "created"


def test_zero_amount_reservation_is_rejected(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(
        client,
        auth_headers,
        price="0.00",
    )

    provider_calls = []

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        lambda **kwargs: provider_calls.append(kwargs),
    )

    response = order_request(
        client,
        auth_headers,
        reservation_id,
    )

    assert response.status_code == 409
    assert "zero-value" in response.json()["detail"]
    assert provider_calls == []

    payment = get_payment(client, reservation_id)
    assert payment is None


def test_invalid_or_blank_idempotency_key_is_rejected(
    client,
    auth_headers,
):
    reservation_id = create_reservation(client, auth_headers)

    response = client.post(
        "/payments/orders",
        json={"reservation_id": reservation_id},
        headers={
            **auth_headers,
            "Idempotency-Key": "   ",
        },
    )

    assert response.status_code == 422


def test_checkout_cannot_revive_expired_initial_hold(
    client,
    auth_headers,
    razorpay_configured,
    monkeypatch,
):
    reservation_id = create_reservation(client, auth_headers)

    db = client.app.state.testing_session_local()

    try:
        now = db.scalar(select(func.now()))
        reservation = db.get(Reservation, reservation_id)

        reservation.expires_at = now - timedelta(minutes=1)
        db.commit()

    finally:
        db.close()

    provider_calls = []

    monkeypatch.setattr(
        payment_service,
        "create_razorpay_order",
        lambda **kwargs: provider_calls.append(kwargs),
    )

    response = order_request(
        client,
        auth_headers,
        reservation_id,
        key="too-late-key",
    )

    assert response.status_code == 409
    assert "expired" in response.json()["detail"].lower()
    assert provider_calls == []

    db = client.app.state.testing_session_local()

    try:
        reservation = db.get(Reservation, reservation_id)

        assert reservation.status == "expired"
        assert reservation.checkout_deadline_at is None

        event_seat_id = db.scalar(
            select(
                # Get the reservation's associated event seat.
                # The relationship is queried through ReservationSeat below.
                Reservation.id
            ).where(Reservation.id == reservation_id)
        )
        assert event_seat_id == reservation_id

    finally:
        db.close()

    seats = client.get(
        f"/events/{reservation.event_id}/seats"
    ).json()

    assert seats[0]["status"] == "available"