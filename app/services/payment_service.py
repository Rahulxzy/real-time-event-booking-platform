from datetime import datetime, timedelta, timezone
from decimal import Decimal

import razorpay
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import settings
from app.models import Event, EventSeat, Payment, Reservation, ReservationSeat, User

import hashlib
import hmac

CHECKOUT_WINDOW_MINUTES = 10
MAX_RESERVATION_HOLD_MINUTES = 15
ACTIVE_PAYMENT_STATUSES = ("creating", "created", "authorized")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _get_payment_total_paise(db: Session, reservation_id: int) -> int:
    total = db.scalar(
        select(func.sum(ReservationSeat.price)).where(
            ReservationSeat.reservation_id == reservation_id
        )
    )

    if total is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reservation has no seats",
        )

    amount_paise = Decimal(str(total)) * Decimal("100")

    if amount_paise != amount_paise.to_integral_value():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reservation total cannot be represented in paise",
        )

    amount = int(amount_paise)

    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment is not required for a zero-value reservation",
        )

    return amount


def _payment_order_response(payment: Payment) -> dict:
    if not payment.provider_order_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment order is not ready yet",
        )

    return {
        "payment_id": payment.id,
        "reservation_id": payment.reservation_id,
        "order_id": payment.provider_order_id,
        "amount": payment.amount_paise,
        "currency": payment.currency,
        "key_id": settings.razorpay_key_id,
    }


def create_razorpay_order(
    *,
    amount_paise: int,
    currency: str,
    receipt: str,
    notes: dict,
) -> dict:
    """Create a Razorpay order."""
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RuntimeError("Razorpay API credentials are not configured")

    client = razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )

    return client.order.create(
        data={
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "notes": notes,
        }
    )


def fetch_razorpay_orders_by_receipt(receipt: str) -> dict:
    """Fetch Razorpay orders using their receipt."""
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RuntimeError("Razorpay API credentials are not configured")

    client = razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )

    return client.order.all(
        {
            "receipt": receipt,
            "count": 100,
        }
    )


def _get_reconciled_order(
    provider_response: dict,
    *,
    receipt: str,
    payment_id: int,
    reservation_id: int,
    amount_paise: int,
    currency: str,
) -> dict:
    """Validate that exactly one Razorpay order matches our payment attempt."""
    if not isinstance(provider_response, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Razorpay returned an invalid order lookup response",
        )

    items = provider_response.get("items")

    if not isinstance(items, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Razorpay order lookup response did not contain an items list",
        )

    matches = [
        item
        for item in items
        if isinstance(item, dict) and item.get("receipt") == receipt
    ]

    if not matches:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No matching Razorpay order is visible yet. The payment attempt "
                "remains under reconciliation; retry with the same Idempotency-Key."
            ),
        )

    if len(matches) != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Multiple Razorpay orders matched this receipt; "
                "manual reconciliation is required"
            ),
        )

    order = matches[0]
    notes = order.get("notes")

    if (
        not order.get("id")
        or order.get("amount") != amount_paise
        or order.get("currency") != currency
        or not isinstance(notes, dict)
        or str(notes.get("payment_id")) != str(payment_id)
        or str(notes.get("reservation_id")) != str(reservation_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Razorpay order details do not match this payment attempt; "
                "manual reconciliation is required"
            ),
        )

    return order


