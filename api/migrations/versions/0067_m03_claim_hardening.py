"""AI-CONTEXT: M3's duplication backstops and the columns the honest-delivery,
dunning and pre-notice work needs (findings F1, F2, F5, F6, F7).

TWO PARTIAL UNIQUE INDEXES, for the same reason 0060 gave: an application check reads
rows a concurrent transaction has not committed yet, and it does not survive a second
API replica however carefully it is written. `start_claim` was a check-then-act behind
`claim_for_stop(...) or start_claim(...)`, and `generate_pack` had no state guard at
all — so one stop could carry two open claims, and one detention could open two
receivables and invoice the broker twice.

WHY `state = 'open'` RATHER THAN THE WHOLE COLUMN. A stop legitimately accumulates
claim history: a claim is filed, and the driver returns to the same dock on another
load. Only the OPEN one is the singleton, which is exactly the predicate
`claim_for_stop` and `claims_awaiting_alerts` already select on.

WHY `f07.receivable(external_ref)` IS THE FILING BACKSTOP. The claim's own state guard
answers the ordinary double-tap; the index answers the concurrent one, because
`external_ref = 'm03:<claim_id>'` is derived from the claim rather than generated per
call. It is partial on NOT NULL because M4 and every other opener still passes nothing
— see the report's follow-up. This mirrors `uq_journal_entry_type_ref` from 0060.

The upgrade REFUSES to run against data that already violates either rule and names the
rows, rather than surfacing a raw Postgres error from the middle of a deploy.

NO `driver_paid_alert_at`. The brief listed one, for a "claim paid" notification that
turned out to be already built (`m09.mark_receivable_paid`) and made once-only by F7's
transition table — `recovered -> recovered` raises. A nullable column nothing writes is
the built-and-inert shape this codebase keeps finding, so it is not added.
"""

import sqlalchemy as sa
from alembic import op

revision = "0067_m03_claim_hardening"
down_revision = "0066_f13_default_on"
branch_labels = None
depends_on = None

M03 = "m03"
F07 = "f07"

DUPLICATE_OPEN_CLAIMS = sa.text(
    """
    SELECT stop_ref, count(*) AS n
      FROM m03.detention_claim
     WHERE state = 'open'
     GROUP BY stop_ref
    HAVING count(*) > 1
    """
)

DUPLICATE_RECEIVABLE_REFS = sa.text(
    """
    SELECT external_ref, count(*) AS n
      FROM f07.receivable
     WHERE external_ref IS NOT NULL
     GROUP BY external_ref
    HAVING count(*) > 1
    """
)

NEW_COLUMNS = [
    # F5: which F8 message row carries this notice, so "sent" can be read off the row
    # that knows rather than asserted by the caller that hoped.
    sa.Column("start_notice_message_ref", sa.Uuid(), nullable=True),
    # F7: the broker's "free time is nearly up" warning, once per claim.
    sa.Column("pre_notice_sent_at", sa.DateTime(timezone=True), nullable=True),
    # F6: one column per dunning action. Three columns rather than one "last dunned at"
    # because the schedule is three distinct documents with three distinct subjects, and
    # a single timestamp cannot say which of them a broker has actually received.
    sa.Column("dunning_nudge_sent_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("dunning_firm_sent_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("dunning_escalation_offer_sent_at", sa.DateTime(timezone=True), nullable=True),
    # F6: `escalate` accepted an `external_ref` and dropped it on the floor. No existing
    # column fits — `receivable_ref` is ours and the receivable's own `external_ref` is
    # now the filing backstop above — so the collection partner's handle gets its own.
    sa.Column("escalation_ref", sa.String(300), nullable=True),
]


def _refuse(rows, what: str) -> None:
    detail = "; ".join(str(tuple(r)) for r in rows[:10])
    raise RuntimeError(
        f"0067 cannot apply: {len(rows)} {what} already exist and would violate the new "
        f"constraint. Reconcile them first — this migration will not choose which row "
        f"survives. Offenders: {detail}"
    )


def upgrade() -> None:
    conn = op.get_bind()

    duplicates = conn.execute(DUPLICATE_OPEN_CLAIMS).fetchall()
    if duplicates:
        _refuse(duplicates, "stops with more than one OPEN detention claim")

    duplicate_refs = conn.execute(DUPLICATE_RECEIVABLE_REFS).fetchall()
    if duplicate_refs:
        _refuse(duplicate_refs, "duplicate receivable external_refs")

    for column in NEW_COLUMNS:
        op.add_column("detention_claim", column, schema=M03)

    op.create_index(
        "uq_detention_claim_open_stop",
        "detention_claim",
        ["stop_ref"],
        unique=True,
        schema=M03,
        postgresql_where=sa.text("state = 'open'"),
    )
    op.create_index(
        "uq_receivable_external_ref",
        "receivable",
        ["external_ref"],
        unique=True,
        schema=F07,
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_receivable_external_ref", table_name="receivable", schema=F07)
    op.drop_index("uq_detention_claim_open_stop", table_name="detention_claim", schema=M03)
    for column in reversed(NEW_COLUMNS):
        op.drop_column("detention_claim", column.name, schema=M03)
