"""F8 — where a push actually goes

design-prd §13.1 calls background-permission survival "a platform-critical asset"
precisely because the model is about reaching a driver who is NOT looking at the app.
Everything F8 decides has, until now, ended either in a row the driver had to open the
inbox to see, or in a stream that only reaches an app already on screen. This table is
the missing half: the browser endpoint a P0 can be delivered to while the phone is in a
pocket.

ONE ROW PER BROWSER, not per driver — a phone and a cab tablet are two, and both should
buzz. `endpoint` is the push service's own URL for that browser instance, unique across
the world, so it is the natural key and a re-subscribe UPDATES rather than accumulates.
Without that constraint a driver who clears their site data collects duplicate pushes
forever, which is exactly the nagging §13.1's budget exists to prevent, arriving through
the transport instead of the tiering.

`p256dh` and `auth` are the subscription's public key material, not secrets of ours:
they are how the payload is encrypted TO that browser (RFC 8291), so the push service
relays ciphertext it cannot read. They are stored because they are useless without the
endpoint and meaningless to anyone else.

Revision ID: 0055_f08_push_subscription
Revises: 0054_m03_driver_clock_alerts
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0055_f08_push_subscription"
down_revision: str | None = "0054_m03_driver_clock_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f08"


def upgrade() -> None:
    op.create_table(
        "push_subscription",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("f01.account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("endpoint", name="uq_push_subscription_endpoint"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_push_subscription_account_id", "push_subscription", ["account_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_push_subscription_account_id", "push_subscription", schema=SCHEMA)
    op.drop_table("push_subscription", schema=SCHEMA)
