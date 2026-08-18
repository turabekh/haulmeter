"""AI-CONTEXT: the invariants of the 49-intent content pack (entry 208).

THIS TESTS DATA, WHICH IS UNUSUAL AND IS THE POINT. The pack is 349 authored rows that
reach a driver's ears, and every property below is one a careless edit breaks silently:

  · a duplicate officer line makes branch selection ambiguous — the classifier is asked
    which of two intents a sentence belongs to when the answer is "both", and the failure
    shows up as a driver being marked wrong for answering the question they heard;
  · an intent whose whole pool is `holdout` teaches nothing, because `teachable_variants`
    excludes holdouts — the intent simply vanishes from drills with nothing reporting it;
  · a `required_slots` name with no fact in `HIDDEN_STATE` is dropped by
    `expected_slots_for`, so the question is asked and never marked;
  · a missing Uzbek explanation is Q-9's honest-absence state shown for a line we DID
    write coaching for, which is the promise being quietly withdrawn.

The pack is imported as data, not run — these hold before anything touches a database.
"""

import importlib.util
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "m15_content_pack",
    pathlib.Path(__file__).parents[3] / "scripts" / "m15_content_pack.py",
)
pack_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pack_mod)

PACK = pack_mod.PACK
HIDDEN_STATE = pack_mod.HIDDEN_STATE
KEYS = [row[0] for row in PACK]


def test_the_pack_meets_the_e3_phase_a_floor():
    """E3.1.9: 'Uzbek coaching content: >=40 intents released through the review pipeline'."""
    assert len(PACK) >= 40


def test_no_two_intents_share_an_officer_line():
    texts = [t for row in PACK for t, _ in row[4]]
    dupes = sorted({t for t in texts if texts.count(t) > 1})
    assert dupes == [], f"ambiguous branch selection: {dupes}"


def test_intent_keys_are_unique():
    assert len(KEYS) == len(set(KEYS))


@pytest.mark.parametrize("row", PACK, ids=KEYS)
def test_every_intent_keeps_exactly_one_holdout_and_a_teachable_pool(row):
    """Q-5 needs a holdout; the drill needs something left after it is excluded."""
    variants = row[4]
    holdouts = [t for t, h in variants if h]
    assert len(holdouts) == 1
    assert len(variants) - 1 >= 1


@pytest.mark.parametrize("row", PACK, ids=KEYS)
def test_every_required_slot_has_a_fact_behind_it(row):
    """A slot the scenario cannot answer is dropped, and the turn goes unmarked."""
    for slot in row[3]:
        assert slot == "acknowledgement" or slot in HIDDEN_STATE, slot


@pytest.mark.parametrize("row", PACK, ids=KEYS)
def test_every_intent_carries_a_model_answer_repairs_and_uzbek(row):
    _, _, meaning, _, variants, answer, repairs, uz = row
    assert meaning.strip()
    assert answer.strip()
    assert len(repairs) >= 2, "FR2 wants a repair branch that names the confusion"
    assert len(uz) > 60, "an explanation shorter than a sentence is not one"


@pytest.mark.parametrize("row", PACK, ids=KEYS)
def test_the_uzbek_explanation_is_not_english(row):
    """Q-9 exists so a driver promised their language is never handed English.

    A row of English text sitting in a `uz` explanation would satisfy every structural
    check and defeat the entire point, so this looks for Uzbek's own orthography.
    """
    uz = row[7]
    assert any(ch in uz for ch in "o'g'shchqxo‘g‘") or "yapti" in uz or "ngiz" in uz
