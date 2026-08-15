"""AI-CONTEXT: the m14 schema — connector, vehicle map, import watermark (E2 slice 1, D8).

THE PASTED KEY IS STORED AS CIPHERTEXT, and that is an owner decision (2026-08-15) rather
than a default. The kickoff put the key in a column and said a better home is a handoff
note, not an improvisation, so it was asked. What settled it was not the public repo — a
key was never going to be committed — it was `scripts/backup_db.sh`: this database is
dumped nightly and uploaded offsite to a GCS bucket, and A12 made that upload REQUIRED. A
plaintext column ships a working credential to somebody else's fleet telematics into a
bucket, every night, forever.

So the column holds AES-GCM ciphertext; the secret is `M14_CONNECTOR_KEY` in `infra/.env`
(0600 root:root on the VM, excluded by `deploy.sh`, empty placeholder in `.env.example`).
`key_last4` exists so a portal can show WHICH key is installed without the ciphertext ever
leaving the server.

TWO UNIQUE CONSTRAINTS, both there before the defect rather than after it — migration 0077
is one session old and its lesson was that a document which exists once should be unique in
Postgres: re-pasting a key is a CORRECTION to one connector, and re-mapping a vehicle is a
CORRECTION to one mapping. Neither is a second row.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0079_m14_recovery"
down_revision = "0078_evidence_class_source"
branch_labels = None
depends_on = None

SCHEMA = "m14"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    # AI-CONTEXT: created explicitly, then REFERENCED with `create_type=False` — the
    # pattern migration 0057 already wrote down, and this session re-learned by ignoring
    # it. A bare `sa.Enum` inside `create_table` emits its own CREATE TYPE, so the type is
    # made twice and the second fails with DuplicateObject.
    #
    # WORTH KNOWING HOW IT FAILS: alembic printed "Running upgrade" for BOTH 0078 and
    # 0079, then rolled the whole transaction back — so the log said two migrations ran
    # and the database had neither the m14 schema nor 0078's two columns. Reading the exit
    # line would have said success. Read `alembic current` and the columns.
    sa.Enum("motive", name="connector_provider", schema=SCHEMA).create(
        op.get_bind(), checkfirst=True
    )
    sa.Enum("active", "disabled", "failing", name="connector_status", schema=SCHEMA).create(
        op.get_bind(), checkfirst=True
    )
    provider = postgresql.ENUM(name="connector_provider", schema=SCHEMA, create_type=False)
    status = postgresql.ENUM(name="connector_status", schema=SCHEMA, create_type=False)

    op.create_table(
        "connector",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fleet_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("provider", provider, nullable=False),
        # never rendered, never logged, never returned by a route
        sa.Column("key_ciphertext", sa.Text(), nullable=False),
        sa.Column("key_last4", sa.String(length=4), nullable=False),
        sa.Column("status", status, nullable=False, server_default="active"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "fleet_id", "provider", name="uq_connector_fleet_provider"
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "vehicle_map",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "connector_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.connector.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider_vehicle_ref", sa.String(length=120), nullable=False),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("f01.account.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "connector_id", "provider_vehicle_ref", name="uq_vehicle_map_connector_vehicle"
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "trace_import",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "connector_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.connector.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider_vehicle_ref", sa.String(length=120), nullable=False),
        # the PROVIDER's clock, deliberately — comparing ours would drop records whenever
        # the two disagree, and that disagreement is what F12 records rather than hides
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pings_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "connector_id", "provider_vehicle_ref", name="uq_trace_import_vehicle"
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("trace_import", schema=SCHEMA)
    op.drop_table("vehicle_map", schema=SCHEMA)
    op.drop_table("connector", schema=SCHEMA)
    sa.Enum(name="connector_status", schema=SCHEMA).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="connector_provider", schema=SCHEMA).drop(op.get_bind(), checkfirst=True)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
