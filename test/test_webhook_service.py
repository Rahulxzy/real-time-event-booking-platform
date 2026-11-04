
import hashlib
import hmac

import pytest
from fastapi import HTTPException

from app.database import settings
from app.services.webhook_service import (
    verify_razorpay_webhook_signature,
)


@pytest.fixture
def webhook_secret(monkeypatch):
    monkeypatch.setattr(
        settings,
        "razorpay_webhook_secret",
        "test_webhook_secret",
    )


def generate_signature(
    body: bytes,
    secret: str = "test_webhook_secret",
) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


def test_valid_webhook_signature(webhook_secret):
    raw_body = b'{"event":"payment.captured"}'

    signature = generate_signature(raw_body)

    assert verify_razorpay_webhook_signature(
        raw_body=raw_body,
        signature=signature,
    ) is True


def test_invalid_webhook_signature_is_rejected(webhook_secret):
    raw_body = b'{"event":"payment.captured"}'

    assert verify_razorpay_webhook_signature(
        raw_body=raw_body,
        signature="f" * 64,
    ) is False


def test_modified_body_invalidates_signature(webhook_secret):
    original_body = b'{"event":"payment.captured"}'
    modified_body = b'{"event":"payment.failed"}'

    signature = generate_signature(original_body)

    assert verify_razorpay_webhook_signature(
        raw_body=modified_body,
        signature=signature,
    ) is False


def test_missing_signature_is_rejected(webhook_secret):
    assert verify_razorpay_webhook_signature(
        raw_body=b'{"event":"payment.captured"}',
        signature="",
    ) is False


def test_missing_webhook_secret_returns_503(monkeypatch):
    monkeypatch.setattr(
        settings,
        "razorpay_webhook_secret",
        None,
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_razorpay_webhook_signature(
            raw_body=b'{"event":"payment.captured"}',
            signature="a" * 64,
        )

    assert exc_info.value.status_code == 503
