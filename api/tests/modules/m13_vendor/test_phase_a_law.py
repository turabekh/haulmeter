"""AI-CONTEXT: the Phase-A law (PRD extension §E1.1) as an executable test.

M13 publishes information and processes ZERO food/service payments. The platform
sells nothing and takes no cut — that is what keeps it legally a directory while
informal vendors formalize, and it is a legal posture, not a preference. So it is
enforced mechanically here rather than trusted to review: if someone wires an order
or a charge into this module, this file goes red.

Phase B (pre-order/prepay) activates behind a SEPARATE flag that does not exist yet.
"""

from pathlib import Path

from app.foundation.f13_flags import public as flags
from app.modules.m13_vendor import public as m13

MODULE_DIR = Path(m13.__file__).parent


def _module_source() -> str:
    return "\n".join(p.read_text() for p in sorted(MODULE_DIR.rglob("*.py")))


def test_m13_never_imports_the_ledger():
    # F7 is the money layer. M13 must have no route to it, directly or via an alias.
    source = _module_source()
    assert "f07_ledger" not in source
    assert "issue_points" not in source


def test_m13_declares_no_payment_or_order_surface():
    source = _module_source().lower()
    # `price_cents` is allowed and deliberate — it is DISPLAYED, never charged
    for forbidden in (
        "stripe",
        "payment_intent",
        "def charge",
        "class order",
        "payout",
        "take_rate",
        "settle(",
    ):
        assert forbidden not in source, f"Phase A forbids a payment path: {forbidden}"


# every table M13 is allowed to own. The allowlist form is deliberate: an
# unexpected table fails here even if its name looks innocent. Session B added
# vendor_review (FR5), promotion (FR6), facility_claim (FR7) and content_report
# (Q-8); the portal session added menu_item — none of them money tables.
#
# `menu_item` is the one worth pausing on, because it holds prices. It is the
# vendor's STANDING menu: what they sell and for how much, kept once instead of
# retyped for every appearance. It carries the same kind of number `offering`
# already carried and for the same reason — a driver deciding whether to detour
# needs to know what a plate costs. There is no order, no basket, no total, and
# nothing in this module can act on the figure. Adding it here was a deliberate
# decision, which is exactly what this allowlist exists to force.
ALLOWED_TABLES = {
    "vendor",
    "vendor_member",
    "vendor_document",
    "appearance",
    "offering",
    "menu_item",
    "vendor_review",
    "promotion",
    "facility_claim",
    "content_report",
}
# ...and a second, independent net: a money table fails on its NAME, so a future
# table cannot slip through merely by being added to the allowlist above.
MONEY_TABLE_WORDS = (
    "order",
    "payment",
    "charge",
    "payout",
    "invoice",
    "transaction",
    "ledger",
    "checkout",
    "price",
    "billing",
)


def _m13_tables() -> set[str]:
    from app.modules.m13_vendor.domain import models

    return {cls.__tablename__ for cls in vars(models).values() if hasattr(cls, "__tablename__")}


def test_the_schema_owns_only_its_declared_tables():
    assert _m13_tables() == ALLOWED_TABLES


def test_no_table_name_is_money_shaped():
    for table in _m13_tables():
        for word in MONEY_TABLE_WORDS:
            assert word not in table, f"Phase A forbids a money table: {table}"


def test_offering_price_is_information_only():
    # a price on a menu line is a fact about the world, like a fuel price on a pin —
    # nothing in this module can act on it
    columns = {c.name for c in m13.Offering.__table__.columns}
    assert "price_cents" in columns
    assert not columns & {"paid", "charged_at", "payment_ref", "order_id"}


def test_the_orders_flag_does_not_exist_yet(db):
    # Phase B is gated on a separate flag whose activation needs verified vendors, a
    # payment partner, and an owner go (PRD §17 Q13). It must not be pre-created.
    m13.register_module(db)
    assert flags.get_config(db, "m13_orders") is None
    keys = {f.key for f in db.query(flags.FeatureFlag).all()}
    assert "m13_orders" not in keys


def test_the_module_flag_is_registered_and_defaults_off(db):
    m13.register_module(db)
    assert m13.is_active(db) is False
    flags.enable(db, m13.FLAG_KEY)
    assert m13.is_active(db) is True
