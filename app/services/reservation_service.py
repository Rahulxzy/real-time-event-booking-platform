
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


def confirm_reservation_from_captured_payment(
    db: Session,
    reservation_id: int,
    payment_id: int,
) -> Reservation:
    """
    Confirm a reservation only when its associated payment is captured
    and the captured amount matches the reservation total.

    Lock order:
    Event -> Reservation -> Payment -> EventSeat
    """

    try:
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

        if reservation.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot confirm a {reservation.status} reservation",
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

        # 5. Validate payment currency.
        if payment.currency != "INR":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Payment currency does not match reservation currency",
            )

        # 6. Calculate the reservation total from stored price snapshots.
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

        # 7. Compare the captured payment amount with the expected amount.
        if payment.amount_paise != expected_amount_paise:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Payment amount does not match reservation total",
            )

        # 8. Get database time and normalize timezone.
        now = db.scalar(select(func.now()))

        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # Use checkout deadline if checkout was initiated.
        deadline = (
            reservation.checkout_deadline_at
            if reservation.checkout_deadline_at is not None
            else reservation.expires_at
        )

        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        # 9. Handle expired reservation.
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

            # Preserve expiry and seat-release changes.
            db.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Reservation has expired; "
                    "payment requires reconciliation"
                ),
            )

        # 10. Lock reservation seats.
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

        # 11. Confirm reservation atomically.
        for seat in event_seats:
            seat.status = "booked"

        reservation.status = "confirmed"
        reservation.confirmed_at = now

        db.commit()
        db.refresh(reservation)

        return reservation

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise
