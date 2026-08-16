"""AI-CONTEXT: F1 gains a Telegram method and a guest principal (E3 §E3.2, D14).

ADDITIVE ONLY. Existing auth is untouched: no column changes on `account`, `auth_method`
or `auth_session`, and every existing row keeps its meaning. E3 §E3.2 asks for exactly
that — "Migration adds the method rows only" — because F1's registry was designed for
this and a rework would mean the design had not held.

`ALTER TYPE ... ADD VALUE` IS THE ONE STATEMENT HERE WORTH KNOWING ABOUT. Postgres 12+
permits it inside a transaction, but the new label CANNOT BE USED in the same transaction
that adds it. This migration only adds the label; nothing in it inserts a row carrying
`telegram`. A later migration that both adds an enum value and writes it will fail, and it
will fail in a way that reads like the value was never added — which is TRAPS §1.2's
lesson wearing different clothes. If a data migration ever needs the new label, it goes in
a SEPARATE revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "0085_f01_tg_guest"
down_revision = "0084_m15_roadside"
branch_labels = None
depends_on = None

SCHEMA = "f01"


def upgrade() -> None:
    # the label only — nothing in this revision writes it (see the module docstring)
    op.execute(f"ALTER TYPE {SCHEMA}.method_type ADD VALUE IF NOT EXISTS 'telegram'")

    op.create_table(
        "guest_principal",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("token", sa.Uuid(), nullable=False, index=True),
        # which module may use it. An opt-in rather than a label — see `guests.py`.
        sa.Column("module", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "claimed_account_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.account.id"),
            nullable=True,
            index=True,
        ),
        sa.UniqueConstraint("token", name="uq_guest_principal_token"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("guest_principal", schema=SCHEMA)
    # AI-CONTEXT: the enum label is NOT removed, and that is not laziness. Postgres has no
    # `ALTER TYPE ... DROP VALUE`; removing it means rebuilding the type, re-typing every
    # column that uses it, and dropping their defaults first (TRAPS §1.5). A downgrade
    # that leaves an unused label costs nothing, and a downgrade that rebuilds a live
    # auth enum to save one unused label is how a rollback becomes an outage.
