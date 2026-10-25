
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user
from app.models import Event, EventSeat, Seat, User
from app.schemas import EventSeatAvailabilityResponse

router = APIRouter(
    prefix="/events/{event_id}",
    tags=["Event Seat Inventory"],
)


@router.post("/inventory", status_code=status.HTTP_201_CREATED)
def initialize_event_inventory(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = db.get(Event, event_id)

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    seats = db.scalars(
        select(Seat.id).where(Seat.venue_id == event.venue_id)
    ).all()

    if not seats:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot initialize inventory because this venue has no seats",
        )

    created_count = 0

    try:
        for seat_id in seats:
            existing = db.scalar(
                select(EventSeat.id).where(
                    EventSeat.event_id == event.id,
                    EventSeat.seat_id == seat_id,
                )
            )

            if existing is not None:
                continue

            db.add(
                EventSeat(
                    event_id=event.id,
                    seat_id=seat_id,
                    venue_id=event.venue_id,
                    status="available",
                )
            )

            try:
                with db.begin_nested():
                    db.flush()
                created_count += 1
            except IntegrityError:
                # A concurrent request may have inserted this seat already.
                continue

        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise

    total_count = len(
        db.scalars(
            select(EventSeat.id).where(EventSeat.event_id == event.id)
        ).all()
    )

    return {
        "event_id": event.id,
        "created_count": created_count,
        "total_count": total_count,
        "message": "Event inventory initialized successfully",
    }


@router.get(
    "/seats",
    response_model=list[EventSeatAvailabilityResponse],
)
def list_event_seats(
    event_id: int,
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    rows = db.execute(
        select(EventSeat, Seat)
        .join(Seat, EventSeat.seat_id == Seat.id)
        .where(EventSeat.event_id == event_id)
        .order_by(Seat.row_label, Seat.seat_number)
    ).all()

    return [
        EventSeatAvailabilityResponse(
            id=event_seat.id,
            event_id=event_seat.event_id,
            seat_id=event_seat.seat_id,
            row_label=seat.row_label,
            seat_number=seat.seat_number,
            status=event_seat.status,
        )
        for event_seat, seat in rows
    ]


@router.get(
    "/seats/{seat_id}",
    response_model=EventSeatAvailabilityResponse,
)
def get_event_seat(
    event_id: int,
    seat_id: int,
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    row = db.execute(
        select(EventSeat, Seat)
        .join(Seat, EventSeat.seat_id == Seat.id)
        .where(
            EventSeat.event_id == event_id,
            EventSeat.seat_id == seat_id,
        )
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seat not found in event inventory",
        )

    event_seat, seat = row

    return EventSeatAvailabilityResponse(
        id=event_seat.id,
        event_id=event_seat.event_id,
        seat_id=event_seat.seat_id,
        row_label=seat.row_label,
        seat_number=seat.seat_number,
        status=event_seat.status,
    )
