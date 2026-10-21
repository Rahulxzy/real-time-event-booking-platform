from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User, Venue
from app.schemas import VenueCreate, VenueResponse, VenueUpdate

router = APIRouter(prefix="/venues", tags=["Venues"])


@router.post(
    "",
    response_model=VenueResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_venue(
    venue_data: VenueCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    venue = Venue(**venue_data.model_dump())
    db.add(venue)

    try:
        db.commit()
        db.refresh(venue)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create venue due to a database conflict",
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        raise

    return venue


@router.get("", response_model=list[VenueResponse])
def list_venues(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    if skip < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="skip must be greater than or equal to 0",
        )

    if not 1 <= limit <= 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 100",
        )

    statement = select(Venue).order_by(Venue.id).offset(skip).limit(limit)
    return db.scalars(statement).all()


@router.get("/{venue_id}", response_model=VenueResponse)
def get_venue(
    venue_id: int,
    db: Session = Depends(get_db),
):
    venue = db.get(Venue, venue_id)

    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found",
        )

    return venue


@router.patch("/{venue_id}", response_model=VenueResponse)
def update_venue(
    venue_id: int,
    venue_data: VenueUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updates = venue_data.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one field must be provided",
        )

    if any(value is None for value in updates.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Venue fields cannot be null",
        )

    venue = db.get(Venue, venue_id)

    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found",
        )

    for field, value in updates.items():
        setattr(venue, field, value)

    try:
        db.commit()
        db.refresh(venue)
    except SQLAlchemyError:
        db.rollback()
        raise

    return venue


@router.delete(
    "/{venue_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_venue(
    venue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    venue = db.get(Venue, venue_id)

    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found",
        )

    try:
        db.delete(venue)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return Response(status_code=status.HTTP_204_NO_CONTENT)