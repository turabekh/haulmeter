"""AI-CONTEXT: an on-time proof learns which message carried its notice.

Counterparty email left the request thread this session — it was 2.5 s of connect,
STARTTLS and AUTH inside the handler before a byte of a notice moved, with a 10 s timeout,
holding a POOLED DATABASE CONNECTION and a threadpool slot for the whole round trip. §23
records that exact outage: "QueuePool limit of size 5 overflow 10 reached", the API out of
connections and answering nothing.

`OnTimeProof.notice_sent` means THE COUNTERPARTY WAS REACHED, and it was written by the
request that decided to reach them — `message.sent_at is not None`, evaluated immediately
after a synchronous send. With delivery moved to the `outbound_mail` sweep, that
expression is False at file time for every proof, forever: not wrong at the instant it is
written, which is the subtle part, and never corrected afterwards.

A boolean that is always False is indistinguishable from a feature that does not work, and
this one is a driver's evidence that they arrived on time AND that the broker was told.

So the proof records WHICH F8 message carries its notice, and `reconcile_on_time_notices`
stamps `notice_sent` when that row actually lands. This is the same shape M3 already used
for `start_notice_message_ref` beside `start_notice_sent_at` — the ref records that we
decided to send, the other column records that it went, and only the message row knows the
second thing (finding F5).

NOTHING IS BACKFILLED, and nothing can be. Existing rows were written under the old
synchronous path, where `notice_sent` was already decided correctly at the moment of the
send; they have no message to point at and need none. NULL here means "filed before the
proof carried a ref", which is exactly true.
"""

import sqlalchemy as sa
from alembic import op

revision = "0072_on_time_notice_ref"
down_revision = "0071_thumbnail_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "on_time_proof",
        sa.Column("notice_message_ref", sa.Uuid(), nullable=True),
        schema="m05",
    )
    # indexed because the reconcile's only query is "proofs whose ref is in this batch",
    # run once a minute against a table that grows one row per on-time arrival
    op.create_index(
        op.f("ix_m05_on_time_proof_notice_message_ref"),
        "on_time_proof",
        ["notice_message_ref"],
        unique=False,
        schema="m05",
    )


def downgrade() -> None:
    # AI-CONTEXT: `notice_sent` is deliberately left as it stands. Reverting this column
    # loses the ability to reconcile FUTURE sends, and a downgrade that also rewrote the
    # booleans would be editing a driver's record of what a broker was told — which is the
    # one thing an evidence trail may never do to itself.
    op.drop_index(
        op.f("ix_m05_on_time_proof_notice_message_ref"),
        table_name="on_time_proof",
        schema="m05",
    )
    op.drop_column("on_time_proof", "notice_message_ref", schema="m05")
