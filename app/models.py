
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

from sqlalchemy import CheckConstraint


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    address: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Event(Base):
    __tablename__ = "events"

    __table_args__ = (
        CheckConstraint(
            "ends_at > starts_at",
            name="ck_events_end_after_start",
        ),
        CheckConstraint(
            "price >= 0 AND capacity > 0",
            name="ck_events_price_capacity_valid",
        ),
        UniqueConstraint(
            "id",
            "venue_id",
            name="uq_events_id_venue_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    capacity: Mapped[int] = mapped_column(
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Seat(Base):
    __tablename__ = "seats"

    __table_args__ = (
        UniqueConstraint(
            "venue_id",
            "row_label",
            "seat_number",
            name="uq_seats_venue_row_seat",
        ),
        CheckConstraint(
            "seat_number > 0",
            name="ck_seats_seat_number_positive",
        ),
        UniqueConstraint(
            "id",
            "venue_id",
            name="uq_seats_id_venue_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    venue_id: Mapped[int] = mapped_column(
        ForeignKey("venues.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    row_label: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    seat_number: Mapped[int] = mapped_column(
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class EventSeat(Base):
    __tablename__ = "event_seats"

    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "seat_id",
            name="uq_event_seats_event_seat",
        ),
        CheckConstraint(
            "status IN ('available', 'reserved', 'booked')",
            name="ck_event_seats_status_valid",
        ),
        Index(
            "ix_event_seats_event_status",
            "event_id",
            "status",
        ),
        ForeignKeyConstraint(
            ["event_id", "venue_id"],
            ["events.id", "events.venue_id"],
            name="fk_event_seats_event_venue",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["seat_id", "venue_id"],
            ["seats.id", "seats.venue_id"],
            name="fk_event_seats_seat_venue",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id",
            "event_id",
            name="uq_event_seats_id_event_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    event_id: Mapped[int] = mapped_column(
        nullable=False,
    )

    seat_id: Mapped[int] = mapped_column(
        nullable=False,
    )

    venue_id: Mapped[int] = mapped_column(
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="available",
        server_default="available",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )



class Reservation(Base):
    __tablename__ = "reservations"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'expired', 'cancelled')",
            name="ck_reservations_status_valid",
        ),
        UniqueConstraint(
            "id",
            "event_id",
            name="uq_reservations_id_event_id",
        ),
        Index(
            "ix_reservations_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_reservations_event_status_expiry",
            "event_id",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ReservationSeat(Base):
    __tablename__ = "reservation_seats"

    __table_args__ = (
        UniqueConstraint(
            "reservation_id",
            "event_seat_id",
            name="uq_reservation_seats_reservation_event_seat",
        ),
        ForeignKeyConstraint(
            ["reservation_id", "event_id"],
            ["reservations.id", "reservations.event_id"],
            name="fk_reservation_seats_reservation_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["event_seat_id", "event_id"],
            ["event_seats.id", "event_seats.event_id"],
            name="fk_reservation_seats_event_seat",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_reservation_seats_reservation",
            "reservation_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    reservation_id: Mapped[int] = mapped_column(
        nullable=False,
    )

    event_seat_id: Mapped[int] = mapped_column(
        nullable=False,
    )

    event_id: Mapped[int] = mapped_column(
        nullable=False,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
