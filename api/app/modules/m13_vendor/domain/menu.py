"""AI-CONTEXT: M13 — the vendor's standing menu (PRD extension §E1, portal session).

Offerings were keyed to the APPEARANCE and nothing else, so a cook retyped every
dish and every price for every window they published. This is the list they keep.

**The separation is the design, not an accident of layering.** A `MenuItem` is what
the vendor sells; an `Offering` is what was ADVERTISED for one window. Publishing
copies the first into the second, so raising a price today changes what will be
advertised next and never what a driver was shown last Tuesday. The reliability
record and the reviews both refer to past windows, and a menu that rewrote history
would make them unauditable.

**Nothing here moves money.** `price_cents` is information only, exactly as on
`Offering` — Phase A processes no payments and the platform sells nothing
(§E1.1). There is no order, no basket, no total, and no billing column.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import MenuItem, Vendor
from .service import OfferingIn

MAX_MENU_ITEMS = 40
MAX_PRICE_CENTS = 100_000  # $1,000 — a plate of food, not a truck payment
MAX_ITEM_NAME_CHARS = 120


class InvalidMenuItem(Exception):
    pass


def _validate(name: str, price_cents: int, portions: int | None) -> str:
    clean = (name or "").strip()
    if not clean:
        raise InvalidMenuItem("a menu item needs a name")
    if len(clean) > MAX_ITEM_NAME_CHARS:
        raise InvalidMenuItem(f"at most {MAX_ITEM_NAME_CHARS} characters")
    if price_cents is None or price_cents < 0:
        raise InvalidMenuItem("a price is required")
    if price_cents > MAX_PRICE_CENTS:
        # Q-4 exists because "food available" is useless to a driver deciding on a
        # detour; a mistyped $1,200 tamale is the same failure wearing a number
        raise InvalidMenuItem("that price looks like a typo")
    if portions is not None and portions < 0:
        raise InvalidMenuItem("portions cannot be negative")
    return clean


def list_menu(db: Session, vendor_id, include_inactive: bool = False) -> list[MenuItem]:
    stmt = select(MenuItem).where(MenuItem.vendor_id == vendor_id)
    if not include_inactive:
        stmt = stmt.where(MenuItem.is_active.is_(True))
    return list(db.scalars(stmt.order_by(MenuItem.sort_order, MenuItem.name)))


def add_menu_item(
    db: Session,
    vendor: Vendor,
    name: str,
    price_cents: int,
    portions: int | None = None,
    sort_order: int | None = None,
) -> MenuItem:
    clean = _validate(name, price_cents, portions)
    existing = db.scalar(
        select(MenuItem).where(MenuItem.vendor_id == vendor.id, MenuItem.name == clean)
    )
    if existing is not None:
        # a cook re-adding a dish they retired means "bring it back", not "make a
        # second one" — the unique constraint would refuse anyway, and refusing with
        # a database error is not an answer
        existing.price_cents = price_cents
        existing.portions = portions
        existing.is_active = True
        existing.updated_at = datetime.now(UTC)
        db.flush()
        return existing

    if len(list_menu(db, vendor.id, include_inactive=True)) >= MAX_MENU_ITEMS:
        raise InvalidMenuItem(f"a menu holds at most {MAX_MENU_ITEMS} items")

    item = MenuItem(
        vendor_id=vendor.id,
        name=clean,
        price_cents=price_cents,
        portions=portions,
        sort_order=sort_order if sort_order is not None else len(list_menu(db, vendor.id)),
    )
    db.add(item)
    db.flush()
    return item


def update_menu_item(
    db: Session,
    vendor: Vendor,
    item_id,
    name: str | None = None,
    price_cents: int | None = None,
    portions: int | None = None,
    is_active: bool | None = None,
    sort_order: int | None = None,
) -> MenuItem:
    item = db.scalar(
        select(MenuItem).where(MenuItem.id == item_id, MenuItem.vendor_id == vendor.id)
    )
    if item is None:
        # scoped by vendor in the QUERY, so another vendor's item is indistinguishable
        # from one that does not exist — a tenancy check that cannot be forgotten
        raise InvalidMenuItem("no such menu item")

    clean = _validate(
        name if name is not None else item.name,
        price_cents if price_cents is not None else item.price_cents,
        portions if portions is not None else item.portions,
    )
    item.name = clean
    if price_cents is not None:
        item.price_cents = price_cents
    if portions is not None:
        item.portions = portions
    if is_active is not None:
        item.is_active = is_active
    if sort_order is not None:
        item.sort_order = sort_order
    item.updated_at = datetime.now(UTC)
    db.flush()
    return item


def remove_menu_item(db: Session, vendor: Vendor, item_id) -> MenuItem:
    """Retires an item rather than deleting it. Past appearances hold their own
    price snapshots, so nothing published is at risk either way — but a seasonal
    dish comes back, and a cook who removed one by accident should not have to
    remember what it cost."""
    return update_menu_item(db, vendor, item_id, is_active=False)


def menu_as_offerings(db: Session, vendor_id, item_ids=None) -> list[OfferingIn]:
    """The bridge to `publish_appearance`. Returns what to ADVERTISE, which the
    publish path then snapshots — this function hands over values, never rows, so
    there is no way for a later menu edit to reach back into a published window."""
    items = list_menu(db, vendor_id)
    if item_ids is not None:
        wanted = {str(i) for i in item_ids}
        items = [i for i in items if str(i.id) in wanted]
    return [OfferingIn(name=i.name, price_cents=i.price_cents, portions=i.portions) for i in items]


__all__ = [
    "MAX_ITEM_NAME_CHARS",
    "MAX_MENU_ITEMS",
    "MAX_PRICE_CENTS",
    "InvalidMenuItem",
    "add_menu_item",
    "list_menu",
    "menu_as_offerings",
    "remove_menu_item",
    "update_menu_item",
]
