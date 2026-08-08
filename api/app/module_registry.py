"""AI-CONTEXT: every module's flag, registered in one place (§23 entry 105).

PRD §6 is the governing rule: each module is "built end-to-end **behind its own feature
flag** in the platform's flag registry… Flags exist for **operational safety and
controlled activation**." Audited on 29 July 2026, that was true of exactly one module:

    modules declaring FLAG_KEY ......... 13 of 13
    flags registered in the database ...  3 (m01_map, m11_voice, m13_vendor)
    routers checking their flag ........  1 (m13_vendor)
    calling register_module at startup .  0 (m11 did it lazily, inside a request)

So M2–M10 and M12 were reachable with no gate, and there was **no kill switch**: if M3's
claim logic started producing wrong money on the deployed box, the only remedy was a
redeploy. §23 entries 92 and 93 both happened without one.

`is_enabled` returns FALSE for a flag that was never registered, so the order matters —
registering has to come first, or adding the gates would switch the product off.

Called from the app lifespan AND from the test fixture, because tests build their schema
with `create_all` rather than migrations and would otherwise have no flags at all: every
gated route would 404 for the whole suite, which would read as "the gates work".
"""

from sqlalchemy.orm import Session

from app.modules.m01_map import public as m1
from app.modules.m02_facility_intel import public as m2
from app.modules.m03_detention import public as m3
from app.modules.m04_accessorial import public as m4
from app.modules.m05_protection import public as m5
from app.modules.m06_parking import public as m6
from app.modules.m07_fuel import public as m7
from app.modules.m08_intelligence import public as m8
from app.modules.m09_money import public as m9
from app.modules.m10_community import public as m10
from app.modules.m11_voice import public as m11
from app.modules.m12_fleet import public as m12
from app.modules.m13_vendor import public as m13

# in build order (PRD §6), which is also dependency order — a listing that reads like
# the law it implements is one a reviewer can check against it
MODULES = (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12, m13)


def _register_ai_budgets(db: Session) -> None:
    """Every module gets an F9 spend cap, at boot, before it can spend anything.

    AI-CONTEXT: audit F-17 — `_check_budget` returned silently for a module with no
    `ModuleBudget` row, and `set_module_budget` had no caller outside the tests. So F9's
    cost control had never governed a single call: a well-designed guard, tested in
    isolation, with nothing in the product wired to switch it on. Structurally the same
    finding as F-02, which is why the audit named it a pattern rather than a bug.

    Seeded for ALL modules rather than only the four that call F9 today (m02, m04, m09,
    m11). A per-module opt-in is a list someone must remember to extend, and the failure
    mode of forgetting is silent unlimited spend — the exact shape being fixed. The
    invariant is simply "a module has a budget", and `test_module_flags` asserts it.

    Existing rows are LEFT ALONE. The number is an operator's decision and a restart must
    never overrule it, which is the same rule `register_all` applies to flag state below.
    """
    from app.foundation.f09_ai_gateway import public as ai
    from app.foundation.f13_flags import public as flags

    flags.register_config(
        db,
        ai.CONFIG_MONTHLY_BUDGET,
        ai.DEFAULT_MONTHLY_BUDGET_MICROS,
        description=(
            "Default per-module AI spend cap, micros of USD per calendar month "
            "(25000000 = $25). Applies to modules seeded after this is changed; "
            "existing per-module rows are edited individually."
        ),
        scope="ai",
    )
    default = int(flags.get_config(db, ai.CONFIG_MONTHLY_BUDGET, ai.DEFAULT_MONTHLY_BUDGET_MICROS))
    for module in MODULES:
        if db.get(ai.ModuleBudget, module.MODULE) is None:
            ai.set_module_budget(db, module.MODULE, default)
    db.flush()


def register_all(db: Session) -> list[str]:
    """Idempotent. Returns the flag keys that now exist, so a caller can assert on the
    result rather than trusting that a loop ran.

    AI-CONTEXT: a flag REGISTERED FOR THE FIRST TIME comes up ENABLED, and only then.
    `register_flag` defaults to off, which is the right default for a flag somebody is
    about to switch on deliberately — but these twelve are not new capabilities, they
    are capabilities that have been serving drivers ungated for months. Registering
    them off would have switched the product off on deploy, including M3 detention.
    Owner decision, 29 July 2026: preserve today's behaviour; the point of the exercise
    is that a kill switch EXISTS, not that everything stops.

    A flag that already exists is left exactly as it is — enabled or disabled — because
    that state is an owner decision and a deploy must never overrule it. That is why
    this compares before and after rather than simply setting `enabled=True`.
    """
    from app.foundation.f01_identity import public as identity
    from app.foundation.f13_flags import public as flags

    # AI-CONTEXT: F1's registration runs HERE, at boot, and it did not before.
    #
    # `register_authority_verification` was called lazily from inside the
    # /auth/verify-authority handler — which is the exact pattern this file's own header
    # records as the m11 defect: "m11 did it lazily, inside a request". It registers the
    # verification flag and, since F-07, the three login-throttle config declarations.
    # Left where it was, those knobs would be absent from /admin/config until somebody
    # happened to call an unrelated endpoint, which is session 112's finding reappearing:
    # a tunable nobody can find is not configuration. Foundation components are not
    # flag-gated like modules, so it takes no part in the enable-on-first-registration
    # rule below.
    identity.register_authority_verification(db)
    _register_ai_budgets(db)

    known_before = {
        key for (key,) in db.query(flags.FeatureFlag.key).all()  # noqa: S608 - ORM
    }
    registered = []
    for module in MODULES:
        module.register_module(db)
        registered.append(module.FLAG_KEY)
    db.flush()
    for key in registered:
        if key in known_before:
            continue  # already an owner's decision — never overruled by a restart
        flag = db.get(flags.FeatureFlag, key)
        if flag is not None:
            flag.enabled = True
    db.flush()
    return registered
