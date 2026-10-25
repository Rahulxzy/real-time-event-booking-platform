
"""add event seat inventory

Revision ID: 311fcb345c93
Revises: e7046366987f
Create Date: 2026-10-25 19:35:32.846761
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "311fcb345c93"
down_revision: Union[str, Sequence[str], None] = "e7046366987f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Create referenced unique constraints before adding composite foreign keys.
    op.create_unique_constraint(
        "uq_events_id_venue_id",
        "events",
        ["id", "venue_id"],
    )

    op.create_unique_constraint(
        "uq_seats_id_venue_id",
        "seats",
        ["id", "venue_id"],
    )

    # Create event-specific seat inventory.
    op.create_table(
        "event_seats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("seat_id", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="available",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('available', 'reserved', 'booked')",
            name="ck_event_seats_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "venue_id"],
            ["events.id", "events.venue_id"],
            name="fk_event_seats_event_venue",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["seat_id", "venue_id"],
            ["seats.id", "seats.venue_id"],
            name="fk_event_seats_seat_venue",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "seat_id",
            name="uq_event_seats_event_seat",
        ),
    )

    op.create_index(
        "ix_event_seats_event_status",
        "event_seats",
        ["event_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Revert event-specific seat inventory."""

    # Drop dependent objects before their referenced constraints.
    op.drop_index(
        "ix_event_seats_event_status",
        table_name="event_seats",
    )

    op.drop_table("event_seats")

    op.drop_constraint(
        "uq_seats_id_venue_id",
        "seats",
        type_="unique",
    )

    op.drop_constraint(
        "uq_events_id_venue_id",
        "events",
        type_="unique",
    )
