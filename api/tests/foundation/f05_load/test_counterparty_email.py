"""The broker's address: validation, and the copy-on-write rule that guards edits (D1).

`contact_email` has been on the counterparty since F5 shipped and nothing but tests ever
wrote it — which is why every notice this product sent went to an invented literal. These
are the two pieces that make writing it safe.
"""

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f05_load import public as loads

VALID = [
    "ap@acme.example",
    "  ap@acme.example  ",  # trimmed
    "first.last+detention@sub.acme.example",
    "a@b.example",
]
INVALID = [
    ("acme.example", "no @"),
    ("ap@acme@example.com", "two @"),
    ("ap@acme", "no dot in the domain"),
    ("ap@.example", "domain starts with a dot"),
    ("ap@acme.", "domain ends with a dot"),
    ("@acme.example", "no local part"),
    ("ap@", "no domain"),
    ("ap acme@example.com", "whitespace"),
    ("Acme AP <ap@acme.example>", "a pasted display name"),
]


@pytest.mark.parametrize("raw", VALID)
def test_a_usable_address_is_accepted_and_trimmed(raw):
    assert loads.validate_contact_email(raw) == raw.strip()


@pytest.mark.parametrize("raw,why", INVALID)
def test_junk_is_refused_with_a_reason(raw, why):
    with pytest.raises(loads.InvalidContactEmail):
        loads.validate_contact_email(raw)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_nothing_means_clear_it_rather_than_fail(raw):
    """Removing the address on file is a legitimate request, not a validation error."""
    assert loads.validate_contact_email(raw) is None


def test_an_overlong_address_is_refused_at_the_columns_width():
    too_long = "a" * 310 + "@acme.example"  # 323 > 320
    assert len(too_long) > loads.MAX_CONTACT_EMAIL

    with pytest.raises(loads.InvalidContactEmail):
        loads.validate_contact_email(too_long)


# --- D1: in place, or copy-on-write ---
def _load_for(db, email_addr, broker=None, name="oo@example.com"):
    account = identity.register_account(db, name, "pw-123456")
    broker = broker or loads.create_counterparty(db, "Acme", loads.CounterpartyKind.broker)
    return account, broker, loads.create_load(db, account.id, counterparty_id=broker.id)


def test_a_row_only_this_account_uses_is_edited_in_place(db):
    _, broker, load = _load_for(db, None)

    counterparty, copied = loads.set_load_counterparty_email(db, load, "ap@acme.example")

    assert copied is False
    assert counterparty.id == broker.id  # same row
    assert broker.contact_email == "ap@acme.example"
    assert load.counterparty_id == broker.id


def test_a_row_another_account_also_uses_is_copied_not_edited(db):
    """Constructed directly: production does not share rows today, but nothing stops it.

    `create_counterparty` never dedupes, so one row per load is a property of ONE call
    site rather than of the schema — and if that ever changes, an in-place edit would mean
    one driver silently rewriting where another driver's detention notices go.
    """
    mine, broker, my_load = _load_for(db, None)
    theirs = identity.register_account(db, "other@example.com", "pw-123456")
    their_load = loads.create_load(db, theirs.id, counterparty_id=broker.id)

    counterparty, copied = loads.set_load_counterparty_email(db, my_load, "ap@acme.example")

    assert copied is True
    assert counterparty.id != broker.id
    assert counterparty.contact_email == "ap@acme.example"
    # my load points at the copy; theirs is untouched, address and all
    assert my_load.counterparty_id == counterparty.id
    assert their_load.counterparty_id == broker.id
    assert broker.contact_email is None


def test_the_copy_carries_the_counterpartys_identity_forward(db):
    mine, broker, my_load = _load_for(db, None)
    broker.name = "Acme Brokerage"
    broker.mc_number = "MC-112233"
    broker.contact_phone = "+1-555-0100"
    db.flush()
    theirs = identity.register_account(db, "other@example.com", "pw-123456")
    loads.create_load(db, theirs.id, counterparty_id=broker.id)

    copy, copied = loads.set_load_counterparty_email(db, my_load, "ap@acme.example")

    assert copied is True
    assert (copy.name, copy.kind, copy.mc_number, copy.contact_phone) == (
        "Acme Brokerage", broker.kind, "MC-112233", "+1-555-0100",
    )


def test_a_second_load_of_my_own_does_not_trigger_a_copy(db):
    """The rule is about OTHER accounts. Two of my own loads sharing a broker is mine to edit."""
    account, broker, first = _load_for(db, None)
    second = loads.create_load(db, account.id, counterparty_id=broker.id)

    counterparty, copied = loads.set_load_counterparty_email(db, first, "ap@acme.example")

    assert copied is False
    assert counterparty.id == broker.id
    assert second.counterparty_id == broker.id  # and it sees the new address too


def test_clearing_the_address_is_allowed(db):
    _, broker, load = _load_for(db, None)
    loads.set_load_counterparty_email(db, load, "ap@acme.example")

    counterparty, copied = loads.set_load_counterparty_email(db, load, None)

    assert copied is False
    assert counterparty.contact_email is None


def test_a_load_with_no_counterparty_is_refused_rather_than_silently_ignored(db):
    account = identity.register_account(db, "solo@example.com", "pw-123456")
    load = loads.create_load(db, account.id)

    with pytest.raises(loads.InvalidContactEmail):
        loads.set_load_counterparty_email(db, load, "ap@acme.example")
