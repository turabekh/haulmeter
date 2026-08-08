"""AI-CONTEXT: F13 Feature Flags, Validation Gates & Config Registry (PRD §7.13).

Flags are configuration with kill-switch semantics — the operational safety
mechanism for the single continuous build (flags gate ACTIVATION, not scope,
PRD §6). Validation gates are per-module activation preconditions (legal
sign-off, partner agreements, insurance bound); a flag cannot be enabled until
all its gates are satisfied, and a kill switch force-disables regardless. The
config registry holds runtime tables (detention defaults, geofence tuning,
points economy, fee percentages) that other components read instead of
hardcoding — the eventual home for the placeholder constants scattered in
F3/F8/F9/F10/F11.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ConfigDeclaration, ConfigEntry, FeatureFlag, ValidationGate


class GateNotSatisfied(Exception):
    pass


class FlagNotFound(Exception):
    pass


# --- Flags ---
def register_flag(
    db: Session, key: str, description: str | None = None, default_on: bool = False
) -> FeatureFlag:
    """AI-CONTEXT: the `enabled` parameter is GONE, and that is audit F-02's fix.

    It used to let a caller create a row already switched on, which is how six validation
    gates across M3, M6 and M7 came to have never been read: `enable()` is the only
    function here that checks them, and a flag born enabled never goes through it.

    `default_on` says the same thing honestly — "this capability ships on" is a fact about
    the code — and it REFRESHES on every boot for the same reason `description` does. What
    it cannot do is write `enabled`, which now belongs to the operator alone.
    """
    flag = db.get(FeatureFlag, key)
    if flag is None:
        flag = FeatureFlag(key=key, description=description, default_on=default_on)
        db.add(flag)
        db.flush()
        return flag
    # AI-CONTEXT: two INDEPENDENT refreshes, not an elif chain, and the difference was a
    # real bug caught by its own test. Written as `elif`, a flag whose default AND
    # description both changed refreshed only the default — which is exactly the m13 case
    # that motivated the description refresh in the first place (a half renamed at the
    # same time as its default changing). Both are facts about the shipped code, so both
    # refresh, always. `enabled` is neither and is never touched here.
    if flag.default_on != default_on:
        flag.default_on = default_on
        db.flush()
    if description is not None and flag.description != description:
        # AI-CONTEXT: the description REFRESHES; `enabled` never does.
        #
        # `register_config` has always done this for declarations — "a code default
        # that changed is what the console shows afterwards" — and flags did not, so a
        # description written once was frozen on every box that had already booted.
        # A6 is what surfaced it: `m13_vendor` became the FOOD half and every existing
        # box, production included, still called it "M13 Vendor Network", which is now
        # the name of both halves together. An operator reading that would switch off
        # what they believed was the whole vendor network and actually leave the
        # service centres running.
        #
        # A stale label on a switch is worse than none: it answers the question wrongly
        # and so stops anyone asking. `enabled` is deliberately untouched — that is the
        # operator's state, and a redeploy must never silently flip a flag back.
        flag.description = description
        db.flush()
    return flag


def _effective(flag: FeatureFlag) -> bool:
    """The one place the effective state of an EXISTING flag is decided (audit F-12).

    A kill switch beats everything — that is what a kill switch is for. Otherwise the
    operator's decision wins if they have made one, and the code's declaration carries it
    if they have not.
    """
    if flag.kill_switch:
        return False
    return flag.default_on if flag.enabled is None else flag.enabled


def running_ahead_of_gates(db: Session) -> list[tuple[str, list[str]]]:
    """Flags that are effectively ON while their own activation gates are unsatisfied.

    AI-CONTEXT: this is the honest half of audit F-02, and the reason the fix is not
    simply "make gates block the default".

    Three modules carry gates and all six were unsatisfied on the running box while all
    three flags read enabled: M3 detention (`legal_signoff`,
    `collection_partner_agreement`), M6 parking (`refund_policy`,
    `damage_liability_posture`), M7 fuel (`merchant_agreement`, `payment_partner`). Those
    are business preconditions, and satisfying a gate is an assertion that a legal review
    or a commercial agreement actually happened — which is not something a deploy may
    decide.

    Making the gates block the default would therefore have taken M3 dark on the next
    boot: the detention clock is the wedge, and stopping it is a far worse outcome than
    the state being unverified. The 29 July owner decision — preserve live behaviour —
    stands.

    So the gate does the one thing it can honestly do here: it SAYS SO. This is reported
    at boot and exposed on the admin console, which turns "the gate silently does nothing"
    into "M3, M6 and M7 are running ahead of their preconditions, and here they are". That
    is §11.7's rule — never assert what you do not know — pointed at the operator instead
    of the driver.

    Every DELIBERATE activation is still gated: `enable()` refuses, and it is now the only
    writer of `enabled` to True.
    """
    out: list[tuple[str, list[str]]] = []
    for flag in db.query(FeatureFlag).all():
        if not _effective(flag):
            continue
        unsatisfied = sorted(g.name for g in flag.gates if not g.satisfied)
        if unsatisfied:
            out.append((flag.key, unsatisfied))
    return sorted(out)


def clear_decision(db: Session, flag_key: str) -> FeatureFlag:
    """Hand a flag back to its code default by forgetting the operator's decision.

    Without this there is no way back: once `disable()` has written False, `enabled` is
    non-NULL forever and the declared default can never apply again. `enable()` would set
    it True, which is a different thing — an explicit decision to be on, gates checked.
    """
    flag = db.get(FeatureFlag, flag_key)
    if flag is None:
        raise FlagNotFound(flag_key)
    flag.enabled = None
    db.flush()
    return flag


def is_switched_off(db: Session, flag_key: str) -> bool:
    """AI-CONTEXT: the MODULE GATE's predicate, and deliberately not `is_enabled`
    (§23 entry 105).

    `is_enabled` answers "may this run?" and treats an unregistered flag as OFF, which
    is correct for a capability nobody has switched on yet. A module gate asks the
    opposite question — "has anyone switched this OFF?" — and the difference decides
    what happens when the registry itself fails.

    Registration runs at startup. If it ever fails, `is_enabled` would take the entire
    product dark: twelve modules answering 404 because a bootstrap query hiccuped. That
    is a self-inflicted outage of exactly the kind §23 entries 92, 93 and 100 kept
    finding. This predicate fails OPEN on absence and CLOSED on an explicit decision:
    a module is refused only when a flag row exists and says so.

    The kill switch a driver-facing product actually needs is "turn M3 off NOW", and
    that is a row that exists and says off. Nothing here weakens it.
    """
    flag = db.get(FeatureFlag, flag_key)
    if flag is None:
        return False  # never governed — behaves exactly as it did before gates existed
    return not _effective(flag)


def add_gate(db: Session, flag_key: str, name: str, note: str | None = None) -> ValidationGate:
    """AI-CONTEXT: idempotent, and it was not (§23 entry 105).

    Every module's `register_module` calls this for each of its activation gates, and
    registration now runs on EVERY application start — so a second boot hit
    `uq_validation_gate_flag_name` and the whole registry transaction rolled back,
    taking the flags with it. A registration routine that cannot be run twice is a
    landmine under any process that restarts.

    An existing gate is RETURNED UNCHANGED rather than reset. `satisfied` is an owner
    decision — a legal sign-off that has been granted must not be revoked by a deploy,
    which is precisely what re-creating the row would have done."""
    if db.get(FeatureFlag, flag_key) is None:
        raise FlagNotFound(flag_key)
    existing = db.scalar(
        select(ValidationGate).where(
            ValidationGate.flag_key == flag_key, ValidationGate.name == name
        )
    )
    if existing is not None:
        return existing
    gate = ValidationGate(flag_key=flag_key, name=name, note=note)
    db.add(gate)
    db.flush()
    return gate


def satisfy_gate(db: Session, gate: ValidationGate, note: str | None = None) -> ValidationGate:
    gate.satisfied = True
    gate.satisfied_at = datetime.now(UTC)
    if note is not None:
        gate.note = note
    db.flush()
    return gate


def unsatisfy_gate(db: Session, gate: ValidationGate, note: str | None = None) -> ValidationGate:
    """AI-CONTEXT: a gate can be withdrawn as well as met. An activation
    precondition that could only ever be ticked is a one-way ratchet — if a legal
    review lapses or an insurance policy expires, the gate must be able to go back,
    and `enable` will then refuse until it is met again."""
    gate.satisfied = False
    gate.satisfied_at = None
    if note is not None:
        gate.note = note
    db.flush()
    return gate


def get_gate(db: Session, flag_key: str, name: str) -> ValidationGate | None:
    return db.scalar(
        select(ValidationGate).where(
            ValidationGate.flag_key == flag_key, ValidationGate.name == name
        )
    )


def can_activate(db: Session, flag_key: str) -> bool:
    flag = db.get(FeatureFlag, flag_key)
    if flag is None:
        raise FlagNotFound(flag_key)
    return all(gate.satisfied for gate in flag.gates)


def enable(db: Session, flag_key: str) -> FeatureFlag:
    flag = db.get(FeatureFlag, flag_key)
    if flag is None:
        raise FlagNotFound(flag_key)
    unsatisfied = [g.name for g in flag.gates if not g.satisfied]
    if unsatisfied:
        raise GateNotSatisfied(f"{flag_key}: {unsatisfied}")
    flag.enabled = True
    db.flush()
    return flag


def disable(db: Session, flag_key: str) -> FeatureFlag:
    flag = db.get(FeatureFlag, flag_key)
    if flag is None:
        raise FlagNotFound(flag_key)
    flag.enabled = False
    db.flush()
    return flag


def kill(db: Session, flag_key: str) -> FeatureFlag:
    flag = db.get(FeatureFlag, flag_key)
    if flag is None:
        raise FlagNotFound(flag_key)
    flag.kill_switch = True
    db.flush()
    return flag


def clear_kill(db: Session, flag_key: str) -> FeatureFlag:
    flag = db.get(FeatureFlag, flag_key)
    if flag is None:
        raise FlagNotFound(flag_key)
    flag.kill_switch = False
    db.flush()
    return flag


def is_enabled(db: Session, flag_key: str) -> bool:
    """AI-CONTEXT: audit F-12 — this and `is_switched_off` are no longer two
    implementations of one question.

    They used to compute the effective state separately, and the audit's finding was that
    they "only agree because F-02 force-enables everything". Both now defer to
    `_effective`, so for a flag that EXISTS they cannot disagree — not by discipline, by
    construction.

    What still differs, deliberately, is the answer for a flag that does not exist at all,
    and both defaults remain the ones §23 entry 105 argued for:

      · here, absent means DOES NOT RUN — a capability nobody registered must not fire.
      · in `is_switched_off`, absent means NOT SWITCHED OFF — a registry hiccup must not
        take twelve modules dark and 404 the product.

    `test_module_flags` asserts both halves, including that they agree on every registered
    flag, so a future edit to one of them cannot quietly reintroduce the split.
    """
    flag = db.get(FeatureFlag, flag_key)
    if flag is None:
        return False
    return _effective(flag)


# --- Config registry ---
def register_config(db: Session, key: str, default, description: str | None = None,
                    scope: str = "global") -> "ConfigDeclaration":
    """Declare that a key is tunable, WITHOUT writing a value for it.

    Called from `register_module`, which runs on every boot — so it is idempotent, and a
    code default that changed is what the console shows afterwards. See the model's
    AI-CONTEXT for why this does not seed a ConfigEntry."""
    row = db.get(ConfigDeclaration, key)
    if row is None:
        row = ConfigDeclaration(
            key=key, scope=scope, default_value=default, description=description
        )
        db.add(row)
    else:
        row.default_value = default
        row.description = description
        row.scope = scope
    db.flush()
    return row


def declared_configs(db: Session, scope: str = "global") -> dict:
    """Everything tunable in this scope, whether or not anyone has tuned it — with the
    shipped default beside the set value, because an operator comparing what they
    changed against what shipped needs both."""
    out = {}
    for row in db.scalars(
        select(ConfigDeclaration).where(ConfigDeclaration.scope == scope).order_by(
            ConfigDeclaration.key
        )
    ):
        entry = db.get(ConfigEntry, row.key)
        out[row.key] = {
            "default": row.default_value,
            "description": row.description,
            "set": entry is not None,
            "value": entry.value if entry is not None else row.default_value,
        }
    return out


def set_config(db: Session, key: str, value, scope: str = "global") -> ConfigEntry:
    entry = db.get(ConfigEntry, key)
    if entry is None:
        entry = ConfigEntry(key=key, scope=scope, value=value)
        db.add(entry)
    else:
        entry.value = value
        entry.scope = scope
    db.flush()
    return entry


def get_config(db: Session, key: str, default=None):
    entry = db.get(ConfigEntry, key)
    return entry.value if entry is not None else default


def get_scope(db: Session, scope: str) -> dict:
    entries = db.scalars(select(ConfigEntry).where(ConfigEntry.scope == scope))
    return {entry.key: entry.value for entry in entries}
