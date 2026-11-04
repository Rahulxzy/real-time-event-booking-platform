
from datetime import timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Event,
    EventSeat,
    Payment,
    Reservation,
    ReservationSeat,
)


def confirm_reservation_from_captured_payment_in_transaction(
    db: Session,
    reservation_id: int,
    payment_id: int,
) -> tuple[Reservation, str]:
    """
    Confirm a reservation inside the caller's transaction.

    Returns:
        (reservation, "confirmed")
        (reservation, "already_confirmed")
        (reservation, "expired")

    This function never commits or rolls back. The caller owns
    the transaction.

    Lock order:
    Event -> Reservation -> Payment -> EventSeat.
    """

    # 1. Read reservation to identify its event.
    initial_reservation = db.get(Reservation, reservation_id)

    if initial_reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )

    # 2. Lock event first.
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

    # 3. Lock reservation.
    reservation = db.scalar(
        select(Reservation)
        .where(
            Reservation.id == reservation_id,
            Reservation.event_id == event.id,
        )
        .with_for_update()
    )

    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )

    # 4. Lock and validate the associated payment.
    payment = db.scalar(
        select(Payment)
        .where(
            Payment.id == payment_id,
            Payment.reservation_id == reservation.id,
        )
        .with_for_update()
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found for this reservation",
        )

    if payment.status != "captured":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Reservation cannot be confirmed "
                "without a captured payment"
            ),
        )

    if payment.currency != "INR":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment currency does not match reservation currency",
        )

    # 5. Idempotency check.
    if reservation.status == "confirmed":
        if reservation.confirmed_payment_id == payment.id:
            return reservation, "already_confirmed"

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Reservation is already confirmed "
                "by a different payment"
            ),
        )

    if reservation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot confirm a {reservation.status} reservation",
        )

    # 6. Calculate reservation total from stored price snapshots.
    reservation_total = db.scalar(
        select(func.sum(ReservationSeat.price)).where(
            ReservationSeat.reservation_id == reservation.id
        )
    )

    if reservation_total is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reservation has no seats",
        )

    reservation_total = Decimal(str(reservation_total))
    expected_amount_paise = int(reservation_total * 100)

    if payment.amount_paise != expected_amount_paise:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment amount does not match reservation total",
        )

    # 7. Get database time and normalize timezone.
    now = db.scalar(select(func.now()))

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    deadline = (
        reservation.checkout_deadline_at
        if reservation.checkout_deadline_at is not None
        else reservation.expires_at
    )

    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    # 8. Handle an expired reservation without committing.
    # The caller must persist this outcome together with its own changes.
    if deadline <= now:
        reservation.status = "expired"

        event_seat_ids = db.scalars(
            select(ReservationSeat.event_seat_id)
            .where(
                ReservationSeat.reservation_id == reservation.id
            )
            .order_by(ReservationSeat.event_seat_id)
        ).all()

        if event_seat_ids:
            seats = db.scalars(
                select(EventSeat)
                .where(
                    EventSeat.id.in_(event_seat_ids),
                    EventSeat.event_id == event.id,
                )
                .order_by(EventSeat.id)
                .with_for_update()
            ).all()

            for seat in seats:
                if seat.status == "reserved":
                    seat.status = "available"

        return reservation, "expired"

    # 9. Lock reservation seats.
    event_seats = db.scalars(
        select(EventSeat)
        .join(
            ReservationSeat,
            ReservationSeat.event_seat_id == EventSeat.id,
        )
        .where(
            ReservationSeat.reservation_id == reservation.id,
            EventSeat.event_id == event.id,
        )
        .order_by(EventSeat.id)
        .with_for_update()
    ).all()

    if not event_seats or any(
        seat.status != "reserved"
        for seat in event_seats
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reservation seats are no longer reserved",
        )

    # 10. Confirm reservation and record the exact payment.
    for seat in event_seats:
        seat.status = "booked"

    reservation.status = "confirmed"
    reservation.confirmed_at = now
    reservation.confirmed_payment_id = payment.id

    return reservation, "confirmed"


def confirm_reservation_from_captured_payment(
    db: Session,
    reservation_id: int,
    payment_id: int,
) -> Reservation:
    """
    Backward-compatible wrapper for callers that own no outer transaction.

    Commits confirmation or expiry changes before returning/raising.
    """

    try:
        reservation, outcome = (
            confirm_reservation_from_captured_payment_in_transaction(
                db,
                reservation_id,
                payment_id,
            )
        )

        db.commit()
        db.refresh(reservation)

        if outcome == "expired":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Reservation has expired; "
                    "payment requires reconciliation"
                ),
            )

        return reservation

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise
