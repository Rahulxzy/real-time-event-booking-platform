
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.database import settings

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Return True if the password matches the stored hash."""
    try:
        password_hasher.verify(hashed_password, password)
        return True
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(subject: str) -> str:
    """Create a signed JWT access token for a user."""
    now = datetime.now(timezone.utc)

    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(
            minutes=settings.access_token_expire_minutes
        ),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def verify_access_token(token: str) -> dict:
    """Verify a JWT and return its claims."""
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "iat", "exp"]},
    )
