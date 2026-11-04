
import hashlib
import hmac
import json

from datetime import timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import settings
from app.models import (
    Event,
    Payment,
    PaymentWebhookEvent,
    Reservation,
)
from app.services.reservation_service import (
    confirm_reservation_from_captured_payment_in_transaction,
)


def verify_razorpay_webhook_signature(
    *,
    raw_body: bytes,
    signature: str,
) -> bool:
    """Verify Razorpay webhook signature using the exact raw request body."""

    if not settings.razorpay_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret is not configured",
        )

    if not signature:
        return False

    expected_signature = hmac.new(
        settings.razorpay_webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        expected_signature,
        signature.lower(),
    )


def _database_now(db: Session):
    now = db.scalar(select(func.now()))

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    return now


def _persist_webhook_event(
    db: Session,
    *,
    provider_event_id: str,
    event_type: str,
    payload: dict,
) -> PaymentWebhookEvent:
    """
    Persist the event before processing it.

    The unique provider event ID protects against concurrent duplicate
    deliveries.
    """

    webhook_event = PaymentWebhookEvent(
        provider_event_id=provider_event_id,
        event_type=event_type,
        payload=payload,
        status="received",
    )

    try:
        db.add(webhook_event)
        db.commit()
        db.refresh(webhook_event)
        return webhook_event

    except IntegrityError:
        db.rollback()

        existing_event = db.scalar(
            select(PaymentWebhookEvent).where(
                PaymentWebhookEvent.provider_event_id
                == provider_event_id
            )
        )

        if existing_event is None:
            raise

        return existing_event


def _extract_payment_entity(payload: dict) -> dict:
    """Extract the payment entity from a Razorpay webhook payload."""

    payment_payload = payload.get("payload", {}).get("payment", {})
    entity = payment_payload.get("entity")

    if not isinstance(entity, dict):
        raise ValueError("Webhook does not contain a valid payment entity")

    required_fields = ("id", "order_id", "amount", "currency")

    if any(entity.get(field) is None for field in required_fields):
        raise ValueError("Webhook payment entity is missing required fields")

    return entity


def _process_payment_event(
    db: Session,
    *,
    event_type: str,
    payload: dict,
) -> str | None:
    """
    Process a supported payment event.

    Lock order:
    Event -> Reservation -> Payment -> EventSeat.

    Returns an optional reconciliation note.
    """

    target_status = {
        "payment.authorized": "authorized",
        "payment.captured": "captured",
        "payment.failed": "failed",
    }.get(event_type)

    # Unknown events are safely acknowledged without payment changes.
    if target_status is None:
        return None

    entity = _extract_payment_entity(payload)

    provider_order_id = entity["order_id"]
    provider_payment_id = entity["id"]
    amount_paise = entity["amount"]
    currency = entity["currency"]

    if (
        not isinstance(amount_paise, int)
        or isinstance(amount_paise, bool)
        or amount_paise <= 0
    ):
        raise ValueError("Webhook payment amount is invalid")

    if currency != "INR":
        raise ValueError("Webhook payment currency is not supported")

    # Find the local payment without acquiring a row lock.
    payment_snapshot = db.scalar(
        select(Payment).where(
            Payment.provider == "razorpay",
            Payment.provider_order_id == provider_order_id,
        )
    )

    if payment_snapshot is None:
        raise ValueError("No local payment matches the Razorpay order")

    reservation_snapshot = db.get(
        Reservation,
        payment_snapshot.reservation_id,
    )

    if reservation_snapshot is None:
        raise ValueError("Payment reservation does not exist")

    # Acquire locks in the application's established order.
    event = db.scalar(
        select(Event)
        .where(Event.id == reservation_snapshot.event_id)
        .with_for_update()
    )

    if event is None:
        raise ValueError("Payment event does not exist")

    reservation = db.scalar(
        select(Reservation)
        .where(
            Reservation.id == payment_snapshot.reservation_id,
            Reservation.event_id == event.id,
        )
        .with_for_update()
    )

    if reservation is None:
        raise ValueError("Payment reservation does not exist")

    payment = db.scalar(
        select(Payment)
        .where(
            Payment.id == payment_snapshot.id,
            Payment.reservation_id == reservation.id,
        )
        .with_for_update()
    )

    if payment is None:
        raise ValueError("Local payment attempt does not exist")

    # Verify provider data against our trusted local order.
    if (
        payment.provider_order_id != provider_order_id
        or payment.amount_paise != amount_paise
        or payment.currency != currency
    ):
        raise ValueError("Webhook payment details do not match local records")

    existing_payment = db.scalar(
        select(Payment).where(
            Payment.provider_payment_id == provider_payment_id,
            Payment.id != payment.id,
        )
    )

    if existing_payment is not None:
        raise ValueError(
            "Razorpay payment ID is already associated with another attempt"
        )

    if (
        payment.provider_payment_id is not None
        and payment.provider_payment_id != provider_payment_id
    ):
        raise ValueError(
            "A different Razorpay payment is already linked to this attempt"
        )

    # Refunded payments are not changed by older payment events.
    if payment.status in ("refunded", "partially_refunded"):
        return "Payment is already refunded; reconciliation may be required"

    # A captured payment must never be downgraded by stale events.
    if payment.status == "captured" and target_status != "captured":
        return None

    # A late authorization event must not undo a failed payment.
    if payment.status == "failed" and target_status == "authorized":
        return None

    payment.provider_payment_id = provider_payment_id

    if target_status == "authorized":
        if payment.status in ("creating", "created", "authorized"):
            payment.status = "authorized"

    elif target_status == "failed":
        if payment.status != "captured":
            payment.status = "failed"

            error_code = entity.get("error_code")
            error_description = entity.get("error_description")

            payment.failure_code = (
                str(error_code)[:100] if error_code else None
            )
            payment.failure_description = (
                str(error_description) if error_description else None
            )

    elif target_status == "captured":
        payment.status = "captured"

        if payment.captured_at is None:
            payment.captured_at = _database_now(db)

        db.flush()

        # Critical case:
        # Another payment may already have confirmed this reservation.
        # Never confirm the same reservation using a second payment.
        if reservation.status == "confirmed":
            if reservation.confirmed_payment_id == payment.id:
                return None

            return (
                "Payment captured, but reservation is already confirmed "
                "by another payment. Refund or reconciliation is required."
            )

        reservation, outcome = (
            confirm_reservation_from_captured_payment_in_transaction(
                db,
                reservation.id,
                payment.id,
            )
        )

        if outcome == "expired":
            return (
                "Payment captured after reservation expiry. "
                "Reservation expired and seats were released; "
                "refund or reconciliation is required."
            )

        if outcome == "already_confirmed":
            return None

    return None


