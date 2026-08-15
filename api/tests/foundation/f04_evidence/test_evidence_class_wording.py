"""AI-CONTEXT: what an ELD-derived pack is allowed to say to a counterparty (M14-FR3).

WRITTEN BEFORE THE RENDERER CHANGED, AND WATCHED FAIL. That is the kickoff's requirement
and it is not ceremony: *"A guard nobody has watched fail is the species that shipped
`.cluster` at 36 dp."*

THE SENTENCE THIS IS ABOUT. The pack's location block says, today, for every pack:

    "Location data as reported by the driver's device. The hash chain shows these
     records are unaltered since capture; it does not attest how they were produced."

Every clause of that is true of a phone-verified pack and the first clause is FALSE of an
ELD-derived one: it credits a driver's device for readings a telematics provider produced.
§11.7 aimed at a counterparty — an AP clerk who catches a pack overclaiming once distrusts
every pack after it, and this product's whole argument to a broker is that its documents
are worth more than a screenshot.

WHAT EACH CLASS MAY CLAIM:
  · `phone_verified` — hash-chained capture, EXIF, server timestamps.
  · `eld_derived`    — PROVIDER-reported timestamps, provider NAMED, and explicitly not
                       covered by the capture chain.
  · `mixed`          — both, saying which artifacts sit on which side.
"""

from app.foundation.f04_evidence.domain import render

# the exact clause that must not appear over provider data
DEVICE_CLAUSE = "as reported by the driver's device"
CHAIN_CLAUSE = "unaltered since capture"


def _text(evidence_class: str, providers=(), pings: int = 12) -> str:
    context = render.PackContext(
        location_basis={
            "pings": pings,
            "accuracy_min_m": 4.0,
            "accuracy_median_m": 8.0,
            "accuracy_max_m": 30.0,
            "accuracy_reported": pings,
            "divergent_clock_pings": 0,
            "implausible_moves": 0,
        },
        evidence_class=evidence_class,
        evidence_providers=list(providers),
    )
    return render.location_basis_text(context)


def test_a_phone_pack_still_says_what_it_always_said():
    """The class that shipped, unchanged. Every existing pack is this one, and a wording
    change here would alter documents already sent to brokers."""
    text = _text("phone_verified")
    assert DEVICE_CLAUSE in text
    assert CHAIN_CLAUSE in text


def test_an_eld_pack_never_credits_the_drivers_device():
    # the whole defect in one assertion
    text = _text("eld_derived", providers=["motive"])
    assert DEVICE_CLAUSE not in text


def test_an_eld_pack_NAMES_the_provider():
    """§11.7: state who said what. A pack that says 'a telematics provider' without
    naming it gives a clerk nothing to check."""
    text = _text("eld_derived", providers=["motive"])
    assert "Motive" in text or "motive" in text


def test_an_eld_pack_does_not_claim_the_capture_chain_covers_it():
    """The chain proves OUR COPY is unaltered since we received it. It says nothing about
    how the reading was produced, and for provider data it does not even cover the
    capture — there was no capture. Claiming otherwise is the overclaim that costs a
    clerk's trust in every later pack."""
    text = _text("eld_derived", providers=["motive"])
    assert CHAIN_CLAUSE not in text


def test_a_mixed_pack_says_which_side_each_source_sits_on():
    text = _text("mixed", providers=["motive"])
    assert DEVICE_CLAUSE in text  # the phone half is still the phone half
    assert "Motive" in text or "motive" in text


def test_an_absent_trail_still_asserts_nothing_whatever_the_class():
    """The honest-absence branch survives the new classes. A zero rendered as
    '0 implausible movements' would be the strongest sentence on the page and completely
    unearned."""
    for cls in ("phone_verified", "eld_derived", "mixed"):
        text = _text(cls, providers=["motive"], pings=0)
        assert "not available" in text.lower()
        assert "0 implausible" not in text
