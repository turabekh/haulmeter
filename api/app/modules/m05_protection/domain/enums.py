import enum


class CapturePhase(enum.Enum):
    pickup = "pickup"
    delivery = "delivery"


# design/PRD M5-FR2: guided cargo-condition photo sequence
CONDITION_SEQUENCE = ["trailer_exterior", "seals", "load_blocking", "reefer_setpoint"]

# doc types surfaced in inspection mode (M5-FR3)
INSPECTION_DOC_TYPES = ["cdl", "med_card", "insurance", "permit"]


class StopPacketState(enum.Enum):
    """AI-CONTEXT: A1 requirement 5 — "the driver reviews before it sends. Nothing
    leaves silently. A packet the driver did not see is a document they cannot vouch
    for." The gap between drafted and sent is a person.

    `discarded` is that person saying no, and it had no way to (owner request,
    2026-08-11). A review with only one exit is not a review: the queue offered Send and
    nothing else, so a packet a driver did not want stayed on the Load tab forever and
    the only way to clear it was to send a document they had decided not to send.

    IT DESTROYS NOTHING. A packet is a pointer to a stop; the BOL, the photos and the
    evidence chain live in F4/M5 and are untouched, still exported from Past loads. This
    state means "not going to a dispatcher", never "gone".

    IT IS FINAL, by construction rather than by a rule anyone has to remember.
    `stop_ref` is uniquely constrained and `draft_stop_packet` is get-or-create, so a
    later EXIT at the same dock returns THIS row rather than drafting a second one — and
    the queue reads `state == draft`, so it does not come back. A discard that could be
    undone by driving through a geofence again would not be a decision.
    """

    draft = "draft"
    sent = "sent"
    discarded = "discarded"
