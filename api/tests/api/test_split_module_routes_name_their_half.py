"""AI-CONTEXT: a rule that lived only in a docstring, made into a check (§23 entry 224).

`require_any_module` gates the M13 router on "is ANY half live" — food OR service centres
— deliberately, so that switching food off "would not take the repair shops with it"
(A6). Its docstring then states the obligation that creates:

    "this gate is never sufficient on its own, and every route behind it names its own
     half."

Nothing enforced that. `PUT /vendors/alerts/opt-in` did not name its half, and the gap was
invisible because BOTH halves happen to be off in production today — the router 404s, so
the missing guard looks like a working refusal. The day A6 turns service centres on, every
unguarded route wakes up with it.

This reads the router's own source and fails if a route is added without a guard. The
exemptions are named, with reasons, and the test asserts the list does not grow: a silent
addition is exactly the failure it exists to prevent.
"""

import ast
import pathlib

ROUTER_SOURCE = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "m13_vendor.py"

# calling any of these is "naming your half"
HALF_GUARDS = {"_require_food", "_require_service", "_require_half", "_require_type",
               "_require_reportable"}

# AI-CONTEXT: `_require_active` is deliberately NOT in that set. It asks `m13.is_active`,
# which is the same weak "is any half live" question the ROUTER already asked — so a route
# that calls it has satisfied the gate twice and named its half zero times.

EXEMPT = {
    # A driver must always be able to STOP receiving something, even from a half that is
    # being wound down. Gating a withdrawal would trap them in alerts they cannot switch
    # off — and `follow`/`unfollow` are asymmetric on purpose: you cannot START following
    # a dead half, and you can always stop.
    "mute_vendor": "withdrawal — always allowed",
    "unfollow_vendor": "withdrawal — always allowed",
    # KNOWN GAP, filed as N-18 rather than waved through. It calls `_require_active`, so
    # with food off and service centres on it can still answer with food promotions.
    # Listed here so the rule holds for every new route while this one stays visible.
    "facility_promotions": "known gap — N-18",
}


def _routes():
    tree = ast.parse(ROUTER_SOURCE.read_text())
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        decorated = any(
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and isinstance(d.func.value, ast.Name)
            and d.func.value.id == "router"
            for d in node.decorator_list
        )
        if decorated:
            called = {
                n.func.id
                for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            }
            yield node.name, called


def test_every_route_behind_the_split_router_names_its_own_half():
    unguarded = [
        name
        for name, called in _routes()
        if not (called & HALF_GUARDS) and name not in EXEMPT
    ]
    assert not unguarded, (
        "these routes sit behind `require_any_module` and never name their half, so they "
        f"go live the moment EITHER half does: {unguarded}"
    )


def test_the_exemption_list_does_not_grow_quietly():
    """The rule is only worth as much as the list of things excused from it."""
    assert set(EXEMPT) == {"mute_vendor", "unfollow_vendor", "facility_promotions"}


def test_the_router_really_is_gated_on_any_half():
    """If this router stops being a split-module router, the rule above stops applying —
    and a test that keeps passing after its premise is gone is worse than no test."""
    source = ROUTER_SOURCE.read_text()
    assert "require_any_module(m13.FLAG_KEY, m13.SERVICE_CENTER_FLAG_KEY)" in source


def test_the_food_opt_in_is_covered_now():
    """The route that prompted the rule, asserted by name so a revert is loud."""
    called = dict(_routes())["set_alert_opt_in"]
    assert called & HALF_GUARDS
