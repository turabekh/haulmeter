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

def _nullable(kind: str) -> dict:
    # structured outputs support anyOf; a bare {"type": ["integer","null"]} union is
    # the shakier spelling, so every optional field is written this way
    return {"anyOf": [{"type": kind}, {"type": "null"}]}


# AI-CONTEXT: the schema is what makes the parse a guarantee rather than a request.
#
# `additionalProperties: false` is required on every object by structured outputs, and
# that is why `accessorial_terms` is a LIST of {term, wording} rather than the open
# term->wording map it would naturally be: an open map is exactly what
# additionalProperties forbids. The list is normalised back to a map on the way out, so
# nothing downstream learns about the schema's constraint.
#
# Every field is `required` and nullable rather than optional, because "the contract
# does not say" is an answer this product needs to hear explicitly — an absent key and
# a null are indistinguishable to a reader, and only one of them is a statement.
RATE_CON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "reference_number",
        "broker_name",
        "rate_cents",
        "detention_rate_cents_per_hour",
        "free_time_minutes",
        "stops",
        "accessorial_terms",
    ],
    "properties": {
        "reference_number": _nullable("string"),
        "broker_name": _nullable("string"),
        "rate_cents": _nullable("integer"),
        "detention_rate_cents_per_hour": _nullable("integer"),
        "free_time_minutes": _nullable("integer"),
        # AI-CONTEXT: a rate con is a ROUTE, and this schema described one delivery
        # (§23 entry 68). A real contract's stops table carried a pickup at Harvest
        # Foods DC on 08/03 08:00-10:00 and a delivery in Columbus on 08/05 07:30; the
        # parse kept the second and threw the first away. So detention at the SHIPPER
        # could never be claimed — shippers detain drivers as often as receivers do —
        # and §10.2's next-stop preview could never render for an imported load,
        # because there was never a second stop to preview.
        "stops": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "stop_type",
                    "name",
                    "address",
                    "appointment_start",
                    "appointment_end",
                ],
                "properties": {
                    "stop_type": {"type": "string", "enum": ["pickup", "delivery"]},
                    "name": _nullable("string"),
                    "address": _nullable("string"),
                    # a window, not a moment: the pickup row read "08:00 - 10:00" and
                    # collapsing that to one time loses the half a driver is judged on
                    "appointment_start": _nullable("string"),
                    "appointment_end": _nullable("string"),
                },
            },
        },
        "accessorial_terms": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["term", "wording"],
                "properties": {"term": {"type": "string"}, "wording": {"type": "string"}},
            },
        },
    },
}

PROMPT_TEMPLATE = (
    "You are reading a freight rate confirmation. Extract only what the document "
    "actually states. Return a single JSON object with these keys: "
    "reference_number (string or null), broker_name (string or null), "
    "rate_cents (integer total linehaul in cents, or null), "
    "detention_rate_cents_per_hour (integer cents per hour, or null), "
    "free_time_minutes (integer minutes of free time before detention accrues, or null), "
    "stops (a list, IN THE ORDER THE DRIVER RUNS THEM, of "
    "{stop_type: \"pickup\" or \"delivery\", name, address, appointment_start, "
    "appointment_end} — one entry for EVERY row of the stops table, pickups included; "
    "appointment_start/appointment_end are ISO 8601 datetimes or null, and a stop "
    "given a window like \"08:00 - 10:00\" has both), "
    "accessorial_terms (a list of {term, wording} taken from the contract, may be empty). "
    "Use null for anything the document does not state. Never infer a market-standard "
    "value for a term the document is silent on. The rate confirmation is attached. {doc}"
)

# The terms that make a parse worth showing as a parse. A model handed something it
# cannot read answers with a full object of nulls, and `parse_structured` accepts it
# because its required-keys check tests for the KEY, not for a value — so without this
# the confirm screen would print "Read from your rate con" over an empty form, which
# is the product asserting it did something it did not.
READABLE_KEYS = ["detention_rate_cents_per_hour", "free_time_minutes", "rate_cents"]


def parsed_stops(parsed: dict | None) -> list[dict]:
    """The route the contract describes, in order, pickups included.

    Defensive about shape because a model can return null for an array it found
    nothing for, and `stops: null` and `stops: []` mean the same thing to a driver."""
    rows = (parsed or {}).get("stops") or []
    return [r for r in rows if isinstance(r, dict)]


