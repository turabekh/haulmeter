"""F8 — the positive half of the per-subject notification preference

`muted_subjects` has always been there because the `vendor_alert` class definition
requires a one-tap mute per vendor. It is a suppression list, read at dispatch.

`followed_subjects` is the mirror: subjects an account asked to hear ABOUT. It is
read by callers choosing an audience, not by dispatch, which is why F8 also exposes
a reverse lookup (`followers_of`).

Why this belongs in F8 rather than in M13: it is a per-driver preference INSIDE a
notification class, exactly like the mute sitting beside it. Splitting the positive
and negative halves of one idea across two components to serve one consumer would
mean two places to be right about who hears what.

Existing rows default to an empty list. Nobody has followed anything yet, and there
is nothing to infer — a prior crowd confirmation is a contribution, not a request to
be notified, and reading it as consent is the mistake this column exists to end.

Revision ID: 0046_f08_followed_subjects
Revises: 0045_m13_halal_claim
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046_f08_followed_subjects"
down_revision: str | None = "0045_m13_halal_claim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f08"


def upgrade() -> None:
    op.add_column(
        "notification_class_pref",
        sa.Column("followed_subjects", sa.JSON(), nullable=False, server_default="[]"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("notification_class_pref", "followed_subjects", schema=SCHEMA)