def _recover_existing_payment_order(
    db: Session,
    *,
    payment_id: int,
    reservation_id: int,
    user: User,
    idempotency_key: str,
) -> dict:
    """Reconcile an uncertain order without creating another Razorpay order."""

    payment_snapshot = db.get(Payment, payment_id)

    if payment_snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment attempt not found",
        )

    receipt = f"eventpay-{payment_snapshot.id}"
    expected_amount = payment_snapshot.amount_paise
    expected_currency = payment_snapshot.currency

    # Network request happens without holding database row locks.
    try:
        provider_response = fetch_razorpay_orders_by_receipt(receipt)

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Could not reconcile the payment attempt with Razorpay. "
                "No new order was created; retry with the same Idempotency-Key."
            ),
        ) from exc

    provider_order = _get_reconciled_order(
        provider_response,
        receipt=receipt,
        payment_id=payment_id,
        reservation_id=reservation_id,
        amount_paise=expected_amount,
        currency=expected_currency,
    )

    try:
        # Reacquire locks in the application-wide order.
        reservation_snapshot = db.get(Reservation, reservation_id)

        if (
            reservation_snapshot is None
            or reservation_snapshot.user_id != user.id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        event = db.scalar(
            select(Event)
            .where(Event.id == reservation_snapshot.event_id)
            .with_for_update()
        )

        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )

        reservation = db.scalar(
            select(Reservation)
            .where(
                Reservation.id == reservation_id,
                Reservation.event_id == event.id,
                Reservation.user_id == user.id,
            )
            .with_for_update()
        )

        payment = db.scalar(
            select(Payment)
            .where(
                Payment.id == payment_id,
                Payment.reservation_id == reservation_id,
                Payment.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )

        if reservation is None or payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment attempt not found",
            )

        if payment.status == "captured":
            db.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Payment has already been captured",
            )

        if payment.status == "created" and payment.provider_order_id:
            db.commit()
            return _payment_order_response(payment)

        if payment.status != "creating":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Payment attempt is no longer eligible for "
                    "automatic reconciliation"
                ),
            )

        # Link the recovered Razorpay order to our local payment.
        payment.provider_order_id = provider_order["id"]
        payment.status = "created"

        order_status = provider_order.get("status")
        amount_paid = provider_order.get("amount_paid", 0)

        db.commit()
        db.refresh(payment)

        # Do not return an order as a fresh checkout if it is already paid
        # or has another unexpected provider state.
        if order_status not in ("created", "attempted") or amount_paid != 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Razorpay order was recovered, but its state requires "
                    "payment reconciliation. Do not start another checkout."
                ),
            )

        now = _as_utc(db.scalar(select(func.now())))

        deadline_value = (
            reservation.checkout_deadline_at
            if reservation.checkout_deadline_at is not None
            else reservation.expires_at
        )

        if (
            reservation.status != "pending"
            or _as_utc(deadline_value) <= now
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Razorpay order was recovered, but the reservation "
                    "checkout window has expired or is no longer pending."
                ),
            )

        return _payment_order_response(payment)

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Razorpay order was found but could not be reconciled locally"
            ),
        )


def _expire_reservation_and_release_seats(
    db: Session,
    reservation: Reservation,
    event: Event,
) -> None:
    """Expire a pending reservation while preserving lock order."""

    reservation.status = "expired"

    event_seat_ids = db.scalars(
        select(ReservationSeat.event_seat_id)
        .where(ReservationSeat.reservation_id == reservation.id)
        .order_by(ReservationSeat.event_seat_id)
    ).all()

    if event_seat_ids:
        event_seats = db.scalars(
            select(EventSeat)
            .where(
                EventSeat.id.in_(event_seat_ids),
                EventSeat.event_id == event.id,
            )
            .order_by(EventSeat.id)
            .with_for_update()
        ).all()

        for event_seat in event_seats:
            if event_seat.status == "reserved":
                event_seat.status = "available"


