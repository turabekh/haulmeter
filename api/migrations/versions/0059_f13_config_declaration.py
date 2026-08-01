"""AI-CONTEXT: F13 config DECLARATIONS — what is tunable, as opposed to what is tuned.

`/admin/config` listed `ConfigEntry` rows, which exist only once someone has set them,
so an unset key was invisible and guessing it was the only way in. A1 req 1's capture
checklist is the first config key any component actually reads, and it would have
shipped as configuration nobody could find.
"""

import sqlalchemy as sa
from alembic import op

revision = "0059_f13_config_decl"
down_revision = "0058_a01_checklist_doc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "config_declaration",
        sa.Column("key", sa.String(length=120), primary_key=True),
        sa.Column("scope", sa.String(length=60), nullable=False, server_default="global"),
        sa.Column("default_value", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column(
            "declared_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="f13",
    )
    op.create_index(
        "ix_f13_config_declaration_scope", "config_declaration", ["scope"], schema="f13"
    )


def downgrade() -> None:
    op.drop_index("ix_f13_config_declaration_scope", table_name="config_declaration", schema="f13")
    op.drop_table("config_declaration", schema="f13")
