"""AI-CONTEXT: the m15 schema (E3 §E3.1.4).

THERE IS NO VOICEPRINT COLUMN, AND THERE IS NO D-QUESTION THAT COULD ADD ONE. E3 states
it twice — "no voiceprints, no biometric matching, ever" (§E3.1.4) and again in §E3.6's
unchanged list. This note exists because an absence leaves no other trace: a later session
asked to "recognise the speaker" or "match this voice to the driver" is being asked for the
one thing this module refused by construction, and the refusal is not a gap to fill.

THE THREE CONSTRAINTS E3 CALLS OUT ARE DECLARED HERE AS WELL AS IN THE MIGRATION, and that
is TRAPS §1.3 rather than belt-and-braces. The test database is built by
`Base.metadata.create_all`, so a constraint that lives only in a migration is never
exercised by a single test — it exists in production and nowhere the suite can see it.
That is migration 0077's lesson, and the check across the whole schema found exactly one
deviation, which means the habit holds and is worth keeping.

Retention: `turn.audio_ref` carries the 30-day driver-deletable TTL class (§E3.4.3);
cached officer, drill and sign audio is permanent content. Derived transcripts, scores and
skill state persist. The distinction is enforced by the TTL class on the F6 object, not by
this schema — what this schema owes it is that raw driver audio is reachable from exactly
one column, so a deletion sweep has one place to look.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import (
    ContentStatus,
    Difficulty,
    EntitlementKind,
    EntitlementSource,
    SessionMode,
    Speaker,
    TurnReviewStatus,
)

SCHEMA = "m15"
ACCOUNT_FK = "f01.account.id"
ORG_FK = "f01.organization.id"
DOCUMENT_FK = "f06.document.id"
EVIDENCE_LOG_FK = "f04.evidence_log.id"


class ScenarioVersion(Base):
    """A roadside check as a versioned, reproducible thing.

    AI-CONTEXT: the version is HIDDEN STATE — a driver never sees it and never picks it.
    It exists so that a reassessment can be drawn against the same scenario definition a
    baseline used, which is the only way "improved" means anything.
    """

    __tablename__ = "scenario_version"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer)
    domain_mix: Mapped[dict] = mapped_column(JSONB, default=dict)
    # AI-CONTEXT: the FACTS a scenario is built on — destination, HOS hours, cargo, trailer
    # (E3 §E3.1.2). Expected answers DERIVE from this; `intent.required_slots` only names
    # WHICH facts a question needs. Conflating the two scored a driver who answered
    # perfectly as incomplete, because the validator was matching their words against the
    # string "required". Found by running a real session, not by reading the schema.
    hidden_state: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, name="difficulty", schema=SCHEMA)
    )
    # intent KEYS rather than ids: a scenario definition is content, and content is
    # authored against stable keys. An array cannot carry a foreign key, so the engine
    # validates membership — see the scenario engine's slot validation.
    allowed_intents: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}"
    )
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", schema=SCHEMA),
        default=ContentStatus.draft,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Intent(Base):
    """What the officer is actually asking for, independent of how it is phrased."""

    __tablename__ = "intent"
    __table_args__ = (
        UniqueConstraint("key", name="uq_intent_key"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(96))
    domain: Mapped[str] = mapped_column(String(64))
    canonical_meaning: Mapped[str] = mapped_column(Text)
    required_slots: Mapped[dict] = mapped_column(JSONB, default=dict)
    difficulty_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PhraseVariant(Base):
    """One way an officer might say an intent. Holdouts are never taught.

    AI-CONTEXT: `holdout` is quality law Q-5 and it is the reason reassessment means
    anything. A holdout variant never appears in a drill or in coaching, so a driver who
    improves on one has improved at the language rather than at the item. The property
    test on the generators is what holds it — a filter a caller must remember to apply is
    a filter that will be forgotten.
    """

    __tablename__ = "phrase_variant"
    __table_args__ = (
        Index("ix_phrase_variant_intent_status", "intent_id", "status"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    intent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.intent.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, name="difficulty", schema=SCHEMA)
    )
    voice: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # cached officer audio is PERMANENT content, not the 30-day TTL class
    audio_ref: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(DOCUMENT_FK), nullable=True
    )
    holdout: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", schema=SCHEMA),
        default=ContentStatus.draft,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)


class SignItem(Base):
    """Road signs — the non-verbal half of the roadside check."""

    __tablename__ = "sign_item"
    __table_args__ = (
        UniqueConstraint("key", name="uq_sign_item_key"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(96))
    rendering_ref: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(DOCUMENT_FK), nullable=True
    )
    meaning: Mapped[str] = mapped_column(Text)
    dynamic: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", schema=SCHEMA),
        default=ContentStatus.draft,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)


class CoachingContent(Base):
    """The teaching, in the driver's own language. Module data, not F15 catalogue strings.

    AI-CONTEXT: quality law Q-9 — no silent English. A missing locale renders the honest
    empty state rather than falling back to English, which is F15's criterion 5 applied to
    module data. That is a rendering rule; what the schema owes it is that absence is
    representable, so there is no row rather than a row full of English.
    """

    __tablename__ = "coaching_content"
    __table_args__ = (
        Index("ix_coaching_content_locale", "locale"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    intent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.intent.id"), nullable=True, index=True
    )
    sign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.sign_item.id"), nullable=True, index=True
    )
    locale: Mapped[str] = mapped_column(String(12))
    explanation: Mapped[str] = mapped_column(Text)
    glosses: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    review_status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", schema=SCHEMA),
        default=ContentStatus.draft,
    )


class Session(Base):
    """One sitting: a check, a drill, a reassessment, or private practice.

    AI-CONTEXT: `account_id` and `guest_token` are BOTH nullable because a session may
    begin before anyone has an account — that is M15-FR1's whole point, and the claim
    attaches the rows afterwards. `guest_token` carries no foreign key yet: F1's guest
    principal table lands in this session's F1 extension commit, and a cross-schema
    constraint added in the same breath as the table it points at is the safer order.

    `band` is a STRING, not an enum, and that is deliberate. E3 never enumerates the
    bands, and what we tell a driver they are is a product judgment rather than a schema
    detail — freezing an invented vocabulary into a Postgres type is how a later session
    inherits a set nobody chose. Recorded as an owner question in the Session-A handoff.

    `provisional` is quality law Q-8: until rolling human agreement clears the threshold,
    every org-facing band renders the provisional label.
    """

    __tablename__ = "session"
    __table_args__ = (
        # E3 §E3.1.4: ONE LIVE SESSION PER GUEST PRINCIPAL. Partial, because the
        # restriction is on the LIVE one — a guest who finishes a check and starts
        # another is ordinary, and only an unfinished session is exclusive. The predicate
        # also excludes NULL tokens, or every authenticated session would collide with
        # every other on a NULL guest_token.
        Index(
            "uq_session_live_guest",
            "guest_token",
            unique=True,
            postgresql_where=text("completed_at IS NULL AND guest_token IS NOT NULL"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK), nullable=True, index=True
    )
    guest_token: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(ORG_FK), nullable=True, index=True)
    scenario_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.scenario_version.id")
    )
    mode: Mapped[SessionMode] = mapped_column(Enum(SessionMode, name="session_mode", schema=SCHEMA))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provisional: Mapped[bool] = mapped_column(Boolean, default=True)


class Turn(Base):
    """One exchange inside a session. The raw audio here is the 30-day TTL class."""

    __tablename__ = "turn"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_turn_session_seq"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.session.id"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[Speaker] = mapped_column(Enum(Speaker, name="speaker", schema=SCHEMA))
    # AI-CONTEXT: the ONE column holding raw driver audio, and the 30-day driver-deletable
    # TTL class rides on it (§E3.4.3). Keeping it to one column is what gives a deletion
    # sweep a single place to look.
    audio_ref: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(DOCUMENT_FK), nullable=True
    )
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    asr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.intent.id"), nullable=True
    )
    expected_slots: Mapped[dict] = mapped_column(JSONB, default=dict)
    observed_slots: Mapped[dict] = mapped_column(JSONB, default=dict)
    scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    failure_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}"
    )
    review_status: Mapped[TurnReviewStatus] = mapped_column(
        Enum(TurnReviewStatus, name="turn_review_status", schema=SCHEMA),
        default=TurnReviewStatus.not_needed,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelAnswer(Base):
    """A clear answer a driver SHADOWS (M15-FR5), in English.

    AI-CONTEXT: deliberately NOT a `PhraseVariant`. That table is "one way an officer might
    say an intent", and the session loop draws its questions from it — a model answer
    living there could be asked as a question, which is the exchange back to front.

    Shaped like one on purpose, though: same `status`, `version` and `audio_ref`, so the
    Q-6 publish path, the admin review surface and the TTS job all handle it without
    special cases.
    """

    __tablename__ = "model_answer"
    __table_args__ = (
        Index("ix_model_answer_intent_status", "intent_id", "status"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    intent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.intent.id"))
    text: Mapped[str] = mapped_column(Text)
    # the answer is ENGLISH — it is what the driver is practising. The coaching that
    # explains it is in their own language, and lives in `coaching_content`.
    locale: Mapped[str] = mapped_column(String(12), default="en", server_default="en")
    audio_ref: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("f06.document.id"), nullable=True
    )
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status", schema=SCHEMA),
        default=ContentStatus.draft,
        server_default=ContentStatus.draft.value,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SkillState(Base):
    """Spaced repetition per driver per variant."""

    __tablename__ = "skill_state"
    __table_args__ = (
        # E3 §E3.1.4: ONE skill_state ROW PER ACCOUNT × VARIANT. A second row is a
        # duplicate history, and spaced repetition run against two histories of the same
        # item schedules it twice.
        UniqueConstraint("account_id", "variant_id", name="uq_skill_state_account_variant"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(ACCOUNT_FK), index=True)
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.phrase_variant.id"))
    exposure_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    srs_interval: Mapped[int] = mapped_column(Integer, default=0)
    srs_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    difficulty_ceiling: Mapped[Difficulty | None] = mapped_column(
        Enum(Difficulty, name="difficulty", schema=SCHEMA), nullable=True
    )


class DrillPlan(Base):
    """The 30-day plan, one row per day."""

    __tablename__ = "drill_plan"
    __table_args__ = (
        UniqueConstraint("account_id", "plan_day", name="uq_drill_plan_account_day"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(ACCOUNT_FK), index=True)
    plan_day: Mapped[int] = mapped_column(Integer)
    items: Mapped[dict] = mapped_column(JSONB, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Entitlement(Base):
    """Who may use the sponsored features, and for how long.

    AI-CONTEXT: this is what scopes the 45-day gate window to pilot orgs WITHOUT a per-org
    flag (§E3.1.8). `source` may read `stripe`, and Phase A has no code path that writes
    it — D15 is open, `m15_billing` does not exist, and an enum member reaches nothing.
    """

    __tablename__ = "entitlement"
    __table_args__ = (
        # E3 §E3.1.4: ONE ENTITLEMENT PER SUBJECT × KIND × WINDOW. Two rows for the same
        # window is a double grant, and the second is what silently extends access nobody
        # granted.
        #
        # AI-CONTEXT: TWO PARTIAL INDEXES RATHER THAN ONE UNIQUE CONSTRAINT, and a
        # red-first test is the only reason this is not still wrong. A single
        # `UniqueConstraint(subject_account_id, subject_org_id, kind, starts_at, ends_at)`
        # DOES NOT FIRE: an account-subject row leaves `subject_org_id` NULL, Postgres
        # treats NULLs as distinct in a unique index, and two identical grants both
        # insert. The constraint existed, read correctly, and enforced nothing — which is
        # this codebase's oldest pattern wearing a schema.
        #
        # Split by subject, each partial on its own subject being present, the rule is
        # enforced for both shapes and the CHECK below is what guarantees a row is exactly
        # one shape rather than neither or both.
        # NULLS NOT DISTINCT is the second half of the fix, and it was found by probing
        # a live database rather than by this suite. `ends_at` is NULL for an ordinary
        # open-ended grant, and a unique index treats those NULLs as distinct too — so
        # splitting by subject cured one nullable column and left the next one doing
        # exactly the same thing. Two identical open-ended grants both inserted while the
        # tests were green.
        Index(
            "uq_entitlement_account_kind_window",
            "subject_account_id",
            "kind",
            "starts_at",
            "ends_at",
            unique=True,
            postgresql_where=text("subject_account_id IS NOT NULL"),
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "uq_entitlement_org_kind_window",
            "subject_org_id",
            "kind",
            "starts_at",
            "ends_at",
            unique=True,
            postgresql_where=text("subject_org_id IS NOT NULL"),
            postgresql_nulls_not_distinct=True,
        ),
        # E3 §E3.1.4 writes the subject as `account_id | org_id` — an exclusive or. A row
        # with neither is an entitlement granted to nobody; a row with both is an
        # entitlement two different queries would each claim.
        CheckConstraint(
            "(subject_account_id IS NOT NULL) <> (subject_org_id IS NOT NULL)",
            name="ck_entitlement_exactly_one_subject",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    subject_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK), nullable=True, index=True
    )
    subject_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ORG_FK), nullable=True, index=True
    )
    kind: Mapped[EntitlementKind] = mapped_column(
        Enum(EntitlementKind, name="entitlement_kind", schema=SCHEMA)
    )
    source: Mapped[EntitlementSource] = mapped_column(
        Enum(EntitlementSource, name="entitlement_source", schema=SCHEMA),
        default=EntitlementSource.admin,
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(ACCOUNT_FK), nullable=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrainingRecord(Base):
    """The dated, hashed, verifiable record — TRAINING, never assessment.

    AI-CONTEXT: quality law Q-7, and the difference is load-bearing rather than
    terminological. `m15_assessment` does not exist and is gated on D19. The words
    *assessment*, *certificate*, *FMCSA approved* and *pass* are forbidden strings in the
    template and in the rendered PDF text, and the test greps both — a template that is
    clean while the PDF renders otherwise is the failure this guards.
    """

    __tablename__ = "training_record"
    __table_args__ = (
        UniqueConstraint("verification_token", name="uq_training_record_token"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(ACCOUNT_FK), index=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(ORG_FK), nullable=True)
    evidence_ref: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(EVIDENCE_LOG_FK), nullable=True
    )
    pdf_ref: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(DOCUMENT_FK), nullable=True)
    hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_token: Mapped[str] = mapped_column(String(64))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewSample(Base):
    """The calibration harness's row: what the machine said, what a human said.

    AI-CONTEXT: quality law Q-8's rolling agreement metric is computed from these, and
    until it clears the threshold every org-facing band renders provisional. The metric is
    the gate's own fixture — a number that governs what a driver is told about themselves
    should be measured, not asserted.
    """

    __tablename__ = "review_sample"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    turn_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.turn.id"), index=True)
    ai_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    human_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agree: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
