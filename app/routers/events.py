from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import Event, User, Venue
from app.schemas import EventCreate, EventResponse, EventUpdate

router = APIRouter(prefix="/events", tags=["Events"])


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    event_data: EventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    venue = db.get(Venue, event_data.venue_id)

    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found",
        )

    event = Event(**event_data.model_dump())
    db.add(event)

    try:
        db.commit()
        db.refresh(event)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create event due to a database conflict",
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        raise

    return event


@router.get("", response_model=list[EventResponse])
def list_events(
    skip: int = 0,
    limit: int = 20,
    venue_id: int | None = None,
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

    if venue_id is not None and venue_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="venue_id must be greater than 0",
        )

    statement = select(Event)

    if venue_id is not None:
        statement = statement.where(Event.venue_id == venue_id)

    statement = statement.order_by(Event.id).offset(skip).limit(limit)
    return db.scalars(statement).all()


@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    return event


@router.patch("/{event_id}", response_model=EventResponse)
def update_event(
    event_id: int,
    event_data: EventUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updates = event_data.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one field must be provided",
        )

    # Description is optional and can be cleared using null.
    # All other supplied fields must have non-null values.
    nullable_fields = {"description"}

    if any(
        value is None and field not in nullable_fields
        for field, value in updates.items()
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Required event fields cannot be null",
        )

    event = db.get(Event, event_id)

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )

    # Validate the final time range, including unchanged DB values.
    starts_at = updates.get("starts_at", event.starts_at)
    ends_at = updates.get("ends_at", event.ends_at)

    if ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ends_at must be after starts_at",
        )

    # If venue_id changes, ensure the target venue exists.
    if "venue_id" in updates:
        venue = db.get(Venue, updates["venue_id"])

        if venue is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Venue not found",
            )

    for field, value in updates.items():
        setattr(event, field, value)

    try:
        db.commit()
        db.refresh(event)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not update event due to a database conflict",
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        raise

    return event


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_event(
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

    try:
        db.delete(event)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return Response(status_code=status.HTTP_204_NO_CONTENT)