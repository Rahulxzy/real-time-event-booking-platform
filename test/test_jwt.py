
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.database import settings
from app.security import create_access_token, verify_access_token


def test_create_access_token_contains_expected_claims():
    token = create_access_token("123")

    claims = verify_access_token(token)

    assert claims["sub"] == "123"
    assert "iat" in claims
    assert "exp" in claims


def test_invalid_token_is_rejected():
    with pytest.raises(jwt.InvalidTokenError):
        verify_access_token("not.a.valid.token")


def test_token_signed_with_wrong_secret_is_rejected():
    token = jwt.encode(
        {
            "sub": "123",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "this-is-a-different-test-secret-key",
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.InvalidTokenError):
        verify_access_token(token)


def test_expired_token_is_rejected():
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "123",
            "iat": now - timedelta(minutes=10),
            "exp": now - timedelta(minutes=5),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        verify_access_token(token)
