"""AI-CONTEXT: the broker contact parsed off the rate con (J1-A1).

The field, its validation and the F5 registry write have existed since the
counterparty-email session. Only the PARSE never filled them in, so every driver
retyped an address that was printed on the paper in their hand.

What these tests hold is the direction of the risk. A rate con that prints no email
costs a driver some typing; a rate con whose footer was misread into a plausible
address mails a stranger the details of a load. So the negative cases are the ones
that matter here, and there are more of them than positive ones on purpose.
"""

import pytest

from app.foundation.f05_load import public as loads
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f13_flags import public as flags

# a whole parse, so the tests exercise the shape the screen actually receives
BASE = {
    "reference_number": "ABC-1234",
    "broker_name": "Cardinal Logistics",
    "counterparty_email": None,
    "counterparty_phone": None,
    "rate_cents": 185000,
    "detention_rate_cents_per_hour": 5000,
    "free_time_minutes": 120,
    "stops": [],
    "accessorial_terms": [],
}


def _parsed(**over):
    return {**BASE, **over}


# --- the address, when the paper prints one ---


def test_a_printed_address_is_extracted():
    assert loads.parsed_email(_parsed(counterparty_email="dispatch@cardinal.example")) == (
        "dispatch@cardinal.example"
    )


def test_surrounding_whitespace_is_not_a_different_address():
    assert loads.parsed_email(_parsed(counterparty_email="  ap@cardinal.example \n")) == (
        "ap@cardinal.example"
    )


# --- absence, in every spelling a model reaches for ---


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "N/A",
        "n/a",
        "none",
        "None",
        "TBD",
        "unknown",
        "not provided",
        "Not Stated",
        "no email on file",
        "-",
        "—",
    ],
)
def test_a_way_of_saying_nothing_is_not_an_address(raw):
    """Every one of these would otherwise be STORED as the recipient and rendered on the
    packet sheet as an address that was found."""
    assert loads.parsed_email(_parsed(counterparty_email=raw)) is None


@pytest.mark.parametrize(
    "raw",
    [
        "dispatch@",  # a footer that ran off the edge of the photograph
        "@cardinal.example",
        "dispatch@cardinal",  # no dot: not a domain this product can post to
        "dispatch at cardinal.example",
        "dispatch@cardinal.example, ap@cardinal.example",  # two, so which one
        "Cardinal Logistics",
        "www.cardinal.example",
        "dispatch@@cardinal.example",
        "dispatch@.example",
        "dispatch@cardinal.",
    ],
)
def test_a_broken_read_becomes_absence_not_a_repair(raw):
    """A rate con is not INVALID because a model misread its footer — the driver still
    has a field to type in. What must never happen is the state in between: a fragment
    stored as a recipient."""
    assert loads.parsed_email(_parsed(counterparty_email=raw)) is None


def test_the_parse_is_held_to_the_same_rule_the_driver_is():
    """One rule, not two. An address the typed-entry path would reject cannot enter the
    registry through the parse instead."""
    from app.foundation.f05_load.domain.service import InvalidContactEmail

    bad = "dispatch@cardinal"
    with pytest.raises(InvalidContactEmail):
        loads.validate_contact_email(bad)
    assert loads.parsed_email(_parsed(counterparty_email=bad)) is None


# --- the phone ---


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(704) 555-0134", "7045550134"),
        ("704-555-0134", "7045550134"),
        ("704.555.0134", "7045550134"),
        ("+1 704 555 0134", "7045550134"),
        ("17045550134", "7045550134"),
    ],
)
def test_a_printed_number_is_normalised(raw, expected):
    assert loads.parsed_phone(_parsed(counterparty_phone=raw)) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "N/A",
        "704-555-0134 x229",  # an extension: which ten digits are the number?
        "704-555-0134 / 704-555-0199",  # two numbers in one cell
        "555-0134",  # no area code
        "0134",
        "see rate confirmation",
    ],
)
def test_an_ambiguous_number_is_absence(raw):
    """Truncating to the last ten digits is the shape used for a number a HUMAN typed
    into a phone field. Applied to a machine read of a printed cell it turns
    "555-0134 x229" into a number that dials someone else."""
    assert loads.parsed_phone(_parsed(counterparty_phone=raw)) is None


# --- the halves are independent ---


def test_a_phone_without_an_email_is_not_a_failure_of_either():
    contact = loads.parsed_contact(_parsed(counterparty_phone="(704) 555-0134"))
    assert contact == {"email": None, "phone": "7045550134"}


# --- the prompt the DATABASE serves, which is the one that runs ---


def test_a_changed_template_reaches_the_live_parse(db):
    """AI-CONTEXT: the deploy that changes nothing (TRAPS §1).

    `parse_structured` runs the template stored in the database, not the constant in
    the source. The registration used to be `if get_active_prompt(...) is None`, so on
    any box that had ever parsed a rate con the row written on the first call served
    forever — and this session's edit, which adds `counterparty_email` to the schema,
    would have shipped a schema demanding a field the live prompt never asked for.
    """
    ai.register_prompt(db, loads.RATE_CON_PROMPT, ai.AiTask.document_parse, "an older wording")
    db.flush()

    loads.register_rate_con_prompt(db)

    active = ai.get_active_prompt(db, loads.RATE_CON_PROMPT)
    assert active.template == loads.PROMPT_TEMPLATE
    assert active.version == 2


def test_the_earlier_wording_is_kept_rather_than_overwritten(db):
    """A prompt is versioned so an `AiCall` made last week is still readable against the
    text that made it. Bumping the version must not be an in-place edit wearing a
    different name."""
    from sqlalchemy import select

    from app.foundation.f09_ai_gateway.domain.models import Prompt

    ai.register_prompt(db, loads.RATE_CON_PROMPT, ai.AiTask.document_parse, "an older wording")
    db.flush()

    loads.register_rate_con_prompt(db)

    templates = {
        (row.version, row.template)
        for row in db.scalars(select(Prompt).where(Prompt.key == loads.RATE_CON_PROMPT))
    }
    assert (1, "an older wording") in templates
    assert (2, loads.PROMPT_TEMPLATE) in templates


def test_registering_twice_does_not_pile_up_versions(db):
    loads.register_rate_con_prompt(db)
    loads.register_rate_con_prompt(db)
    loads.register_rate_con_prompt(db)
    active = ai.get_active_prompt(db, loads.RATE_CON_PROMPT)
    assert active.version == 1


def test_the_prompt_asks_for_every_key_the_schema_requires():
    """The two drifted apart once already: a schema key the prompt never mentions is a
    field the model is required to return and was never told about."""
    for key in loads.RATE_CON_SCHEMA["required"]:
        assert key in loads.PROMPT_TEMPLATE, f"schema requires {key}; the prompt never names it"


def test_the_prompt_forbids_inventing_an_address():
    """The instruction is load-bearing, not decorative — it is the only thing standing
    between a company name and a guessed address."""
    assert "Never build an address from a company name" in loads.PROMPT_TEMPLATE


# --- the flag ---


def test_the_flag_is_registered_and_ships_off(db):
    loads.register_rate_con_contact(db)
    assert flags.is_enabled(db, loads.CONTACT_FLAG) is False