def has_terms(parsed: dict | None) -> bool:
    # a route the driver can check is a read worth showing, even from a contract that
    # states no money terms at all
    return bool(parsed) and (
        any(parsed.get(k) is not None for k in READABLE_KEYS) or bool(parsed_stops(parsed))
    )


def facility_candidates(db: Session, parsed: dict, limit: int = 3) -> list[dict]:
    """Back-compat shim: the first stop's name, which is what "the receiver" meant when
    a parse only ever had one."""
    rows = parsed_stops(parsed)
    return facility_candidates_for(db, (rows[0].get("name") if rows else "") or "", limit)


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
    parsed = ai.parse_structured(
        db,
        provider,
        "f05",
        RATE_CON_PROMPT,
        context,
        required_keys=REQUIRED_KEYS,
        account_id=account_id,
        schema=RATE_CON_SCHEMA,
    )
    return {**parsed, "accessorial_terms": _terms_as_map(parsed.get("accessorial_terms"))}


def _terms_as_map(terms) -> dict:
    """The schema has to express accessorial terms as a list — structured outputs
    require `additionalProperties: false`, which is precisely what an open map is not.
    Callers keep the map they already expect."""
    if isinstance(terms, dict):
        return terms  # a schema-less provider (or a fixture) answered in map form
    return {
        t["term"]: t.get("wording")
        for t in terms or []
        if isinstance(t, dict) and t.get("term")
    }


def silent_terms(parsed: dict) -> list[str]:
    """Which of the warnable terms this rate con does not state (M4-FR4's
    "pre-acceptance warning"). A missing key and an explicit null mean the same thing:
    the document does not say."""
    gaps = []
    # AI-CONTEXT: matched case-INSENSITIVELY, and that is not tidiness.
    #
    # The model names terms the way the contract does — a live parse returned
    # {"TONU": "50% of linehaul if cancelled after arrival"} — and an exact-key lookup
    # for "tonu" missed it, so the screen told the driver the rate con was SILENT on
    # TONU while quoting the clause that states it. Warning about a term the contract
    # actually grants is worse than not warning at all: a driver who believes there is
    # no TONU clause does not claim TONU.
    accessorials = {
        str(k).strip().lower() for k in (parsed.get("accessorial_terms") or {})
    }
    for key, label in WARNABLE_TERMS.items():
        if label in accessorials or key in accessorials or parsed.get(key) is not None:
            continue
        gaps.append(label)
    return gaps


def facility_candidates_for(db: Session, name: str, limit: int = 3) -> list[dict]:
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
    name = (name or "").strip()
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
    # AI-CONTEXT: the parsed ADDRESS becomes a proposed location (§23 entry 67).
    #
    # `receiver_address` was extracted and dropped, and the import sheet filed every
    # dock at a hardcoded Dallas coordinate — so a Columbus receiver armed its geofence
    # 1,500 km away and ENTER could never fire for a real delivery. The geocoder
    # proposes; the driver disposes. Its own wording for the place travels with it so
    # the confirm screen can show what was matched rather than asserting it (§11.7).
    stops = []
    if readable:
        for index, row in enumerate(parsed_stops(parsed)):
            place = None
            found = facility_registry.geocode(row.get("address") or "", limit=1)
            if found:
                place = {"lat": found[0].lat, "lon": found[0].lon, "label": found[0].label}
            stops.append(
                {
                    "sequence": index,
                    "stop_type": row.get("stop_type") or "delivery",
                    "name": row.get("name"),
                    "address": row.get("address"),
                    "appointment_start": row.get("appointment_start"),
                    "appointment_end": row.get("appointment_end"),
                    "location": place,
                    "facility_candidates": facility_candidates_for(db, row.get("name") or ""),
                }
            )
    return {
        "parsed": parsed if readable else None,
        "readable": readable,
        "silent_on": silent_terms(parsed) if readable else [],
        # every stop carries its OWN candidates and its own geocode: a route is two
        # different docks, and offering the delivery's matches for a pickup would be
        # the pre-ticking defect (entry 65) wearing a different hat
        "stops": stops,
    }
