"""AI-CONTEXT: the rate confirmation, parsed — F5's PRIMARY way to create a load.

PRD §108 lists three ways a Load is created and calls this one primary:
"rate-confirmation upload parsed by the AI Gateway (primary), manual quick-entry, or
fleet/TMS push". PRD §7.16(b) puts "a test driver with a parsed rate con" in the
Foundation DoD.

Every piece existed and none of them were connected. F6 has stored the `rate_con` type
since it was written, F9 does structured `document_parse` (M4 and M9 both use it), and
`create_load_from_parsed_terms` has taken a parsed dict from the day it was written —
but the only place the chain was ever assembled was inside
`tests/e2e/test_common_ground_e2e.py`. The Load tab therefore offered a four-field
manual form in the empty state where §10.2 specifies "Add a load" by rate-con photo.

This module is the production path, and it stops at a DRAFT. It never creates the
load. M4-FR4 specifies "accessorial terms extraction from rate cons (F5/F9) with a
driver-confirm step", and the confirm step is the load-bearing part: a machine read of
a photographed contract is a proposal, and the driver is the only one who can see both
the paper and the screen.
"""

from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry
from app.foundation.f09_ai_gateway import public as ai

RATE_CON_PROMPT = "rate_con_parse"

# What the parse is REQUIRED to return for the draft to be worth showing. Deliberately
# short: a rate con that yields nothing but a detention rate is still worth confirming,
# and demanding more would send a driver back to typing everything by hand.
REQUIRED_KEYS = ["detention_rate_cents_per_hour"]

# The terms M4-FR4 warns about when a rate con is SILENT on them. "Silent on detention"
# is not the same as "no detention" — it means the contract does not say, which is a
# fact about the paper the driver should learn before accepting the load, not after
# waiting four hours at a dock.
WARNABLE_TERMS = {
    "detention_rate_cents_per_hour": "detention",
    "free_time_minutes": "free_time",
    "tonu": "tonu",
}

PROMPT_TEMPLATE = (
    "You are reading a freight rate confirmation. Extract only what the document "
    "actually states. Return a single JSON object with these keys: "
    "reference_number (string or null), broker_name (string or null), "
    "rate_cents (integer total linehaul in cents, or null), "
    "detention_rate_cents_per_hour (integer cents per hour, or null), "
    "free_time_minutes (integer minutes of free time before detention accrues, or null), "
    "receiver_name (string or null), receiver_address (string or null), "
    "appointment (ISO 8601 datetime string or null), "
    "accessorial_terms (object mapping term name to the contract's wording, may be empty). "
    "Use null for anything the document does not state. Never infer a market-standard "
    "value for a term the document is silent on. The rate confirmation is attached. {doc}"
)

# The terms that make a parse worth showing as a parse. A model handed something it
# cannot read answers with a full object of nulls, and `parse_structured` accepts it
# because its required-keys check tests for the KEY, not for a value — so without this
# the confirm screen would print "Read from your rate con" over an empty form, which
# is the product asserting it did something it did not.
READABLE_KEYS = ["detention_rate_cents_per_hour", "free_time_minutes", "rate_cents"]


def has_terms(parsed: dict | None) -> bool:
    return bool(parsed) and any(parsed.get(k) is not None for k in READABLE_KEYS)


def register_rate_con_prompt(db: Session) -> None:
    """Idempotent, and registered under the same key the Foundation e2e already uses,
    so the assembled chain and the production path cannot drift apart."""
    if ai.get_active_prompt(db, RATE_CON_PROMPT) is None:
        ai.register_prompt(db, RATE_CON_PROMPT, ai.AiTask.document_parse, PROMPT_TEMPLATE)


def parse_rate_con(
    db: Session,
    provider,
    doc_ref: str,
    account_id=None,
    document_b64: str | None = None,
    media_type: str | None = None,
) -> dict:
    """Run the document through F9's structured-output path.

    Raises `ai.StructuredOutputError` when the model returns nothing usable and
    `ai.PromptNotFound` when the prompt was never registered — both surface to the
    driver as "we could not read this one, enter it yourself" rather than as a load
    built on invented terms. A rate con is a CONTRACT; a plausible guess about its
    detention rate is worse than no guess at all, because the driver would find out
    which it was only when the claim was refused.
    """
    register_rate_con_prompt(db)
    # the DOCUMENT travels, not a description of it. The first version of this passed
    # `document.content_hash` — copied from the Foundation e2e, where a fake provider
    # made it irrelevant — so the live model was handed a SHA-256 string and answered,
    # correctly, that it could read nothing.
    context = {"doc": doc_ref}
    if document_b64 and media_type:
        context["document_b64"] = document_b64
        context["document_media_type"] = media_type
    return ai.parse_structured(
        db,
        provider,
        "f05",
        RATE_CON_PROMPT,
        context,
        required_keys=REQUIRED_KEYS,
        account_id=account_id,
    )


def silent_terms(parsed: dict) -> list[str]:
    """Which of the warnable terms this rate con does not state (M4-FR4's
    "pre-acceptance warning"). A missing key and an explicit null mean the same thing:
    the document does not say."""
    gaps = []
    accessorials = parsed.get("accessorial_terms") or {}
    for key, label in WARNABLE_TERMS.items():
        if key in accessorials or parsed.get(key) is not None:
            continue
        gaps.append(label)
    return gaps


def facility_candidates(db: Session, parsed: dict, limit: int = 3) -> list[dict]:
    """What the parsed receiver might already be in the registry.

    Matched rather than created, because `POST /load` creating a facility
    unconditionally is how the registry accumulates a duplicate row for every load a
    driver files — and those duplicates are what M2's dwell history aggregates over.
    Name-only search: a rate con carries an address string, and there is no geocoder in
    this stack to turn it into the coordinates `find_duplicate_candidates` needs.

    These are OFFERED and never pre-selected, and the reason is measured rather than
    assumed. Against "ACME Distribution Center", pg_trgm scores an unrelated
    "Dallas Distribution Center" at **0.645** and the correct-but-abbreviated
    "ACME Distribution Ctr" at **0.679** — the wrong answer and the right one are four
    hundredths apart, because the score is dominated by the words they share. No
    threshold separates them, so there is no honest default: the driver picks. A wrong
    match costs one tap to notice, and a wrong default costs a load attached to a dock
    they never visited, taking its dwell history with it.
    """
    name = (parsed.get("receiver_name") or "").strip()
    if not name:
        return []
    rows = facility_registry.search_by_name(db, name, limit=limit)
    return [
        {
            "facility_id": str(fac.id),
            "name": fac.name,
            "address": fac.address,
            "score": round(score, 2),
        }
        for fac, score in rows
    ]


def draft_from_rate_con(
    db: Session,
    provider,
    doc_ref: str,
    account_id=None,
    document_b64: str | None = None,
    media_type: str | None = None,
) -> dict:
    """The whole read, as one thing the confirm screen can render: what the parse says,
    what the rate con is silent about, and which known facility it might be.

    `readable` is the screen's right to say "read from your rate con", and it is false
    when nothing usable came back — a full object of nulls is not a read."""
    parsed = parse_rate_con(
        db,
        provider,
        doc_ref,
        account_id=account_id,
        document_b64=document_b64,
        media_type=media_type,
    )
    readable = has_terms(parsed)
    return {
        "parsed": parsed if readable else None,
        "readable": readable,
        "silent_on": silent_terms(parsed) if readable else [],
        "facility_candidates": facility_candidates(db, parsed) if readable else [],
    }
