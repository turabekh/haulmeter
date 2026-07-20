import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

from .enums import AccessorialKind, AccessorialState

SCHEMA = "m04"
ACCOUNT_FK = "f01.account.id"


class AccessorialClaim(Base):
    __tablename__ = "accessorial_claim"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(ACCOUNT_FK, ondelete="CASCADE"), index=True
    )
    load_ref: Mapped[uuid.UUID] = mapped_column(index=True)
    stop_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    counterparty_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    kind: Mapped[AccessorialKind] = mapped_column(
        Enum(AccessorialKind, name="accessorial_kind", schema=SCHEMA)
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    document_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)  # lumper receipt (F6)
    receivable_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    state: Mapped[AccessorialState] = mapped_column(
        Enum(AccessorialState, name="accessorial_state", schema=SCHEMA),
        default=AccessorialState.draft,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
