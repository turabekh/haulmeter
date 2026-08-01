"""A1 — the Stop Packet a driver reviews before it is sent

A1 requirement 5: "The driver reviews before it sends. Nothing leaves silently. A
packet the driver did not see is a document they cannot vouch for."

That is why this is a TABLE and not a function call. The packet is drafted by one
actor — a geofence EXIT — and sent by another, the driver, and the whole point is the
wait in between. A packet composed and sent in one breath could not be reviewed, and
the requirement would be satisfied in name only.

`uq_stop_packet_stop` is the other half of the same idea. Geofences bounce, and two
drafts for one stop is two documents a driver has to reject — the second of which
teaches them the queue is noise, which is how a review step quietly becomes a rubber
stamp.

Revision ID: 0057_a01_stop_packet
Revises: 0056_a09_facility_geog_idx
Create Date: 2026-08-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057_a01_stop_packet"
down_revision: str | None = "0056_a09_facility_geog_idx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # AI-CONTEXT: created explicitly, then referenced with `create_type=False`. A bare
    # `sa.Enum` inside `create_table` emits its own CREATE TYPE, so the type is made
    # twice and the second one fails with DuplicateObject — which reads as "the table
    # is broken" when the table has not been reached yet.
    state = sa.Enum("draft", "sent", name="stop_packet_state", schema="m05")
    state.create(op.get_bind(), checkfirst=True)
    state_col = postgresql.ENUM(
        "draft", "sent", name="stop_packet_state", schema="m05", create_type=False
    )
    op.create_table(
        "stop_packet",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("stop_ref", sa.Uuid(), nullable=False),
        sa.Column("counterparty_ref", sa.Uuid(), nullable=True),
        sa.Column("state", state_col, nullable=False),
        sa.Column("drafted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shared_pack_ref", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["account_id"], ["f01.account.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("stop_ref", name="uq_stop_packet_stop"),
        schema="m05",
    )
    op.create_index("ix_stop_packet_account_id", "stop_packet", ["account_id"], schema="m05")
    op.create_index("ix_stop_packet_stop_ref", "stop_packet", ["stop_ref"], schema="m05")


def downgrade() -> None:
    op.drop_index("ix_stop_packet_stop_ref", table_name="stop_packet", schema="m05")
    op.drop_index("ix_stop_packet_account_id", table_name="stop_packet", schema="m05")
    op.drop_table("stop_packet", schema="m05")
    sa.Enum(name="stop_packet_state", schema="m05").drop(op.get_bind(), checkfirst=True)
