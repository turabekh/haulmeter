"""AI-CONTEXT: Public interface for F13 Feature Flags, Gates & Config Registry.

The ONLY import surface other packages may use to reach F13 (import-linter
enforced). Flags with kill-switch semantics gate module ACTIVATION (not scope);
validation gates are activation preconditions; the config registry holds runtime
tables. Consumed by every module.
"""
from .domain.models import ConfigEntry, FeatureFlag, ValidationGate
from .domain.service import (
    FlagNotFound,
    GateNotSatisfied,
    add_gate,
    can_activate,
    clear_kill,
    disable,
    enable,
    get_config,
    get_scope,
    is_enabled,
    kill,
    register_flag,
    satisfy_gate,
    set_config,
)

__all__ = [
    "ConfigEntry",
    "FeatureFlag",
    "ValidationGate",
    "FlagNotFound",
    "GateNotSatisfied",
    "add_gate",
    "can_activate",
    "clear_kill",
    "disable",
    "enable",
    "get_config",
    "get_scope",
    "is_enabled",
    "kill",
    "register_flag",
    "satisfy_gate",
    "set_config",
]
