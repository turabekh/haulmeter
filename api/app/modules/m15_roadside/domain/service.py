"""AI-CONTEXT: M15 Roadside Readiness — module core (PRD Extension E3, owner decision D14).

D14 is signed at **scope (b): Session A only**. Sessions B and C are authorized against
that entry by their own kickoffs, so this file grows in three deliberate steps and a later
session should not read its thinness as an omission.

What this module may NEVER acquire without a new owner decision, recorded here because the
absence is the design and an absence leaves no other trace:

· **No voiceprint, no biometric matching, ever.** There is no column for one, and no
  D-question in E3 §E3.7 could add one (§E3.1.4). A later session asked to "identify the
  speaker" is being asked for something this module refused by construction.
· **No payment code path is reachable.** Phase A carries zero, on the M13 Phase A
  precedent. `m15_billing` does not exist and is gated on D15, which is OPEN.
  `entitlement.source` will carry a `stripe` label when the schema lands — a label is not
  a code path, and nothing may make it one here.
· **No assessment mode.** `m15_assessment` does not exist and is gated on D19's three
  criteria. M15 ships TRAINING records only, and E3's quality law Q-7 makes the difference
  load-bearing: *assessment*, *certificate*, *FMCSA approved* and *pass* are forbidden
  strings in anything this module renders.
"""

from sqlalchemy.orm import Session

from app.foundation.f13_flags import public as flags

# AI-CONTEXT: `m15_roadside` is the master flag. Turning it ON opens the free Roadside
# Check platform-wide; the sponsored surfaces additionally require entitlements, which is
# what scopes the gate window to pilot orgs without inventing a per-org flag (§E3.1.8).
FLAG_KEY = "m15_roadside"

# the key F9 meters AI spend against. Being in `module_registry.MODULES` is what seeds the
# budget row, so m15 is capped from its first boot rather than from its first bill — the
# F-17 invariant ("no uncapped state exists") covers this module from its first row.
MODULE = "m15"


def register_module(db: Session) -> None:
    """AI-CONTEXT: NO `default_on`, and that is the F-02 discipline rather than caution.

    A capability that has never shipped declares nothing and lets the operator's decision
    govern. `register_flag` has no `enabled` parameter at all since audit F-02 — a flag
    born enabled never passes through `enable()`, which is the only function that reads a
    validation gate, and that is how six gates across M3, M6 and M7 came to have never
    been read while their modules ran.

    No validation gates are registered here. E3 §E3.1.9 states the conditions for turning
    this flag on — seven locales passing among them — but §E3.1.8 does not name them as
    F13 gates, and inventing operator state a governing document did not ask for is the
    thing this codebase keeps paying for. The question is recorded for the owner in the
    Session-A handoff instead.
    """
    flags.register_flag(db, FLAG_KEY, description="M15 Roadside Readiness (ELP training)")


def is_enabled(db: Session) -> bool:
    return flags.is_enabled(db, FLAG_KEY)
