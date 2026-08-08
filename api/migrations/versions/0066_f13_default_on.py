"""f13: split a flag's code default from the operator's decision (audit F-02, F-12)

AI-CONTEXT: `enabled` carried two different facts and the collision made six validation
gates inert. See `f13_flags/domain/models.py` for the full argument; what matters here is
the BACKFILL, because getting it wrong either takes M3 dark or silently re-enables
something an operator switched off.

    default_on  the code's declaration; `register_flag` refreshes it on every boot
    enabled     the operator's decision, and NULL now means "they have not made one"

**The backfill preserves every existing row's behaviour exactly, and deliberately does
NOT try to guess which of the two facts a current `enabled` value represents.**

    default_on := enabled      (so a fresh read of either column agrees with today)
    enabled    := enabled      (left alone — treated as an explicit decision)

Both columns therefore say what the box is doing right now, and `_effective` returns the
same answer it would have returned before this migration for every one of the 22 rows.

Two things this avoids, both of which a "cleaner" backfill would have caused:

  · Setting `enabled := NULL` everywhere would hand every flag back to its code default.
    `m13_vendor` and `m13_service_center` are OFF because session 114 switched them off
    in dev AND production, after finding the food half live over demo data. Their code
    default is `True` — they are shipped capabilities — so nulling the column would have
    turned food back on at the next boot. "A redeploy must never silently flip a flag
    back" is the rule `register_flag` was already written to obey.
  · Making the gates block the default would have taken M3 detention dark on the next
    boot, with `legal_signoff` and `collection_partner_agreement` both unsatisfied. The
    detention clock is the wedge. The 29 July owner decision stands and the unsatisfied
    gates are REPORTED instead — `running_ahead_of_gates`.

The consequence, stated plainly rather than hidden: on an already-booted box every flag
has a non-NULL `enabled`, so `default_on` governs nothing there until somebody calls
`clear_decision`. That is correct and is the point — the mechanism is what changes, and it
governs every future flag, every future activation, and A7's inventory gate, which PRD
v2.0 §3 specifies and which would have done nothing under the old assignment.

Downgrade folds the two columns back into one by keeping the effective value, so it is
lossy in the same way the original schema was: it cannot express "no decision".
"""

import sqlalchemy as sa
from alembic import op

revision = "0066_f13_default_on"
down_revision = "0065_f14_job_schedule"
branch_labels = None
depends_on = None

SCHEMA = "f13"


def upgrade() -> None:
    op.add_column(
        "feature_flag",
        sa.Column("default_on", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )
    # today's state becomes the code default AND stays the recorded decision, so nothing
    # about what is running changes
    op.execute(f"UPDATE {SCHEMA}.feature_flag SET default_on = enabled")
    op.alter_column("feature_flag", "enabled", nullable=True, schema=SCHEMA)
    # the server default exists only for the backfill; the model owns it from here
    op.alter_column("feature_flag", "default_on", server_default=None, schema=SCHEMA)


def downgrade() -> None:
    # a NULL decision resolves to the declared default before the column can go back to
    # NOT NULL — otherwise a flag that has never been decided would fail the constraint
    op.execute(f"UPDATE {SCHEMA}.feature_flag SET enabled = default_on WHERE enabled IS NULL")
    op.alter_column(
        "feature_flag",
        "enabled",
        nullable=False,
        server_default=sa.false(),
        schema=SCHEMA,
    )
    op.drop_column("feature_flag", "default_on", schema=SCHEMA)
