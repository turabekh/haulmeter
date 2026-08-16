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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f13_flags import public as flags

from . import diagnosis, prompts

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
    # AI-CONTEXT: registered at BOOT rather than lazily inside a request. `module_registry`
    # records that m11 did it lazily and the knob was absent from /admin until someone
    # happened to call an unrelated endpoint — a prompt nobody can find is not a registry.
    prompts.register_prompts(db)
    # the band thresholds and the calibration gate, tunable without a deploy —
    # they decide what a driver is told they are, so they are the owner's numbers
    diagnosis.register_config(db)


def is_enabled(db: Session) -> bool:
    return flags.is_enabled(db, FLAG_KEY)


# --- the module's half of the guest claim (E3 §E3.2 item 2) --------------------------


def claim_guest_sessions(db: Session, guest_token, account_id) -> int:
    """Re-point this guest's sessions at a real account. Returns how many moved.

    AI-CONTEXT: THE OTHER HALF OF THE CLAIM LIVES IN F1, and the split is the boundary
    rather than a preference. `core < foundation < modules`: F1 owns the principal's
    lifecycle and cannot know what a session is; m15 owns these rows and cannot mark a
    principal claimed. Both halves must run in ONE transaction — the caller's obligation,
    asserted by a test that rolls the pair back together.

    `guest_token` is deliberately NOT cleared. Quality law Q-10 says guest work is never
    lost silently, and keeping the token is what lets a support question — "where did my
    practice go?" — be answered from the rows instead of guessed at. The claim is recorded
    on the F1 principal; this column is the trail back to it.
    """
    from .models import Session as RoadsideSession

    sessions = list(
        db.scalars(
            select(RoadsideSession).where(RoadsideSession.guest_token == guest_token)
        )
    )
    for session in sessions:
        session.account_id = account_id
    db.flush()
    return len(sessions)
