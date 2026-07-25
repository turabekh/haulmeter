"""E2 — F1 equipment registration (plate, unit number, VIN)

Driver request #1: license plate, unit number and an optional VIN alongside the
existing truck dimensions. All SELF-REPORTED — no verification is implied or
performed (VIN is format-validated only, never decoded). Parking bookings (M6)
and service callouts (M13-FR7) both consume plate/unit.

Revision ID: 0032_f01_equipment
Revises: 0031_f10_award_cooldown
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_f01_equipment"
down_revision: str | None = "0031_f10_award_cooldown"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f01"
COLUMNS = (
    ("plate_state", sa.String(2)),
    ("plate_number", sa.String(12)),
    ("unit_number", sa.String(20)),
    ("vin", sa.String(17)),
)


def upgrade() -> None:
    for name, type_ in COLUMNS:
        op.add_column("driver_profile", sa.Column(name, type_, nullable=True), schema=SCHEMA)


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("driver_profile", name, schema=SCHEMA)
