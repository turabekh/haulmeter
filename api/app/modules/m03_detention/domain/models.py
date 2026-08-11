import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import ClaimMode, ClaimState, DetentionTrigger

SCHEMA = "m03"
ACCOUNT_FK = "f01.account.id"


class DetentionClaim(Base):
    """AI-CONTEXT: one OPEN claim per stop, and the rule lives in Postgres (finding F1).

    `claim_for_stop(...) or start_claim(...)` at the arrival endpoint is a check-then-act:
    it reads rows a concurrent transaction has not committed yet, so two arrivals for one
    stop both missed and both inserted. After that `claim_for_stop`'s `db.scalar` RAISES
    on the multiple it finds, and every read of that stop's money breaks.

    The predicate is `state = 'open'` rather than the whole column because a stop
    legitimately accumulates history — a claim is filed, the driver returns to the same
    dock on another load. Only the open one is the singleton, which is the predicate the
    module's own reads already select on. Migration 0067; `uq_journal_entry_type_ref` on
    F7 is the same pattern for the same reason.
    """

    __tablename__ = "detention_claim"
    __table_args__ = (
        Index(
            "uq_detention_claim_open_stop",
            "stop_ref",
            unique=True,
            postgresql_where=text("state = 'open'"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    stop_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    facility_ref: Mapped[uuid.UUID] = mapped_column()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    counterparty_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    mode: Mapped[ClaimMode] = mapped_column(Enum(ClaimMode, name="claim_mode", schema=SCHEMA))
    trigger: Mapped[DetentionTrigger] = mapped_column(
        Enum(DetentionTrigger, name="detention_trigger", schema=SCHEMA),
        default=DetentionTrigger.arrival,
    )
    free_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detention_rate_cents_per_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detention_seconds: Mapped[int] = mapped_column(Integer, default=0)
    amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    evidence_log_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    receivable_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    start_notice_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # AI-CONTEXT: which F8 message row carries the start notice (finding F5). The two
    # columns say DIFFERENT things and both are needed: the ref records that we decided
    # to send and is written on every attempt, `start_notice_sent_at` records that it
    # actually went and is written only when the message row has `sent_at`. Before this
    # the second was written unconditionally, so a claim asserted "the broker was told at
    # 10:05" beside a `smtp-failed-…` row — into the evidence pack a dispute turns on.
    start_notice_message_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    # the broker's "free time is nearly up" warning (M3-FR3, finding F7). Deliberately
    # NOT `start_notice_sent_at`: that column means the clock STARTED, which is the fact
    # the evidence event asserts, and a warning is not that fact.
    pre_notice_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # AI-CONTEXT: the DRIVER's two alerts, deliberately separate from
    # `start_notice_sent_at` above — which records the BROKER's notice (§23 entry 106).
    # Two audiences, two records: one column would have made "the driver has been told"
    # mean "the counterparty was emailed", and those come from different code paths at
    # different times. Each is set when the alert is DISPATCHED, not delivered, so a
    # notification F8 suppresses is not re-offered every minute until one gets through.
    driver_start_alert_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    driver_warning_alert_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # AI-CONTEXT: when this claim began watching the stop (§23 entry 73). The clock may
    # not start before it, which is what keeps a previous visit to the same dock out of
    # this load's money. Explicit rather than read off `created_at`: the anchor the
    # amount depends on should be statable by a caller and printable on the invoice.
    clock_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # AI-CONTEXT: the M3-FR6 follow-up cadence (finding F6). `dunning_schedule` computed
    # day 3 / 10 / 21 and had exactly one caller — its own unit test — so no broker has
    # ever been chased. One column per action, not one "last dunned at": the three are
    # distinct documents with distinct subjects, and a single timestamp cannot say which
    # of them a broker actually received. Each means DISPATCHED, matching the driver
    # alert columns above.
    dunning_nudge_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dunning_firm_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dunning_escalation_offer_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # M3-FR7's collection-partner handle. `escalate` took this argument and discarded it,
    # so a claim handed to a partner kept no way back to the file they opened.
    escalation_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    state: Mapped[ClaimState] = mapped_column(
        Enum(ClaimState, name="claim_state", schema=SCHEMA), default=ClaimState.open
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
