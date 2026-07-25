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


def test_the_schema_has_no_money_table():
    from app.modules.m13_vendor.domain import models

    tables = {cls.__tablename__ for cls in vars(models).values() if hasattr(cls, "__tablename__")}
    assert tables == {"vendor", "vendor_member", "vendor_document", "appearance", "offering"}


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
