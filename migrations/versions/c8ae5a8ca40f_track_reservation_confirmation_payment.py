
"""track reservation confirmation payment

Revision ID: c8ae5a8ca40f
Revises: 381dd1235d38
Create Date: 2026-11-04 18:44:39.821444

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8ae5a8ca40f"
down_revision: Union[str, Sequence[str], None] = "381dd1235d38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reservations",
        sa.Column(
            "confirmed_payment_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_unique_constraint(
        "uq_reservations_confirmed_payment",
        "reservations",
        ["confirmed_payment_id"],
    )

    op.create_foreign_key(
        "fk_reservations_confirmed_payment",
        "reservations",
        "payments",
        ["confirmed_payment_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_reservations_confirmed_payment",
        "reservations",
        type_="foreignkey",
    )

    op.drop_constraint(
        "uq_reservations_confirmed_payment",
        "reservations",
        type_="unique",
    )

    op.drop_column(
        "reservations",
        "confirmed_payment_id",
    )
