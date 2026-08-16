"""AI-CONTEXT: day 21 stops offering a collection partner nobody signed (J1-R2).

`dunning_escalation_offer_sent_at` recorded a step that, in practice, NEVER RAN: the
send was gated on `collection_partner_agreement`, that gate has been unsatisfied since it
was added in 0066, and the column was therefore NULL on every claim in existence. What
day 21 actually did was nothing — `skipped_ungated` — so a broker who ignored the day-3
nudge and the day-10 chaser heard nothing further, ever.

R2 replaces the offer with the firm, contract-citing follow-up. The column keeps its
meaning ("the day-21 follow-up went out") and loses a name that describes an offer this
product does not make.

A RENAME, not a drop-and-add: the values must survive even though there are none today,
because `escalate` remains a real receivable state and a box that had somehow sent one
must not silently lose the record of it. Postgres renames a column in place with no
table rewrite, so this is cheap on any size of table.
"""

from alembic import op

revision = "0082_dunning_final_notice"
down_revision = "0081_driver_profile_mpg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "detention_claim",
        "dunning_escalation_offer_sent_at",
        new_column_name="dunning_final_notice_sent_at",
        schema="m03",
    )


def downgrade() -> None:
    op.alter_column(
        "detention_claim",
        "dunning_final_notice_sent_at",
        new_column_name="dunning_escalation_offer_sent_at",
        schema="m03",
    )
