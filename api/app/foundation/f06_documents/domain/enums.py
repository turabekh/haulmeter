import enum


class DocType(enum.Enum):
    rate_con = "rate_con"
    bol = "bol"
    pod = "pod"
    lumper_receipt = "lumper_receipt"
    # AI-CONTEXT: A1's capture checklist named five artifacts; three were already doc
    # types and these two were not. A checklist row with nowhere to capture it is a tick
    # that can never turn green — decoration facing the other way (see `has_bol`).
    seal = "seal"
    damage = "damage"
    cdl = "cdl"
    med_card = "med_card"
    insurance = "insurance"
    permit = "permit"
    settlement = "settlement"
    other = "other"


class ExtractionStatus(enum.Enum):
    pending = "pending"
    extracted = "extracted"
    failed = "failed"


class RetentionClass(enum.Enum):
    """AI-CONTEXT: how long an object's BYTES live. Owner-signed via D14 / E3 §E3.4.3.

    This is the only thing the retention sweep is allowed to select on. Not MIME type,
    not module, not a path prefix — an explicit column set at write time, so a credential
    can never be swept because someone later stored it with an audio content type or under
    a path that matched a pattern. The sweep's SELECT is the guard, and a guard that
    infers is a guard that will one day infer wrong about a driver's CDL.

    `permanent` is the default for everything F6 has ever held. `audio_30d` exists for one
    thing: raw driver audio in `m15.turn.audio_ref`. Cached officer, drill and sign audio
    is CONTENT and stays `permanent` — the distinction E3 §E3.4.3 draws is between a
    recording OF a driver and a recording we made for them.
    """

    permanent = "permanent"
    audio_30d = "audio_30d"
