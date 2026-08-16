"""AI-CONTEXT: M15's closed vocabularies (E3 §E3.1.4).

What is an enum here and what is deliberately a string is itself a decision. A closed
vocabulary in Postgres is a claim that the set is known and complete; where E3 names the
members, they are an enum, and where it does not, a string column carries the value until
an owner names them. Inventing a vocabulary and freezing it into a type is how a later
session inherits a set nobody chose — and `band` in particular is a product judgment about
what we tell a driver they are, not a schema detail. Those open ones are recorded as owner
questions in the Session-A handoff rather than guessed at here.
"""

import enum


class Difficulty(enum.Enum):
    """E3 §E3.1.3 — deliberately thin at Phase A: two levels, and no third invented."""

    clear = "clear"
    natural = "natural"


class ContentStatus(enum.Enum):
    """The publish path, and quality law Q-6 is enforced on the transitions, not here.

    `released` requires human review plus a version bump; F9-drafted text has no path to a
    driver. The enum can only say which states exist — the service layer is where a draft
    is prevented from reaching a driver, and the publish-path test is what proves it.
    """

    draft = "draft"
    reviewed = "reviewed"
    released = "released"


class SessionMode(enum.Enum):
    """`practice` is load-bearing for quality law Q-3, not a convenience label.

    Practice sessions are structurally invisible to the org-facing query path — not
    filtered out by a caller who remembers to, but unreachable by the function an org
    context is allowed to call.
    """

    check = "check"
    drill = "drill"
    reassessment = "reassessment"
    practice = "practice"


class Speaker(enum.Enum):
    officer = "officer"
    driver = "driver"


class TurnReviewStatus(enum.Enum):
    """Quality law Q-2: uncertain ASR never penalizes.

    `review_needed` is what a below-threshold confidence produces, and such a turn is
    excluded from bands entirely rather than scored low. The distinction between "we heard
    nothing usable" and "we heard something wrong" is the whole point — a driver whose
    accent defeated the recogniser has not failed anything.
    """

    not_needed = "not_needed"
    review_needed = "review_needed"
    reviewed = "reviewed"


class EntitlementKind(enum.Enum):
    program = "program"
    seat = "seat"


class EntitlementSource(enum.Enum):
    """AI-CONTEXT: `stripe` is a LABEL, and Phase A has no code path that writes it.

    D15 is OPEN and `m15_billing` does not exist. E3 §E3.1.4 names this member, so the
    schema carries it verbatim; the Phase-A discipline is that no payment code is
    *reachable*, and an enum member reaches nothing. A later session must not read this
    value's existence as authorization to build toward it — decision entry 176 says so on
    the record.
    """

    admin = "admin"
    stripe = "stripe"