def create_payment_order(
    db: Session,
    *,
    reservation_id: int,
    user: User,
    idempotency_key: str,
) -> dict:
    """
    Create a Razorpay order with reservation-scoped idempotency.

    Database lock order:
    Event -> Reservation -> Payment.

    The payment row is committed before the external API call.
    """

    key = idempotency_key.strip()

    if not key or len(key) > 255:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Idempotency-Key must contain 1 to 255 "
                "non-whitespace characters"
            ),
        )

    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment provider is not configured",
        )

    try:
        # Initial non-locking read only discovers the event ID.
        initial_reservation = db.get(Reservation, reservation_id)

        if (
            initial_reservation is None
            or initial_reservation.user_id != user.id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        # Preserve lock order: Event first.
        event = db.scalar(
            select(Event)
            .where(Event.id == initial_reservation.event_id)
            .with_for_update()
        )

        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )

        reservation = db.scalar(
            select(Reservation)
            .where(
                Reservation.id == reservation_id,
                Reservation.event_id == event.id,
                Reservation.user_id == user.id,
            )
            .with_for_update()
        )

        if reservation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        # Check the idempotency key before rejecting an expired reservation.
        # An uncertain provider request must still be reconciled.
        existing = db.scalar(
            select(Payment)
            .where(
                Payment.reservation_id == reservation.id,
                Payment.idempotency_key == key,
            )
            .with_for_update()
        )

        if existing is not None:

            if existing.status == "created" and existing.provider_order_id:
                now = _as_utc(db.scalar(select(func.now())))

                deadline_value = (
                    reservation.checkout_deadline_at
                    if reservation.checkout_deadline_at is not None
                    else reservation.expires_at
                )

                if (
                    reservation.status != "pending"
                    or _as_utc(deadline_value) <= now
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Reservation checkout window has expired "
                            "or is no longer pending"
                        ),
                    )

                db.commit()
                return _payment_order_response(existing)

            if existing.status == "captured":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Payment has already been captured",
                )

            if existing.status == "creating":
                existing_payment_id = existing.id

                db.commit()

                return _recover_existing_payment_order(
                    db,
                    payment_id=existing_payment_id,
                    reservation_id=reservation.id,
                    user=user,
                    idempotency_key=key,
                )

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This idempotency key has a payment attempt "
                    "requiring manual reconciliation"
                ),
            )

        if reservation.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot start checkout for a "
                    f"{reservation.status} reservation"
                ),
            )

        now = _as_utc(db.scalar(select(func.now())))

        # An expired initial hold must never be revived.
        if reservation.checkout_deadline_at is None:
            effective_deadline = _as_utc(reservation.expires_at)
        else:
            effective_deadline = _as_utc(
                reservation.checkout_deadline_at
            )

        if effective_deadline <= now:
            _expire_reservation_and_release_seats(
                db,
                reservation,
                event,
            )

            db.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation checkout window has expired",
            )

        # Initialize checkout deadline once. Never extend on retries.
        if reservation.checkout_deadline_at is None:
            created_at = _as_utc(reservation.created_at)

            absolute_deadline = (
                created_at
                + timedelta(minutes=MAX_RESERVATION_HOLD_MINUTES)
            )

            checkout_deadline = now + timedelta(
                minutes=CHECKOUT_WINDOW_MINUTES
            )

            reservation.checkout_deadline_at = min(
                checkout_deadline,
                absolute_deadline,
            )

        deadline = _as_utc(reservation.checkout_deadline_at)

        if deadline <= now:
            _expire_reservation_and_release_seats(
                db,
                reservation,
                event,
            )

            db.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation checkout window has expired",
            )

        # Do not allow a second live order under a different key.
        active_payment = db.scalar(
            select(Payment)
            .where(
                Payment.reservation_id == reservation.id,
                Payment.status.in_(ACTIVE_PAYMENT_STATUSES),
            )
            .order_by(Payment.id.desc())
            .with_for_update()
        )

        if active_payment is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "An existing payment attempt is active. "
                    "Retry with its original Idempotency-Key."
                ),
            )

        amount_paise = _get_payment_total_paise(
            db,
            reservation.id,
        )

        payment = Payment(
            reservation_id=reservation.id,
            provider="razorpay",
            amount_paise=amount_paise,
            currency=settings.razorpay_currency,
            status="creating",
            idempotency_key=key,
        )

        db.add(payment)
        db.flush()

        # Persist idempotency record before calling Razorpay.
        db.commit()
        db.refresh(payment)

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A payment attempt with this idempotency key already exists"
            ),
        )

    except SQLAlchemyError:
        db.rollback()
        raise

    # External API call happens outside the DB transaction.
    try:
        provider_order = create_razorpay_order(
            amount_paise=payment.amount_paise,
            currency=payment.currency,
            receipt=f"eventpay-{payment.id}",
            notes={
                "payment_id": str(payment.id),
                "reservation_id": str(payment.reservation_id),
            },
        )

    except Exception as exc:
        # A timeout may happen after Razorpay created the order.
        # Keep status as creating for later reconciliation.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Payment provider result is uncertain. "
                "Do not create a new payment attempt; retry with the same "
                "Idempotency-Key after reconciliation."
            ),
        ) from exc

    provider_order_id = (
        provider_order.get("id")
        if isinstance(provider_order, dict)
        else None
    )

    if not provider_order_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Payment provider returned an invalid order response. "
                "The payment attempt requires reconciliation."
            ),
        )

    try:
        payment = db.scalar(
            select(Payment)
            .where(Payment.id == payment.id)
            .with_for_update()
        )

        if payment is None:
            raise RuntimeError(
                "Payment attempt disappeared after provider call"
            )

        payment.provider_order_id = provider_order_id
        payment.status = "created"

        db.commit()
        db.refresh(payment)

        return _payment_order_response(payment)

    except Exception:
        db.rollback()

        # Razorpay may already have created the order.
        # Never blindly create another order.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Razorpay order may have been created, but it could not be "
                "saved locally. Payment requires reconciliation."
            ),
        )


def verify_razorpay_checkout_signature(
    *,
    order_id: str,
    payment_id: str,
    signature: str,
) -> bool:
    """
    Verify Razorpay Standard Checkout signature.

    HMAC-SHA256(
        order_id + "|" + payment_id,
        Razorpay API key secret
    )
    """
    if not settings.razorpay_key_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment provider is not configured",
        )

    message = f"{order_id}|{payment_id}"

    expected_signature = hmac.new(
        settings.razorpay_key_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        expected_signature,
        signature.lower(),
    )


def fetch_razorpay_payment(payment_id: str) -> dict:
    """Fetch the latest payment details directly from Razorpay."""

    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RuntimeError("Razorpay API credentials are not configured")

    client = razorpay.Client(
        auth=(
            settings.razorpay_key_id,
            settings.razorpay_key_secret,
        )
    )

    return client.payment.fetch(payment_id)


