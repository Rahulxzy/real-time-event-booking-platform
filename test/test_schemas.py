
import pytest
from pydantic import ValidationError

from app.schemas import UserCreate


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
