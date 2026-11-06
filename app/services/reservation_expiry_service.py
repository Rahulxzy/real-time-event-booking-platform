
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Event, EventSeat, Reservation, ReservationSeat


def expire_due_reservations(
    db: Session,
    event_id: int,
) -> int:
    """
    Expire overdue pending reservations for an event
    and release their reserved seats.

    The caller owns the transaction. This function does not
    commit or roll back.

    Lock order:
        Event -> Reservation -> EventSeat
    """

    # 1. Lock the event first.
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
    )

    if event is None:
        return 0

    # 2. Find and lock overdue pending reservations.
    expired_reservations = db.scalars(
        select(Reservation)
        .where(
            Reservation.event_id == event_id,
            Reservation.status == "pending",
            func.coalesce(
                Reservation.checkout_deadline_at,
                Reservation.expires_at,
            ) <= func.now(),
        )
        .order_by(Reservation.id)
        .with_for_update()
    ).all()

    if not expired_reservations:
        return 0

    reservation_ids = [
        reservation.id
        for reservation in expired_reservations
    ]

    # 3. Find all associated event-seat IDs.
    event_seat_ids = db.scalars(
        select(ReservationSeat.event_seat_id)
        .where(
            ReservationSeat.reservation_id.in_(reservation_ids)
        )
        .order_by(ReservationSeat.event_seat_id)
    ).all()

    # 4. Release only seats that are still reserved.
    if event_seat_ids:
        db.execute(
            update(EventSeat)
            .where(
                EventSeat.id.in_(event_seat_ids),
                EventSeat.event_id == event_id,
                EventSeat.status == "reserved",
            )
            .values(status="available")
        )

    # 5. Mark reservations as expired.
    for reservation in expired_reservations:
        reservation.status = "expired"

    return len(expired_reservations)


def expire_user_reservations(
    db: Session,
    user_id: int,
) -> int:
    """
    Expire overdue reservations belonging to a user.

    The caller owns the transaction.
    """

    event_ids = db.scalars(
        select(Reservation.event_id)
        .where(
            Reservation.user_id == user_id,
            Reservation.status == "pending",
            func.coalesce(
                Reservation.checkout_deadline_at,
                Reservation.expires_at,
            ) <= func.now(),
        )
        .distinct()
        .order_by(Reservation.event_id)
    ).all()

    expired_count = 0

    for event_id in event_ids:
        expired_count += expire_due_reservations(
            db,
            event_id,
        )

    return expired_count


def expire_all_due_reservations(
    db: Session,
) -> int:
    """
    Expire overdue reservations across all events.

    Intended for the scheduled background task.
    The caller owns the transaction.
    """

    event_ids = db.scalars(
        select(Reservation.event_id)
        .where(
            Reservation.status == "pending",
            func.coalesce(
                Reservation.checkout_deadline_at,
                Reservation.expires_at,
            ) <= func.now(),
        )
        .distinct()
        .order_by(Reservation.event_id)
    ).all()

    expired_count = 0

    for event_id in event_ids:
        expired_count += expire_due_reservations(
            db,
            event_id,
        )

    return expired_count