def verify_checkout_payment(
    db: Session,
    *,
    order_id: str,
    razorpay_payment_id: str,
    signature: str,
    user: User,
) -> dict:
    """
    Verify Razorpay Checkout callback.

    This endpoint records the verified payment state.
    It does NOT confirm the reservation.

    Reservation confirmation is handled by payment.captured webhook.
    """

    # 1. Verify checkout signature first.
    signature_valid = verify_razorpay_checkout_signature(
        order_id=order_id,
        payment_id=razorpay_payment_id,
        signature=signature,
    )

    if not signature_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Razorpay payment signature",
        )

    # 2. Find our local payment attempt.
    payment_snapshot = db.scalar(
        select(Payment).where(
            Payment.provider == "razorpay",
            Payment.provider_order_id == order_id,
        )
    )

    if payment_snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment order not found",
        )

    reservation_snapshot = db.get(
        Reservation,
        payment_snapshot.reservation_id,
    )

    if (
        reservation_snapshot is None
        or reservation_snapshot.user_id != user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment order not found",
        )

    # 3. Fetch payment directly from Razorpay.
    # Never trust payment status or amount sent by frontend.
    try:
        provider_payment = fetch_razorpay_payment(
            razorpay_payment_id
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not verify payment with Razorpay",
        ) from exc

    if not isinstance(provider_payment, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Razorpay returned an invalid payment response",
        )

    # 4. Validate provider response against our local records.
    if (
        provider_payment.get("id") != razorpay_payment_id
        or provider_payment.get("order_id") != order_id
        or provider_payment.get("amount") != payment_snapshot.amount_paise
        or provider_payment.get("currency") != payment_snapshot.currency
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Razorpay payment details do not match our records",
        )

    provider_status = provider_payment.get("status")

    if provider_status not in ("authorized", "captured", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Payment is not in a verifiable state. "
                "Check the payment status with Razorpay."
            ),
        )

    try:
        # 5. Reacquire locks using application-wide lock order:
        # Event -> Reservation -> Payment.

        event = db.scalar(
            select(Event)
            .where(Event.id == reservation_snapshot.event_id)
            .with_for_update()
        )

        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )

        reservation = db.scalar(
            select(Reservation)
            .where(
                Reservation.id == payment_snapshot.reservation_id,
                Reservation.event_id == event.id,
                Reservation.user_id == user.id,
            )
            .with_for_update()
        )

        if reservation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found",
            )

        payment = db.scalar(
            select(Payment)
            .where(
                Payment.id == payment_snapshot.id,
                Payment.reservation_id == reservation.id,
            )
            .with_for_update()
        )

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment attempt not found",
            )

        # 6. Prevent a payment ID from being associated with
        # another local payment attempt.
        existing_payment = db.scalar(
            select(Payment).where(
                Payment.provider_payment_id == razorpay_payment_id,
                Payment.id != payment.id,
            )
        )

        if existing_payment is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This Razorpay payment is already associated with another attempt",
            )

        if (
            payment.provider_order_id != order_id
            or payment.amount_paise != provider_payment["amount"]
            or payment.currency != provider_payment["currency"]
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Local payment details changed during verification",
            )

        if (
            payment.provider_payment_id is not None
            and payment.provider_payment_id != razorpay_payment_id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A different Razorpay payment is already linked",
            )

        # Refunded payments are terminal for this verification flow.
        if payment.status in ("refunded", "partially_refunded"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This payment has already been refunded",
            )

        # 7. Never downgrade a captured payment.
        if payment.status != "captured":
            payment.provider_payment_id = razorpay_payment_id

            if provider_status == "captured":
                payment.status = "captured"

                if payment.captured_at is None:
                    payment.captured_at = _as_utc(
                        db.scalar(select(func.now()))
                    )

            elif provider_status == "authorized":
                payment.status = "authorized"

            elif provider_status == "failed":
                payment.status = "failed"

        db.commit()
        db.refresh(payment)
        db.refresh(reservation)

        if payment.status == "captured":
            message = (
                "Payment verified and captured. "
                "Reservation confirmation is awaiting the payment webhook."
            )
        elif payment.status == "authorized":
            message = (
                "Payment authorized successfully. "
                "Waiting for payment capture and confirmation."
            )
        else:
            message = "Payment failed. You may initiate another payment attempt."

        return {
            "payment_id": payment.id,
            "reservation_id": reservation.id,
            "payment_status": payment.status,
            "reservation_status": reservation.status,
            "message": message,
        }

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save payment verification result",
        ) from exc