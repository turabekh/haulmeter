"""AI-CONTEXT: the m15 schema (PRD Extension E3, owner decision D14 scope (b)).

TWELVE TABLES AND NO VOICEPRINT COLUMN. E3 §E3.1.4 states it twice and §E3.6 restates it
in the unchanged list: no voiceprints, no biometric matching, ever, and no D-question in
§E3.7 could add one. The absence is the design; it leaves no other trace, so it is written
here where a later session adding a column will read it.

THE ENUMS ARE CREATED EXPLICITLY AND REFERENCED WITH `create_type=False`, which is
migration 0057's lesson that 0079 re-learned the hard way. A bare `sa.Enum` inside
`create_table` emits its own CREATE TYPE, so the type is made twice and the second fails.
How it fails is the part worth keeping: alembic printed "Running upgrade" for BOTH pending
migrations and then rolled the whole transaction back — the log claimed two migrations ran
and the database had neither. Reading the exit line would have reported success. Read
`alembic current` and query `information_schema`.

THREE CONSTRAINTS ARE LOAD-BEARING AND ARE DECLARED ON THE MODELS AS WELL AS HERE
(TRAPS §1.3): one live session per guest principal, one skill_state per account × variant,
one entitlement per subject × kind × window. The test database is built by
`create_all`, so a constraint that exists only in this file is never exercised by a single
test — it would hold in production and nowhere the suite can see it.

THE ENTITLEMENT ONE WAS WRONG TWICE BEFORE IT WAS RIGHT, and both mistakes are the same
mistake: **a unique index over a nullable column is not unique for the rows where that
column is null, and those rows are usually the ordinary ones.**

· First attempt — one `UniqueConstraint(subject_account_id, subject_org_id, kind,
  starts_at, ends_at)`. It reads exactly like the rule E3 states and it enforces nothing:
  a subject is an account OR an org, so one of those columns is always NULL, Postgres
  treats NULLs as distinct, and two identical grants both insert. A red-first test caught
  this one.
· Second attempt — split into two partial indexes by subject. That cured
  `subject_org_id` and left `ends_at` doing the identical thing one column over: an
  open-ended grant has no end date. **The suite was green and a live database still
  accepted the duplicate**, because the test happened to set an end date. Probing the box
  is what found it — which is this project's own rule about the exit line, one layer down.

Hence `NULLS NOT DISTINCT` (PG15+) on both, plus a CHECK that a row has exactly one
subject. Verify by inserting a duplicate, not by reading the index definition.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0084_m15_roadside"
down_revision = "0083_receivable_kind_fee"
branch_labels = None
depends_on = None

SCHEMA = "m15"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    sa.Enum("clear", "natural", name="difficulty", schema=SCHEMA).create(
        op.get_bind(), checkfirst=True
    )
    sa.Enum("draft", "reviewed", "released", name="content_status", schema=SCHEMA).create(
        op.get_bind(), checkfirst=True
    )
    sa.Enum(
        "check", "drill", "reassessment", "practice", name="session_mode", schema=SCHEMA
    ).create(op.get_bind(), checkfirst=True)
    sa.Enum("officer", "driver", name="speaker", schema=SCHEMA).create(
        op.get_bind(), checkfirst=True
    )
    sa.Enum(
        "not_needed", "review_needed", "reviewed", name="turn_review_status", schema=SCHEMA
    ).create(op.get_bind(), checkfirst=True)
    sa.Enum("program", "seat", name="entitlement_kind", schema=SCHEMA).create(
        op.get_bind(), checkfirst=True
    )
    sa.Enum("admin", "stripe", name="entitlement_source", schema=SCHEMA).create(
        op.get_bind(), checkfirst=True
    )

    difficulty = postgresql.ENUM(name="difficulty", schema=SCHEMA, create_type=False)
    content_status = postgresql.ENUM(name="content_status", schema=SCHEMA, create_type=False)
    session_mode = postgresql.ENUM(name="session_mode", schema=SCHEMA, create_type=False)
    speaker = postgresql.ENUM(name="speaker", schema=SCHEMA, create_type=False)
    turn_review = postgresql.ENUM(name="turn_review_status", schema=SCHEMA, create_type=False)
    ent_kind = postgresql.ENUM(name="entitlement_kind", schema=SCHEMA, create_type=False)
    ent_source = postgresql.ENUM(name="entitlement_source", schema=SCHEMA, create_type=False)

    op.create_table(
        "scenario_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("domain_mix", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("difficulty", difficulty, nullable=False),
        sa.Column(
            "allowed_intents",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("environment", sa.String(length=64), nullable=True),
        sa.Column("status", content_status, nullable=False, server_default="draft"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "intent",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(length=96), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("canonical_meaning", sa.Text(), nullable=False),
        sa.Column("required_slots", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("difficulty_rating", sa.Integer(), nullable=True),
        sa.UniqueConstraint("key", name="uq_intent_key"),
        schema=SCHEMA,
    )

    op.create_table(
        "phrase_variant",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "intent_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.intent.id"), nullable=False, index=True
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("difficulty", difficulty, nullable=False),
        sa.Column("voice", sa.String(length=64), nullable=True),
        sa.Column("audio_ref", sa.Uuid(), sa.ForeignKey("f06.document.id"), nullable=True),
        sa.Column("holdout", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", content_status, nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_phrase_variant_intent_status", "phrase_variant", ["intent_id", "status"], schema=SCHEMA
    )

    op.create_table(
        "sign_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(length=96), nullable=False),
        sa.Column("rendering_ref", sa.Uuid(), sa.ForeignKey("f06.document.id"), nullable=True),
        sa.Column("meaning", sa.Text(), nullable=False),
        sa.Column("dynamic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", content_status, nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("key", name="uq_sign_item_key"),
        schema=SCHEMA,
    )

    op.create_table(
        "coaching_content",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "intent_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.intent.id"), nullable=True, index=True
        ),
        sa.Column(
            "sign_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.sign_item.id"), nullable=True, index=True
        ),
        sa.Column("locale", sa.String(length=12), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("glosses", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("review_status", content_status, nullable=False, server_default="draft"),
        schema=SCHEMA,
    )
    op.create_index("ix_coaching_content_locale", "coaching_content", ["locale"], schema=SCHEMA)

    op.create_table(
        "session",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id", sa.Uuid(), sa.ForeignKey("f01.account.id"), nullable=True, index=True
        ),
        # AI-CONTEXT: no foreign key yet, deliberately. F1's guest-principal table lands in
        # this session's F1 extension commit, and a cross-schema constraint is added in the
        # same breath as the table it points at rather than ahead of it.
        sa.Column("guest_token", sa.Uuid(), nullable=True, index=True),
        sa.Column(
            "org_id", sa.Uuid(), sa.ForeignKey("f01.organization.id"), nullable=True, index=True
        ),
        sa.Column(
            "scenario_version_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.scenario_version.id"),
            nullable=False,
        ),
        sa.Column("mode", session_mode, nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("band", sa.String(length=32), nullable=True),
        sa.Column("provisional", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema=SCHEMA,
    )
    # one LIVE session per guest principal (E3 §E3.1.4). Declared on the model too.
    op.create_index(
        "uq_session_live_guest",
        "session",
        ["guest_token"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("completed_at IS NULL AND guest_token IS NOT NULL"),
    )

    op.create_table(
        "turn",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey(f"{SCHEMA}.session.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("speaker", speaker, nullable=False),
        # the one column holding raw driver audio — the 30-day driver-deletable TTL class
        sa.Column("audio_ref", sa.Uuid(), sa.ForeignKey("f06.document.id"), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("asr_confidence", sa.Float(), nullable=True),
        sa.Column("intent_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.intent.id"), nullable=True),
        sa.Column("expected_slots", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("observed_slots", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("scores", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "failure_tags", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"
        ),
        sa.Column("review_status", turn_review, nullable=False, server_default="not_needed"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("session_id", "seq", name="uq_turn_session_seq"),
        schema=SCHEMA,
    )

    op.create_table(
        "skill_state",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id", sa.Uuid(), sa.ForeignKey("f01.account.id"), nullable=False, index=True
        ),
        sa.Column(
            "variant_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.phrase_variant.id"), nullable=False
        ),
        sa.Column("exposure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("srs_interval", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("srs_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("difficulty_ceiling", difficulty, nullable=True),
        # one row per account × variant (E3 §E3.1.4). Declared on the model too.
        sa.UniqueConstraint("account_id", "variant_id", name="uq_skill_state_account_variant"),
        schema=SCHEMA,
    )

    op.create_table(
        "drill_plan",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id", sa.Uuid(), sa.ForeignKey("f01.account.id"), nullable=False, index=True
        ),
        sa.Column("plan_day", sa.Integer(), nullable=False),
        sa.Column("items", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("account_id", "plan_day", name="uq_drill_plan_account_day"),
        schema=SCHEMA,
    )

    op.create_table(
        "entitlement",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "subject_account_id",
            sa.Uuid(),
            sa.ForeignKey("f01.account.id"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "subject_org_id",
            sa.Uuid(),
            sa.ForeignKey("f01.organization.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("kind", ent_kind, nullable=False),
        # `stripe` is a LABEL. Phase A has no code path that writes it — D15 is OPEN and
        # `m15_billing` does not exist. An enum member reaches nothing.
        sa.Column("source", ent_source, nullable=False, server_default="admin"),
        sa.Column("granted_by", sa.Uuid(), sa.ForeignKey("f01.account.id"), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        # E3 §E3.1.4 writes the subject as `account_id | org_id` — an exclusive or.
        sa.CheckConstraint(
            "(subject_account_id IS NOT NULL) <> (subject_org_id IS NOT NULL)",
            name="ck_entitlement_exactly_one_subject",
        ),
        schema=SCHEMA,
    )
    # AI-CONTEXT: one entitlement per subject × kind × window (E3 §E3.1.4), as TWO partial
    # indexes rather than one unique constraint — and a red-first test is the only reason
    # this is not still wrong. A single UNIQUE over both subject columns DOES NOT FIRE:
    # an account-subject row leaves `subject_org_id` NULL, Postgres treats NULLs as
    # distinct, and two identical grants both insert. Declared on the model too, so the
    # suite exercises them (TRAPS §1.3).
    op.create_index(
        "uq_entitlement_account_kind_window",
        "entitlement",
        ["subject_account_id", "kind", "starts_at", "ends_at"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("subject_account_id IS NOT NULL"),
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(
        "uq_entitlement_org_kind_window",
        "entitlement",
        ["subject_org_id", "kind", "starts_at", "ends_at"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("subject_org_id IS NOT NULL"),
        postgresql_nulls_not_distinct=True,
    )

    op.create_table(
        "training_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id", sa.Uuid(), sa.ForeignKey("f01.account.id"), nullable=False, index=True
        ),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("f01.organization.id"), nullable=True),
        sa.Column("evidence_ref", sa.Uuid(), sa.ForeignKey("f04.evidence_log.id"), nullable=True),
        sa.Column("pdf_ref", sa.Uuid(), sa.ForeignKey("f06.document.id"), nullable=True),
        sa.Column("hash", sa.String(length=128), nullable=True),
        sa.Column("verification_token", sa.String(length=64), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("verification_token", name="uq_training_record_token"),
        schema=SCHEMA,
    )

    op.create_table(
        "review_sample",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "turn_id", sa.Uuid(), sa.ForeignKey(f"{SCHEMA}.turn.id"), nullable=False, index=True
        ),
        sa.Column("ai_band", sa.String(length=32), nullable=True),
        sa.Column("human_band", sa.String(length=32), nullable=True),
        sa.Column("reviewer", sa.String(length=128), nullable=True),
        sa.Column("agree", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in (
        "review_sample",
        "training_record",
        "entitlement",
        "drill_plan",
        "skill_state",
        "turn",
        "session",
        "coaching_content",
        "sign_item",
        "phrase_variant",
        "intent",
        "scenario_version",
    ):
        op.drop_table(table, schema=SCHEMA)

    for name in (
        "entitlement_source",
        "entitlement_kind",
        "turn_review_status",
        "speaker",
        "session_mode",
        "content_status",
        "difficulty",
    ):
        sa.Enum(name=name, schema=SCHEMA).drop(op.get_bind(), checkfirst=True)

    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