def process_razorpay_webhook(
    db: Session,
    *,
    raw_body: bytes,
    signature: str,
    provider_event_id: str,
) -> dict:
    """
    Verify, persist and process a Razorpay webhook.

    The inbox insert is committed first.
    Payment changes, reservation changes and the processed event status
    are committed together in the processing transaction.
    """

    if not provider_event_id or len(provider_event_id) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Razorpay event ID",
        )

    if not verify_razorpay_webhook_signature(
        raw_body=raw_body,
        signature=signature,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Razorpay webhook signature",
        )

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook JSON payload",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        )

    event_type = payload.get("event")

    if not isinstance(event_type, str) or not event_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook event type is missing",
        )

    if len(event_type) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook event type is invalid",
        )

    # Commit the durable inbox entry before attempting processing.
    try:
        webhook_event = _persist_webhook_event(
            db,
            provider_event_id=provider_event_id,
            event_type=event_type,
            payload=payload,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not persist webhook event",
        ) from exc

    try:
        # Serialize concurrent processing of the same event.
        webhook_event = db.scalar(
            select(PaymentWebhookEvent)
            .where(PaymentWebhookEvent.id == webhook_event.id)
            .with_for_update()
        )

        if webhook_event is None:
            raise RuntimeError("Persisted webhook event could not be loaded")

        # A successfully processed duplicate is an idempotent no-op.
        if webhook_event.status == "processed":
            db.rollback()

            return {
                "status": "already_processed",
                "event_id": provider_event_id,
            }

        reconciliation_note = _process_payment_event(
            db,
            event_type=webhook_event.event_type,
            payload=webhook_event.payload,
        )

        webhook_event.status = "processed"
        webhook_event.processed_at = _database_now(db)
        webhook_event.error_message = reconciliation_note

        # Atomic commit:
        # payment + reservation + seat + webhook status.
        db.commit()

        return {
            "status": "processed",
            "event_id": provider_event_id,
            "reconciliation_required": reconciliation_note is not None,
        }

    except Exception as exc:
        # Roll back all business changes. The inbox row was committed
        # separately and remains available for a retry.
        db.rollback()

        try:
            failed_event = db.scalar(
                select(PaymentWebhookEvent)
                .where(
                    PaymentWebhookEvent.provider_event_id
                    == provider_event_id
                )
                .with_for_update()
            )

            if failed_event is not None and failed_event.status != "processed":
                failed_event.status = "failed"
                failed_event.error_message = str(exc)[:4000]
                db.commit()
            else:
                db.rollback()

        except Exception:
            db.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook processing failed; retry is safe",
        ) from exc
