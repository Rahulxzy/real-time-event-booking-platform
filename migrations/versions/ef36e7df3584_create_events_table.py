"""create events table

Revision ID: ef36e7df3584
Revises: 54aa04f97d20
Create Date: 2026-10-22 18:24:20.906936
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ef36e7df3584"
down_revision: Union[str, Sequence[str], None] = "54aa04f97d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the events table."""
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("venue_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "price",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
        ),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["venue_id"],
            ["venues.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "ends_at > starts_at",
            name="ck_events_end_after_start",
        ),
        sa.CheckConstraint(
            "price >= 0 AND capacity > 0",
            name="ck_events_price_capacity_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_events_venue_id"),
        "events",
        ["venue_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the events table."""
    op.drop_index(
        op.f("ix_events_venue_id"),
        table_name="events",
    )
    op.drop_table("events")