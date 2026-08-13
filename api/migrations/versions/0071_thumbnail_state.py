"""AI-CONTEXT: derivatives get a column, because "thumbnail" was only ever a variable.

`EvidenceSurface` and `LoadRecordSurface` each hold a map called `thumbs` and render it
into a box a few dozen dp across. What went in it was the ORIGINAL — there is no resize
anywhere in this product, on either side of the wire — so opening a past load downloaded
every full-size photograph of every stop to draw a contact sheet.

ONE COLUMN, NOT TWO. The derivative's key is `<storage_key>.thumb.jpg`, always derivable
from the row that is already there, so storing it as well would be a second fact to keep
in step with the first. All this records is whether we have TRIED.

NULL is the pre-existing state and it is the correct one for every existing row: the job
has not reached it yet. That is what makes this migration its own backfill — 89 evidence
artifacts and 106 documents on the dev box come out of it as work to do rather than as
rows silently marked done. Nothing is written here that a later job cannot rewrite.

"none" is a SUCCESS, not a failure: a PDF rate con has no image to derive from, and
recording that stops it being re-decoded every five minutes forever. The distinction
matters because these two live in one column and only one of them is worth retrying.

Indexed because the job's only query is "rows where this is NULL", and on a table that
grows one row per photograph per stop, a sequential scan every five minutes is the kind
of cost that is invisible until it is not.
"""

import sqlalchemy as sa
from alembic import op

revision = "0071_thumbnail_state"
down_revision = "0070_m05_packet_discarded"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column("thumbnail_state", sa.String(length=16), nullable=True),
        schema="f06",
    )
    op.create_index(
        op.f("ix_f06_document_thumbnail_state"),
        "document",
        ["thumbnail_state"],
        unique=False,
        schema="f06",
    )
    op.add_column(
        "evidence_artifact",
        sa.Column("thumbnail_state", sa.String(length=16), nullable=True),
        schema="f04",
    )
    op.create_index(
        op.f("ix_f04_evidence_artifact_thumbnail_state"),
        "evidence_artifact",
        ["thumbnail_state"],
        unique=False,
        schema="f04",
    )


def downgrade() -> None:
    # AI-CONTEXT: the derivative OBJECTS in storage are deliberately left alone. They are
    # regenerable from the originals and cost a few KB each, and a downgrade that deleted
    # them would make re-upgrading pay for every one again — while a downgrade that
    # deleted the wrong key by a suffix-matching mistake would delete the photograph. The
    # column goes; the bytes are not this migration's to destroy.
    op.drop_index(
        op.f("ix_f04_evidence_artifact_thumbnail_state"),
        table_name="evidence_artifact",
        schema="f04",
    )
    op.drop_column("evidence_artifact", "thumbnail_state", schema="f04")
    op.drop_index(op.f("ix_f06_document_thumbnail_state"), table_name="document", schema="f06")
    op.drop_column("document", "thumbnail_state", schema="f06")
