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

from .models import ConfigEntry, FeatureFlag, ValidationGate


class GateNotSatisfied(Exception):
    pass


class FlagNotFound(Exception):
    pass


# --- Flags ---
def register_flag(
    db: Session, key: str, description: str | None = None, enabled: bool = False
) -> FeatureFlag:
    flag = db.get(FeatureFlag, key)
    if flag is None:
        flag = FeatureFlag(key=key, description=description, enabled=enabled)
        db.add(flag)
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
    return flag.kill_switch or not flag.enabled


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
    flag = db.get(FeatureFlag, flag_key)
    if flag is None:
        return False
    return flag.enabled and not flag.kill_switch


# --- Config registry ---
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
