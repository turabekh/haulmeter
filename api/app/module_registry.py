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
from app.modules.m14_recovery import public as m14

# in build order (PRD §6), which is also dependency order — a listing that reads like
# the law it implements is one a reviewer can check against it
MODULES = (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12, m13, m14)


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

    AI-CONTEXT: this writes NO operator state, and that is audit F-02's fix (§23 entry
    133). It declares what each module ships as — `default_on`, refreshed every boot —
    and never touches `enabled`, which belongs to `enable()`/`disable()` alone and is
    NULL until a human decides.

    The 29 July 2026 owner decision still holds and is unchanged in effect: the twelve
    capabilities that have been serving drivers come up on, because registering them off
    would switch the product off on deploy, M3 detention included. What changed is that
    they come up on because they DECLARE it, so `enable()` keeps its monopoly on writing
    operator state and validation gates govern every deliberate activation.
    """
    from app.foundation.f01_identity import public as identity
    from app.foundation.f03_location import public as location

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
    # AI-CONTEXT: same reasoning, one component over (audit F-09). The ping-retention
    # window is declared at boot so it is in /admin/config before an operator needs it,
    # rather than appearing only once somebody has already set it.
    location.register_location_retention(db)
    _register_ai_budgets(db)

    registered = []
    for module in MODULES:
        module.register_module(db)
        registered.append(module.FLAG_KEY)
    db.flush()
    # AI-CONTEXT: audit F-02 — the loop that used to live here is GONE.
    #
    # It read `if key in known_before: continue` and then `flag.enabled = True`, which is
    # how twelve module flags came up on with their validation gates unread: `enable()` is
    # the only function in F13 that checks a gate, and assignment does not go through it.
    #
    # Each module DECLARES `default_on` in its own `register_module` now, beside the
    # capability it describes, and that declaration carries a fresh box exactly as the
    # assignment did. Two things improve by moving it there. The 29 July decision
    # ("preserve today's behaviour; the point is that a kill switch EXISTS, not that
    # everything stops") is now written where a reader of the module can see it, instead
    # of being a fact about a loop in the registry. And the NEXT module's author has to
    # choose — v2.0 §3's `a07_parking_ahead` is specified with an inventory gate precisely
    # so it does not ship into an empty search, and under the old loop that gate would
    # have done nothing.
    #
    # `known_before` is no longer needed: nothing here writes operator state at all, so
    # there is nothing for a restart to overrule. `enabled` stays NULL until a human
    # decides, and `register_flag` refuses to touch it.
    return registered
