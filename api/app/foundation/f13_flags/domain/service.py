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


def add_gate(db: Session, flag_key: str, name: str, note: str | None = None) -> ValidationGate:
    if db.get(FeatureFlag, flag_key) is None:
        raise FlagNotFound(flag_key)
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
