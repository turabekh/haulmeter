"""AI-CONTEXT: Public interface for F13 Feature Flags, Gates & Config Registry.

The ONLY import surface other packages may use to reach F13 (import-linter
enforced). Flags with kill-switch semantics gate module ACTIVATION (not scope);
validation gates are activation preconditions; the config registry holds runtime
tables. Consumed by every module.
"""

from .domain.models import ConfigDeclaration, ConfigEntry, FeatureFlag, ValidationGate
from .domain.service import (
    FlagNotFound,
    GateNotSatisfied,
    add_gate,
    can_activate,
    clear_kill,
    declared_configs,
    disable,
    enable,
    get_config,
    get_gate,
    get_scope,
    is_enabled,
    is_switched_off,
    kill,
    register_config,
    register_flag,
    satisfy_gate,
    set_config,
    unsatisfy_gate,
)

__all__ = [
    "ConfigDeclaration",
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
    "declared_configs",
    "get_config",
    "get_gate",
    "get_scope",
    "is_enabled",
    "is_switched_off",
    "kill",
    "register_config",
    "register_flag",
    "satisfy_gate",
    "set_config",
    "unsatisfy_gate",
]
