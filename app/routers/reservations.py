
from datetime import timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user
from app.models import (
    Event,
    EventSeat,
    Reservation,
    ReservationSeat,
    Seat,
    User,
)
from app.schemas import (
    ReservationCreate,
    ReservationResponse,
    ReservationSeatResponse,
)

router = APIRouter(
    prefix="/reservations",
    tags=["Reservations"],
)

HOLD_MINUTES = 5


def get_database_now(db: Session):
    """Get the current time from the database clock."""
    now = db.scalar(select(func.now()))

    # SQLite may return a naive datetime in tests.
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    return now


def expire_due_reservations(
    db: Session,
    event_id: int,
) -> int:
    """Expire overdue reservations and release their seats."""

    expired_reservations = db.scalars(
        select(Reservation)
        .where(
            Reservation.event_id == event_id,
            Reservation.status == "pending",
            Reservation.expires_at <= func.now(),
        )
        .order_by(Reservation.id)
        .with_for_update()
    ).all()

    if not expired_reservations:
        return 0

    reservation_ids = [r.id for r in expired_reservations]

    event_seat_ids = db.scalars(
        select(ReservationSeat.event_seat_id)
        .where(
            ReservationSeat.reservation_id.in_(reservation_ids)
        )
        .order_by(ReservationSeat.event_seat_id)
    ).all()

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

    for reservation in expired_reservations:
        reservation.status = "expired"

    return len(expired_reservations)


def build_reservation_response(
    db: Session,
    reservation: Reservation,
) -> dict:
    rows = db.execute(
        select(ReservationSeat, Seat)
        .join(
            EventSeat,
            ReservationSeat.event_seat_id == EventSeat.id,
        )
        .join(
            Seat,
            EventSeat.seat_id == Seat.id,
        )
        .where(
            ReservationSeat.reservation_id == reservation.id
        )
        .order_by(Seat.row_label, Seat.seat_number)
    ).all()

    seats = [
        ReservationSeatResponse(
            event_seat_id=reservation_seat.event_seat_id,
            row_label=seat.row_label,
            seat_number=seat.seat_number,
            price=reservation_seat.price,
        )
        for reservation_seat, seat in rows
    ]

    total = sum(
        (seat.price for seat in seats),
        Decimal("0.00"),
    )

    return {
        "id": reservation.id,
        "event_id": reservation.event_id,
        "user_id": reservation.user_id,
        "status": reservation.status,
        "expires_at": reservation.expires_at,
        "created_at": reservation.created_at,
        "confirmed_at": reservation.confirmed_at,
        "seats": seats,
        "total_amount": total,
    }


def get_owned_reservation(
    db: Session,
    reservation_id: int,
    user_id: int,
) -> Reservation:
    reservation = db.scalar(
        select(Reservation).where(
            Reservation.id == reservation_id,
            Reservation.user_id == user_id,
        )
    )

    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reservation not found",
        )

    return reservation


def expire_user_reservations(
    db: Session,
    user_id: int,
) -> None:
    """Process overdue reservations belonging to a user."""

    event_ids = db.scalars(
        select(Reservation.event_id)
        .where(
            Reservation.user_id == user_id,
            Reservation.status == "pending",
            Reservation.expires_at <= func.now(),
        )
        .distinct()
        .order_by(Reservation.event_id)
    ).all()

    for event_id in event_ids:
        event = db.scalar(
            select(Event)
            .where(Event.id == event_id)
            .with_for_update()
        )

        if event is not None:
            expire_due_reservations(db, event_id)

    db.commit()


