
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
    # Lock the event to serialize inventory initialization
    # and event venue changes.
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
    )

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # Lock physical seats while initializing their event inventory.
    seats = db.scalars(
        select(Seat)
        .where(Seat.venue_id == event.venue_id)
        .order_by(Seat.id)
        .with_for_update()
    ).all()

    if not seats:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot initialize inventory because this venue has no seats",
        )

    created_count = 0

    try:
        for seat in seats:
            existing = db.scalar(
                select(EventSeat.id).where(
                    EventSeat.event_id == event.id,
                    EventSeat.seat_id == seat.id,
                )
            )

            if existing is not None:
                continue

            try:
                # Keep the insert inside the savepoint so an integrity
                # error does not invalidate the outer transaction.
                with db.begin_nested():
                    db.add(
                        EventSeat(
                            event_id=event.id,
                            seat_id=seat.id,
                            venue_id=event.venue_id,
                            status="available",
                        )
                    )
                    db.flush()

                created_count += 1

            except IntegrityError:
                # The unique constraint protects against duplicate rows.
                continue

        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise

    total_count = len(
        db.scalars(
            select(EventSeat.id).where(
                EventSeat.event_id == event.id
            )
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
