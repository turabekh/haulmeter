"""AI-CONTEXT: the pack rides WITH the email, not only behind a link.

Owner request: "when we send the package to brokers, can we send actual pdf instead of
url". Resolved as BOTH, which is the version that loses nothing —

§17 specifies "plain, short, professional; one link; no images", and §23's outbound-artifacts
entry chose the link for a reason worth keeping: *"The **first** open is written into the
chain because 'they opened it on the 12th' is evidence."* An attachment cannot be tracked,
expired or revoked, so replacing the link would trade a fact a dispute can use for a
convenience. Keeping both means the clerk opens the document from their inbox AND the
product still records that they did. Still exactly one link, so §17's rule survives.

A KEY, NOT THE BYTES. Delivery is asynchronous now, so the sweep — not the request — has to
produce the attachment a minute later. Storing the document on the row would put a
multi-megabyte PDF in Postgres for every send; the key points at the copy F4 already
pinned, which is the same copy the link serves. One document, one place, two ways in.

NOTHING IS BACKFILLED. Every existing row is a message that has already gone or already
failed; attaching a pack to it retroactively would describe a delivery that did not happen.

SIZE IS CAPPED IN CODE, not here (`MAX_EMAIL_ATTACHMENT_MB`, 10). Measured on real packs:
96 KB median, 196 KB max today, and 2,230 KB for a pack carrying four real downscaled
photographs — a whole-load record with two dozen would approach the limit corporate filters
enforce. Over the cap the mail still goes with its link; a bounced notice is worse than a
linked one.
"""

import sqlalchemy as sa
from alembic import op

revision = "0076_message_attachment"
down_revision = "0075_notification_queued"
branch_labels = None
depends_on = None

SCHEMA = "f08"


def upgrade() -> None:
    op.add_column(
        "outbound_message",
        sa.Column("attachment_key", sa.String(length=600), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "outbound_message",
        sa.Column("attachment_name", sa.String(length=200), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    # AI-CONTEXT: the pack OBJECTS are deliberately untouched. They are what the link
    # serves — dropping them here would revoke every shared document to undo a column.
    op.drop_column("outbound_message", "attachment_name", schema=SCHEMA)
    op.drop_column("outbound_message", "attachment_key", schema=SCHEMA)
