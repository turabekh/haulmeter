"""AI-CONTEXT: `login_attempt` learns to count two different things (finding F1-6/F1-7).

Registration runs Argon2 for an unauthenticated caller and nothing counted it, so the
route beside the hardened one was an unmetered CPU-exhaustion vector and a free
account-existence oracle. Throttling it needs a counter — and it must NOT be the login
counter.

WHY THE DISCRIMINATOR IS THE WHOLE POINT. Without `kind`, a registration flood from a
carrier NAT would fill the per-IP bucket and lock honest drivers out of LOGIN on the same
address. `LOGIN_MAX_PER_IP = 20`'s own comment exists to avoid exactly that false positive
("higher: a carrier NAT can put many honest drivers on one address"), and sharing the
bucket would reintroduce it through the back door.

NO BACKFILL, deliberately and not as an omission. The column is nullable with a server
default of 'login', so every existing row reads as what it actually was — the table has
only ever held login failures — the moment the column exists. A backfill would rewrite
history to say the same thing it already says.

THE INDEXES ARE REPLACED, NOT ADDED TO. Both queries become
`WHERE identifier = ? AND kind = ? AND occurred_at > ?`, so `kind` belongs in the middle:
the old indexes stay usable by their leading column, and keeping them alongside the new
ones would be pure write amplification on the one table that takes a row per attack
attempt. Verified against the query plan on the running stack rather than assumed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0069_f01_attempt_kind"
down_revision = "0068_f03_location_integrity"
branch_labels = None
depends_on = None

SCHEMA = "f01"
TABLE = "login_attempt"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("kind", sa.String(20), nullable=False, server_default="login"),
        schema=SCHEMA,
    )
    op.drop_index("ix_login_attempt_identifier_time", table_name=TABLE, schema=SCHEMA)
    op.drop_index("ix_login_attempt_ip_time", table_name=TABLE, schema=SCHEMA)
    op.create_index(
        "ix_login_attempt_identifier_kind_time",
        TABLE,
        ["identifier", "kind", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_login_attempt_ip_kind_time",
        TABLE,
        ["client_ip", "kind", "occurred_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_login_attempt_ip_kind_time", table_name=TABLE, schema=SCHEMA)
    op.drop_index("ix_login_attempt_identifier_kind_time", table_name=TABLE, schema=SCHEMA)
    op.create_index(
        "ix_login_attempt_ip_time", TABLE, ["client_ip", "occurred_at"], schema=SCHEMA
    )
    op.create_index(
        "ix_login_attempt_identifier_time", TABLE, ["identifier", "occurred_at"], schema=SCHEMA
    )
    op.drop_column(TABLE, "kind", schema=SCHEMA)
