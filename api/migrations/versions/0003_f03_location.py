"""F3 location & geofence engine — pings, arming, presence, events, tuning

Revision ID: 0003_f03_location
Revises: 0002_f02_facility
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0003_f03_location"
down_revision: str | None = "0002_f02_facility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f03"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    location_mode = sa.Enum(
        "significant_change", "high_accuracy", name="location_mode", schema=SCHEMA
    )
    event_type = sa.Enum("ENTER", "EXIT", "DWELL_TICK", name="geofence_event_type", schema=SCHEMA)

    op.create_table(
        "location_ping",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("client_skew_ms", sa.Integer(), nullable=True),
        sa.Column("gps_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "gps_time_divergent", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("speed_mps", sa.Float(), nullable=True),
        sa.Column("mode", location_mode, nullable=False, server_default="significant_change"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_location_ping_account_id_account",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_location_ping_account_id", "location_ping", ["account_id"], schema=SCHEMA)
    op.create_index("ix_location_ping_occurred_at", "location_ping", ["occurred_at"], schema=SCHEMA)
    op.execute(f"CREATE INDEX ix_location_ping_geom ON {SCHEMA}.location_ping USING gist (geom)")

    op.create_table(
        "geofence_arming",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("radius_m", sa.Float(), nullable=True),
        sa.Column("armed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("disarmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_geofence_arming_account_id_account",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["f02.facility.id"],
            ondelete="CASCADE",
            name="fk_geofence_arming_facility_id_facility",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_geofence_arming_account_id", "geofence_arming", ["account_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_geofence_arming_facility_id", "geofence_arming", ["facility_id"], schema=SCHEMA
    )

    op.create_table(
        "facility_geofence",
        sa.Column("facility_id", sa.Uuid(), primary_key=True),
        sa.Column("radius_m", sa.Float(), nullable=False),
        sa.Column("confirmed_arrivals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["f02.facility.id"],
            ondelete="CASCADE",
            name="fk_facility_geofence_facility_id_facility",
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "geofence_presence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_tick_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_geofence_presence_account_id_account",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["f02.facility.id"],
            ondelete="CASCADE",
            name="fk_geofence_presence_facility_id_facility",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_geofence_presence_account_id", "geofence_presence", ["account_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_geofence_presence_facility_id", "geofence_presence", ["facility_id"], schema=SCHEMA
    )
    op.create_index("ix_geofence_presence_active", "geofence_presence", ["active"], schema=SCHEMA)

    op.create_table(
        "geofence_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["f01.account.id"],
            ondelete="CASCADE",
            name="fk_geofence_event_account_id_account",
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["f02.facility.id"],
            ondelete="CASCADE",
            name="fk_geofence_event_facility_id_facility",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_geofence_event_account_id", "geofence_event", ["account_id"], schema=SCHEMA)
    op.create_index(
        "ix_geofence_event_facility_id", "geofence_event", ["facility_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_geofence_event_occurred_at", "geofence_event", ["occurred_at"], schema=SCHEMA
    )
    op.execute(f"CREATE INDEX ix_geofence_event_geom ON {SCHEMA}.geofence_event USING gist (geom)")


def downgrade() -> None:
    op.drop_table("geofence_event", schema=SCHEMA)
    op.drop_table("geofence_presence", schema=SCHEMA)
    op.drop_table("facility_geofence", schema=SCHEMA)
    op.drop_table("geofence_arming", schema=SCHEMA)
    op.drop_table("location_ping", schema=SCHEMA)
    for enum_name in ("geofence_event_type", "location_mode"):
        op.execute(f"DROP TYPE IF EXISTS {SCHEMA}.{enum_name}")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
