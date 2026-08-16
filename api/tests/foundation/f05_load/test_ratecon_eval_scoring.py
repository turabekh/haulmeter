"""AI-CONTEXT: the eval's scoreboard, which is where its honesty lives (J1-A1).

`make ratecon-eval` itself calls the live model and is not a test — it is a measurement
with no fixed answer. But the function that decides what each answer COUNTS as is
ordinary logic, and if it were wrong the measurement would be confidently wrong in a way
nobody would catch: a scoreboard that scores an invented address as a miss reports a
number that looks fine.

The distinction these tests exist for is INVENTED versus MISSED. They are not two
degrees of the same error. A missed address costs a driver thirty seconds of typing. An
invented one puts a stranger's address in the field a driver is about to confirm, and
the field looks identical either way.
"""

import pytest

from scripts.ratecon_eval import _score

EMAIL = "counterparty_email"
PHONE = "counterparty_phone"


def test_the_printed_address_extracted_is_correct():
    assert _score(EMAIL, "ap@coyote.example", "ap@coyote.example") == "CORRECT"


def test_silence_answered_with_silence_is_a_pass():
    """A rate con that prints no address is not a failure of the parse, and scoring it
    as one would push the prompt toward guessing to raise its own number."""
    assert _score(EMAIL, None, None) == "ABSENT-OK"


def test_an_address_the_paper_prints_and_the_parse_did_not_is_a_miss():
    assert _score(EMAIL, "ap@coyote.example", None) == "MISSED"


def test_an_address_the_paper_never_printed_is_INVENTED_not_a_miss():
    """The one with a victim. Scored separately because it is not a degree of MISSED —
    the driver confirming it cannot tell a read address from an imagined one."""
    assert _score(EMAIL, None, "ap@coyote.example") == "INVENTED"


def test_the_wrong_address_is_wrong():
    assert _score(EMAIL, "ap@coyote.example", "dispatch@coyote.example") == "WRONG"


@pytest.mark.parametrize(
    ("expected", "got"),
    [
        ("(704) 555-0134", "7045550134"),
        ("704-555-0134", "+1 704 555 0134"),
        ("7045550134", "(704) 555-0134"),
    ],
)
def test_a_corpus_written_the_way_the_paper_prints_it_is_not_scored_wrong(expected, got):
    """The expectation goes through the same normaliser the parse output does. Without
    it, a corpus author who copied "(704) 555-0134" off the document exactly as printed
    would manufacture a WRONG on every phone in the corpus."""
    assert _score(PHONE, expected, got) == "CORRECT"


def test_a_fragment_the_parse_returned_counts_as_absence_not_as_wrong():
    """`parsed_email` turns `dispatch@` into None before it ever reaches a driver, so
    the eval must score what the DRIVER would see. Scoring the raw model output would
    measure a screen this product does not have."""
    assert _score(EMAIL, "ap@coyote.example", "dispatch@") == "MISSED"


def test_a_fragment_where_the_paper_printed_nothing_is_not_INVENTED():
    """Same reason, in the direction that matters: the fragment never becomes a
    recipient, so it has no victim and must not be counted as though it did. An eval
    that cried invented here would be un-actionable — the number would never reach
    zero and the flag would never go on."""
    assert _score(EMAIL, None, "dispatch@") == "ABSENT-OK"
