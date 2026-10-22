
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pydantic import ValidationError

from app.schemas import EventCreate, EventUpdate, UserCreate


def test_valid_user_registration_data():
    user = UserCreate(
        email="rahul@example.com",
        password="StrongPass123",
    )

    assert user.email == "rahul@example.com"
    assert user.password == "StrongPass123"


def test_invalid_email_is_rejected():
    with pytest.raises(ValidationError):
        UserCreate(email="invalid-email", password="StrongPass123")


def test_short_password_is_rejected():
    with pytest.raises(ValidationError):
        UserCreate(email="rahul@example.com", password="short")


def valid_event_data():
    now = datetime.now(timezone.utc)

    return {
        "venue_id": 1,
        "title": "Python Conference",
        "description": "A developer conference",
        "starts_at": now + timedelta(days=1),
        "ends_at": now + timedelta(days=1, hours=3),
        "price": Decimal("499.99"),
        "capacity": 100,
    }


def test_valid_event_data():
    event = EventCreate(**valid_event_data())

    assert event.venue_id == 1
    assert event.title == "Python Conference"
    assert event.price == Decimal("499.99")
    assert event.capacity == 100


@pytest.mark.parametrize("price", ["-1.00", "-0.01"])
def test_negative_event_price_is_rejected(price):
    data = valid_event_data()
    data["price"] = Decimal(price)

    with pytest.raises(ValidationError):
        EventCreate(**data)


@pytest.mark.parametrize("capacity", [0, -1])
def test_invalid_event_capacity_is_rejected(capacity):
    data = valid_event_data()
    data["capacity"] = capacity

    with pytest.raises(ValidationError):
        EventCreate(**data)


def test_event_end_before_start_is_rejected():
    data = valid_event_data()
    data["ends_at"] = data["starts_at"] - timedelta(minutes=1)

    with pytest.raises(ValidationError):
        EventCreate(**data)


def test_event_end_equal_to_start_is_rejected():
    data = valid_event_data()
    data["ends_at"] = data["starts_at"]

    with pytest.raises(ValidationError):
        EventCreate(**data)


def test_event_without_timezone_is_rejected():
    data = valid_event_data()
    data["starts_at"] = datetime(2026, 11, 10, 18, 0)

    with pytest.raises(ValidationError):
        EventCreate(**data)


def test_event_update_accepts_partial_data():
    update = EventUpdate(title="Updated Conference")

    assert update.title == "Updated Conference"
    assert update.price is None


def test_event_update_rejects_negative_price():
    with pytest.raises(ValidationError):
        EventUpdate(price=Decimal("-10.00"))


def test_event_update_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        EventUpdate(starts_at=datetime(2026, 11, 10, 18, 0))


def test_event_update_rejects_invalid_time_range_when_both_provided():
    now = datetime.now(timezone.utc)

    with pytest.raises(ValidationError):
        EventUpdate(
            starts_at=now + timedelta(hours=3),
            ends_at=now + timedelta(hours=1),
        )
