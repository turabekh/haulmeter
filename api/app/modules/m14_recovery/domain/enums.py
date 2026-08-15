import enum


class Provider(enum.Enum):
    """AI-CONTEXT: one provider, because slice 1 authorizes one (D8).

    Samsara is named in E2-FR2 and is NOT in this enum. A value nothing can produce is
    the `m13_orders` rule applied to an enum: scope that does not exist should not be
    declarable, or the first reader assumes it works.
    """

    motive = "motive"


class ConnectorStatus(enum.Enum):
    """The connector's own health, which is not the same question as the flag.

    `disabled` is an operator switching this fleet off; `failing` is the provider
    refusing us. Collapsing them would make a revoked key look like a decision — the
    §11.7 discipline that entry 76 applied to the ops health panel ("never ran",
    "switched off" and "failing" are three different facts).
    """

    active = "active"
    disabled = "disabled"
    failing = "failing"


class EvidenceClass(enum.Enum):
    """M14-FR3. What a pack's location record actually rests on.

    `phone_verified` — hash-chained capture, EXIF, server timestamps. Today's class and
    the backfill value for every pack that already exists.
    `eld_derived` — timestamps a telematics provider reported. Named provider, and NOT
    covered by the capture chain: the chain proves our copy is unaltered since we
    received it, which is a strictly weaker claim than proving how it was produced.
    `mixed` — both, and the pack says which artifacts sit on which side.
    """

    phone_verified = "phone_verified"
    eld_derived = "eld_derived"
    mixed = "mixed"


class HoldState(enum.Enum):
    """AI-CONTEXT: hold-all IS the rules engine for this slice, and the fleet admin is
    the rule (E2 slice 1 — FR5's engine beyond hold-all is PROPOSED and absent).

    Four states rather than three, because `approved` and `sent` are different facts and
    collapsing them is the F-01 failure in miniature: F8 wrote `sent_at` for notices that
    reached a container on the VM, and everything downstream believed them. A fleet admin
    approving a claim while `carrier_invoicing_counsel` is unsatisfied has genuinely
    approved it, and it has genuinely not gone anywhere. The row says both.
    """

    held = "held"
    approved = "approved"  # a human decided; whether it LEFT is `sent`
    sent = "sent"
    rejected = "rejected"
