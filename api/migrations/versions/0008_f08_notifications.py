"""F8 notifications & outbound comms — notifications, templates, threads

Revision ID: 0008_f08_notifications
Revises: 0007_f07_ledger
Create Date: 2026-07-20

AI-CONTEXT: self-contained local MetaData + create_all (decision #27, HANDOFF-006):
`notification_channel` is shared by two tables, so a single shared Enum object in
one MetaData emits its CREATE TYPE exactly once. A reference-only stub for
f01.account resolves the cross-schema FKs.
"""

from collections.abc import Sequence
from datetime import time

import sqlalchemy as sa
from alembic import op

revision: str = "0008_f08_notifications"
down_revision: str | None = "0007_f07_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f08"


def _tables():
    meta = sa.MetaData()
    channel = sa.Enum(
        "push", "sms", "email", "in_app", "audio", name="notification_channel", schema=SCHEMA
    )

    sa.Table(
        "account",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        schema="f01",
    )

    prefs = sa.Table(
        "notification_prefs",
        meta,
        sa.Column("account_id", sa.Uuid(), primary_key=True),
        sa.Column("timezone", sa.String(60), nullable=False, server_default="UTC"),
        sa.Column("quiet_start", sa.Time(), nullable=False, server_default=str(time(22, 0))),
        sa.Column("quiet_end", sa.Time(), nullable=False, server_default=str(time(6, 0))),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_notification_prefs_account_id_account",
            use_alter=True,
        ),
        schema=SCHEMA,
    )

    notification = sa.Table(
        "notification",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "tier",
            sa.Enum("P0", "P1", "P2", name="notification_tier", schema=SCHEMA),
            nullable=False,
        ),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("deep_link", sa.String(300), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                "suppressed",
                "digested",
                name="notification_status",
                schema=SCHEMA,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("channel", channel, nullable=True),
        sa.Column(
            "suppress_reason",
            sa.Enum("budget", "quiet_hours", "resting", name="suppress_reason", schema=SCHEMA),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_notification_account_id_account",
            use_alter=True,
        ),
        sa.Index("ix_notification_account_id", "account_id"),
        sa.Index("ix_notification_dispatched_at", "dispatched_at"),
        schema=SCHEMA,
    )

    template = sa.Table(
        "notification_template",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("locale", sa.String(12), nullable=False, server_default="en"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "audience",
            sa.Enum("driver", "counterparty", name="template_audience", schema=SCHEMA),
            nullable=False,
        ),
        sa.Column("channel", channel, nullable=False),
        sa.Column("subject_template", sa.String(300), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("key", "locale", "version", name="uq_template_key_locale_version"),
        sa.Index("ix_notification_template_key", "key"),
        schema=SCHEMA,
    )

    thread = sa.Table(
        "outbound_thread",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("counterparty_ref", sa.Uuid(), nullable=True),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("template_key", sa.String(120), nullable=True),
        sa.Column("reply_to", sa.String(320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_outbound_thread_account_id_account",
            use_alter=True,
        ),
        sa.Index("ix_outbound_thread_account_id", "account_id"),
        sa.Index("ix_outbound_thread_counterparty_ref", "counterparty_ref"),
        schema=SCHEMA,
    )

    message = sa.Table(
        "outbound_message",
        meta,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("outbound", "inbound", name="message_direction", schema=SCHEMA),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("provider_ref", sa.String(300), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            [f"{SCHEMA}.outbound_thread.id"],
            ondelete="CASCADE",
            name="fk_outbound_message_thread_id_outbound_thread",
        ),
        sa.Index("ix_outbound_message_thread_id", "thread_id"),
        schema=SCHEMA,
    )
    return meta, [prefs, notification, template, thread, message]


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    meta, tables = _tables()
    meta.create_all(op.get_bind(), tables=tables)


def downgrade() -> None:
    meta, tables = _tables()
    meta.drop_all(op.get_bind(), tables=tables)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
