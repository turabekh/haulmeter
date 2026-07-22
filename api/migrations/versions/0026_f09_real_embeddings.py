"""F9 embeddings — real EMBED_DIM (1024) + HNSW cosine ANN index

Embeddings are a regenerable cache derived from source text (M2 facility reviews,
etc.), so re-dimensioning safely truncates the table and re-embeds lazily on the
next embed/search. Adds a pgvector HNSW index so cosine search scales past the
brute-force order-by used until now.

Revision ID: 0026_f09_real_embeddings
Revises: 0025_f01_authority_verification
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026_f09_real_embeddings"
down_revision: str | None = "0025_f01_authority_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "f09"
NEW_DIM = 1024
OLD_DIM = 16
INDEX = "ix_embedding_vector_hnsw"


def upgrade() -> None:
    # derived cache — clear rows so the column can be re-typed to the real width;
    # they re-embed on the next embed_and_store / search_similar.
    op.execute(f"DELETE FROM {SCHEMA}.embedding")
    op.execute(
        f"ALTER TABLE {SCHEMA}.embedding "
        f"ALTER COLUMN vector TYPE vector({NEW_DIM}) USING vector::vector({NEW_DIM})"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX} ON {SCHEMA}.embedding "
        f"USING hnsw (vector vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.{INDEX}")
    op.execute(f"DELETE FROM {SCHEMA}.embedding")
    op.execute(
        f"ALTER TABLE {SCHEMA}.embedding "
        f"ALTER COLUMN vector TYPE vector({OLD_DIM}) USING vector::vector({OLD_DIM})"
    )
