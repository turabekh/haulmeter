"""AI-CONTEXT: `fee` joins ReceivableKind — the platform's contingency share (J1-R1).

Every existing kind — detention, tonu, layover, lumper — is money a BROKER owes a
DRIVER. `fee` is the first one pointing the other way: money the driver owes the
platform out of a recovery that has already landed in their own bank. Same table, same
subject column, opposite direction, and the direction is carried by the kind rather than
by a sign on the amount, because a negative receivable would make every existing sum
wrong in a way no test would notice.

WHY A RECEIVABLE AND NOT A LEDGER ENTRY, which is the whole of R1: no cash crosses this
platform on a driver's own recovery. `m09_money/domain/service.py` has recorded that
reasoning since the recovery path was built, and posting cash_clearing -> driver_payable
here would invent a movement we never handled. A receivable records that something is
OWED; a journal entry records that something MOVED. Only the first is true today.

ADD VALUE, never a type rebuild. Postgres 12+ takes `ALTER TYPE ... ADD VALUE` inside a
transaction provided the new label is not USED in the same transaction, which it is not —
nothing writes a `fee` row until the flag is switched on. The rebuild path (create new
type, cast the column, drop the old) is what HANDOFF-125 §4.9 records as needing the
column DEFAULT dropped first; it is avoided entirely here rather than performed carefully.

IRREVERSIBLE, and said out loud rather than faked. Postgres cannot drop a label from an
enum, so `downgrade` raises instead of silently doing nothing — a downgrade that reports
success while leaving the type unchanged is worse than one that refuses.
"""

from alembic import op

revision = "0083_receivable_kind_fee"
down_revision = "0082_dunning_final_notice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE f07.receivable_kind ADD VALUE IF NOT EXISTS 'fee'")


def downgrade() -> None:
    raise NotImplementedError(
        "Postgres cannot remove a value from an enum type. Reversing this means "
        "rebuilding f07.receivable_kind, which is a data migration rather than a "
        "downgrade — and any 'fee' rows would have to be dealt with first."
    )
