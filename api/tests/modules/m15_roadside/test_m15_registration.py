"""AI-CONTEXT: M15 exists as a module, and it ships OFF declaring nothing.

What these hold is small on purpose — Session A's first commit is a skeleton and a
boundary, so the honest thing to assert is the skeleton and the boundary, not behaviour
that has not been written. Two of the four are about an ABSENCE, which is the kind of
claim that rots silently: a flag that quietly gained a `default_on`, and a budget row that
was never seeded, both look like nothing at all until a capability switches itself on at a
deploy or bills without a cap.

The import boundary itself is asserted by `importlinter.ini`'s `m15-does-not-import-m14`
contract rather than from here, and that contract was sabotage-checked when it landed —
an import of `m14_recovery.public` from m15 was added and watched to break it, because a
forbidden-contract typo that never fires reads exactly like a boundary that holds.
"""

from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f13_flags import public as flags
from app.modules.m15_roadside import public as m15


def test_flag_registers_and_declares_nothing(db):
    """F-02 discipline: registration must not write operator state.

    `enabled` is the operator's column and stays NULL until a human decides; `default_on`
    is the code's own declaration and must be False, because a capability that has never
    shipped declares nothing. A flag born enabled never passes through `enable()`, which
    is the only function that reads a validation gate.
    """
    m15.register_module(db)

    flag = db.get(flags.FeatureFlag, m15.FLAG_KEY)
    assert flag is not None, "m15_roadside must exist as a row an operator can find"
    assert flag.enabled is None, "registration must never write operator state"
    assert flag.default_on is False, "a capability that has never shipped declares nothing"


def test_module_reads_as_off_before_anyone_decides(db):
    m15.register_module(db)
    assert m15.is_enabled(db) is False


def test_registered_in_the_module_loop(db):
    """Being in `MODULES` is what seeds the AI budget, so absence is not cosmetic."""
    from app import module_registry

    assert m15 in module_registry.MODULES


def test_ai_spend_is_capped_from_the_first_boot(db):
    """The F-17 invariant — no uncapped state exists — covers m15 from its first row.

    M15 is the module that will meter audio minutes, so an unseeded budget here is not a
    theoretical gap: it is a module that transcribes and synthesizes with no ceiling.
    """
    from app import module_registry

    module_registry.register_all(db)
    assert db.get(ai.ModuleBudget, m15.MODULE) is not None


def test_the_two_gated_flags_do_not_exist(db):
    """D15 and D19 are OPEN, and nothing may build toward them.

    `m15_billing` is gated on the §9 amendment; `m15_assessment` on D19's three criteria.
    Neither flag may be registered by any code path this session added — an existing row
    is what would let a later session switch one on believing it was authorized.
    """
    from app import module_registry

    module_registry.register_all(db)
    assert db.get(flags.FeatureFlag, "m15_billing") is None
    assert db.get(flags.FeatureFlag, "m15_assessment") is None
