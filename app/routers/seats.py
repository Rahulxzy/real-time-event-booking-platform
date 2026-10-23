from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.dependencies import get_db, get_current_user
from app.models import Seat, Venue, User
from app.schemas import SeatCreate, SeatResponse, SeatUpdate

router = APIRouter(prefix="/venues/{venue_id}/seats", tags=["Seats"])


@router.post(
    "",
    response_model=SeatResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_seat(
    venue_id: int,
    seat_data: SeatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found",
        )

    seat = Seat(venue_id=venue_id, **seat_data.model_dump())
    db.add(seat)

    try:
        db.commit()
        db.refresh(seat)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seat already exists for this venue",
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        raise

    return seat


@router.get("", response_model=list[SeatResponse])
def list_venue_seats(
    venue_id: int,
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found",
        )

    statement = (
        select(Seat)
        .where(Seat.venue_id == venue_id)
        .order_by(Seat.row_label, Seat.seat_number)
    )
    return db.scalars(statement).all()


@router.get("/{seat_id}", response_model=SeatResponse)
def get_seat(
    venue_id: int,
    seat_id: int,
    db: Session = Depends(get_db),
):
    seat = db.scalar(
        select(Seat).where(
            Seat.id == seat_id,
            Seat.venue_id == venue_id,
        )
    )

    if seat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seat not found",
        )

    return seat


@router.patch("/{seat_id}", response_model=SeatResponse)
def update_seat(
    venue_id: int,
    seat_id: int,
    seat_data: SeatUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updates = seat_data.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one field must be provided",
        )

    if any(value is None for value in updates.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Seat fields cannot be null",
        )

    seat = db.scalar(
        select(Seat).where(
            Seat.id == seat_id,
            Seat.venue_id == venue_id,
        )
    )

    if seat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seat not found",
        )

    for field, value in updates.items():
        setattr(seat, field, value)

    try:
        db.commit()
        db.refresh(seat)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A seat with this row and number already exists",
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        raise

    return seat


@router.delete(
    "/{seat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_seat(
    venue_id: int,
    seat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    seat = db.scalar(
        select(Seat).where(
            Seat.id == seat_id,
            Seat.venue_id == venue_id,
        )
    )

    if seat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seat not found",
        )

    try:
        db.delete(seat)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return Response(status_code=status.HTTP_204_NO_CONTENT)