@router.post(
    "",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_reservation(
    payload: ReservationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        # Lock event first to serialize reservation operations.
        event = db.scalar(
            select(Event)
            .where(Event.id == payload.event_id)
            .with_for_update()
        )

        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )

        # Release expired seats before checking availability.
        expire_due_reservations(db, event.id)

        event_seats = db.scalars(
            select(EventSeat)
            .where(
                EventSeat.event_id == event.id,
                EventSeat.id.in_(payload.event_seat_ids),
            )
            .order_by(EventSeat.id)
            .with_for_update()
        ).all()

        if len(event_seats) != len(payload.event_seat_ids):
            # Preserve expiry changes even though this request fails.
            db.commit()

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more seats do not belong to this event",
            )

        unavailable = [
            seat.id
            for seat in event_seats
            if seat.status != "available"
        ]

        if unavailable:
            # Expiry changes must not be rolled back by this conflict.
            db.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="One or more requested seats are unavailable",
            )

        now = get_database_now(db)

        reservation = Reservation(
            user_id=current_user.id,
            event_id=event.id,
            status="pending",
            expires_at=now + timedelta(minutes=HOLD_MINUTES),
        )

        db.add(reservation)
        db.flush()

        for event_seat in event_seats:
            event_seat.status = "reserved"

            db.add(
                ReservationSeat(
                    reservation_id=reservation.id,
                    event_seat_id=event_seat.id,
                    event_id=event.id,
                    price=event.price,
                )
            )

        db.commit()
        db.refresh(reservation)

        return build_reservation_response(db, reservation)

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError:
        db.rollback()
        raise


@router.get(
    "/me",
    response_model=list[ReservationResponse],
)
def list_my_reservations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        expire_user_reservations(db, current_user.id)

        reservations = db.scalars(
            select(Reservation)
            .where(Reservation.user_id == current_user.id)
            .order_by(Reservation.created_at.desc())
        ).all()

        return [
            build_reservation_response(db, reservation)
            for reservation in reservations
        ]

    except SQLAlchemyError:
        db.rollback()
        raise


@router.get(
    "/{reservation_id}",
    response_model=ReservationResponse,
)
def get_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        reservation = get_owned_reservation(
            db,
            reservation_id,
            current_user.id,
        )

        event = db.scalar(
            select(Event)
            .where(Event.id == reservation.event_id)
            .with_for_update()
        )

        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )

        expire_due_reservations(db, event.id)
        db.commit()

        reservation = get_owned_reservation(
            db,
            reservation_id,
            current_user.id,
        )

        return build_reservation_response(db, reservation)

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError:
        db.rollback()
        raise


@router.post(
    "/{reservation_id}/confirm",
    response_model=ReservationResponse,
)
def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        reservation = get_owned_reservation(
            db,
            reservation_id,
            current_user.id,
        )

        event = db.scalar(
            select(Event)
            .where(Event.id == reservation.event_id)
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
                Reservation.user_id == current_user.id,
            )
            .with_for_update()
        )

        if reservation.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot confirm a {reservation.status} reservation",
            )

        expire_due_reservations(db, event.id)

        if reservation.status != "pending":
            db.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation has expired",
            )

        event_seats = db.scalars(
            select(EventSeat)
            .join(
                ReservationSeat,
                ReservationSeat.event_seat_id == EventSeat.id,
            )
            .where(
                ReservationSeat.reservation_id == reservation.id,
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

        for seat in event_seats:
            seat.status = "booked"

        reservation.status = "confirmed"
        reservation.confirmed_at = get_database_now(db)

        db.commit()
        db.refresh(reservation)

        return build_reservation_response(db, reservation)

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError:
        db.rollback()
        raise


@router.post(
    "/{reservation_id}/cancel",
    response_model=ReservationResponse,
)
def cancel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        reservation = get_owned_reservation(
            db,
            reservation_id,
            current_user.id,
        )

        event = db.scalar(
            select(Event)
            .where(Event.id == reservation.event_id)
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
                Reservation.user_id == current_user.id,
            )
            .with_for_update()
        )

        if reservation.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only pending reservations can be cancelled",
            )

        expire_due_reservations(db, event.id)

        if reservation.status != "pending":
            db.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation has expired",
            )

        event_seats = db.scalars(
            select(EventSeat)
            .join(
                ReservationSeat,
                ReservationSeat.event_seat_id == EventSeat.id,
            )
            .where(
                ReservationSeat.reservation_id == reservation.id,
            )
            .order_by(EventSeat.id)
            .with_for_update()
        ).all()

        for seat in event_seats:
            if seat.status == "reserved":
                seat.status = "available"

        reservation.status = "cancelled"

        db.commit()
        db.refresh(reservation)

        return build_reservation_response(db, reservation)

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError:
        db.rollback()
        raise
