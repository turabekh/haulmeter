"""AI-CONTEXT: the speech seam refuses when unset, and is metered when it runs (E3 §E3.4).

The assertion this file exists for is `test_resolve_never_returns_a_fake`. Everything else
here would still pass if `resolve_stt` quietly fell back to `FakeSttAdapter` the way
`resolve_provider` falls back for text — and that fallback is precisely the defect E3
§E3.4.5 forbids, because a fake transcript yields a real-looking band about a real
driver's English. A scoring control that degrades silently has become decoration.
"""

import pytest

from app.core.config import get_settings
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f09_ai_gateway.domain import speech
from app.foundation.f09_ai_gateway.domain.enums import AiTask

MODULE = "m15"


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- the loud refusal ---------------------------------------------------------------


def test_unset_stt_key_refuses():
    with pytest.raises(speech.SpeechUnavailable):
        speech.resolve_stt()
    assert speech.stt_configured() is False


def test_unset_tts_key_refuses():
    with pytest.raises(speech.SpeechUnavailable):
        speech.resolve_tts()
    assert speech.tts_configured() is False


def test_a_half_configured_tts_still_refuses(monkeypatch):
    """A key with no region is not configuration, it is a half-finished deploy."""
    monkeypatch.setenv("AZURE_SPEECH_KEY", "present")
    get_settings.cache_clear()
    with pytest.raises(speech.SpeechUnavailable):
        speech.resolve_tts()


def test_resolve_never_returns_a_fake(monkeypatch):
    """THE assertion of this file: refusing must not become falling back.

    `provider.resolve_provider()` returns a deterministic Fake when its key is absent,
    which is correct for text. If this seam ever grew the same habit, a driver would be
    scored on a transcript nobody produced — and every other test here would still pass.
    """
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-present")
    get_settings.cache_clear()
    adapter = speech.resolve_stt()
    assert not isinstance(adapter, speech.FakeSttAdapter)
    assert adapter.name == "deepgram"


def test_a_configured_adapter_is_wired_to_its_provider(monkeypatch):
    """The remainder Session A named is CLOSED — the call is implemented.

    AI-CONTEXT: this asserts the wiring WITHOUT making a request. An earlier version of
    this test expected `NotImplementedError`, and when the call landed it started making a
    real HTTP request from the unit suite and failing on a 401 — a unit test that reaches
    the internet is a unit test that fails when someone's wifi does. The live proof lives
    in `make m15-key-smoke`, which is run deliberately and reported in the handoff.
    """
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-present")
    get_settings.cache_clear()
    adapter = speech.resolve_stt()
    assert adapter.name == "deepgram"
    assert adapter.ENDPOINT.startswith("https://api.deepgram.com/")
    assert callable(adapter.transcribe)


# --- the fakes are for tests, by name only ------------------------------------------


def test_the_fake_is_usable_when_a_test_names_it():
    transcript, confidence = speech.FakeSttAdapter("six hours", 0.42).transcribe(
        b"", locale="en"
    )
    assert transcript == "six hours"
    assert confidence == 0.42


# --- metering (E3 §E3.4.4, the F-17 invariant) --------------------------------------


def test_audio_minutes_spend_the_modules_existing_budget(db):
    ai.set_module_budget(db, MODULE, 25_000_000)
    before = ai.budget_used(db, MODULE)

    cost = speech.record_audio_minutes(db, MODULE, AiTask.stt, 4.0)

    assert cost == int(4.0 * speech.STT_COST_PER_MINUTE_MICROS)
    after = ai.budget_used(db, MODULE)
    assert after - before == cost, "audio must spend the SAME budget as text, not a side channel"


def test_tts_and_stt_are_priced_separately(db):
    ai.set_module_budget(db, MODULE, 25_000_000)
    stt = speech.record_audio_minutes(db, MODULE, AiTask.stt, 1.0)
    tts = speech.record_audio_minutes(db, MODULE, AiTask.tts, 1.0)
    assert stt != tts


def test_an_exhausted_budget_refuses_audio(db):
    """The F-17 invariant reaches m15's first audio minute, not just its text."""
    ai.set_module_budget(db, MODULE, 1)
    speech.record_audio_minutes(db, MODULE, AiTask.stt, 1.0)
    with pytest.raises(ai.BudgetExceeded):
        speech.record_audio_minutes(db, MODULE, AiTask.stt, 1.0)


def test_an_implausible_call_is_refused_before_it_is_billed(db):
    """The anomaly guard is NOT the budget guard, and the difference is the point.

    A single 40-minute transcription sits comfortably inside a monthly cap and is still a
    retry loop or a file being re-processed. At the call it is visible; by the month's end
    it is indistinguishable from ordinary spend.
    """
    ai.set_module_budget(db, MODULE, 25_000_000)
    with pytest.raises(speech.SpeechAnomaly):
        speech.record_audio_minutes(db, MODULE, AiTask.stt, 45.0)
    assert ai.budget_used(db, MODULE) == 0, "a refused call must not be billed"


def test_the_officer_is_SPOKEN_not_read_aloud(monkeypatch):
    """AI-CONTEXT: the owner said "now it is reading a text", and the bare-string SSML was
    most of the reason.

    A voice with no speaking style renders in its neutral read-aloud register. This asserts
    on the SSML BODY that actually goes to Azure — not on the arguments the caller passed —
    because a style that never reaches the request is indistinguishable from no style at
    all, and the symptom is a complaint about the product rather than an error.
    """
    from app.foundation.f09_ai_gateway.domain import speech as _speech
    from app.foundation.f09_ai_gateway.domain.speech import AzureTtsAdapter

    sent = {}

    class _Resp:
        content = b"AUDIO"

        def raise_for_status(self):
            return None

    class _Client:
        def post(self, url, headers=None, content=None):
            sent["ssml"] = content.decode()
            return _Resp()

    # the POOLED client — speech keeps one open so it stops paying a TLS handshake on
    # every call, twice per spoken turn
    monkeypatch.setattr(_speech, "_http", lambda: _Client())
    monkeypatch.setattr(
        "app.foundation.f09_ai_gateway.domain.speech.get_settings",
        lambda: type("S", (), {"azure_speech_key": "k", "azure_speech_region": "r"})(),
    )

    adapter = AzureTtsAdapter()
    adapter.synthesize(
        "Six hours. Let me see your logbook.",
        locale="en-US",
        voice="en-US-KaiNeural",
        style="conversation",
        rate="-4%",
    )

    assert 'name="en-US-KaiNeural"' in sent["ssml"]
    assert '<mstts:express-as style="conversation">' in sent["ssml"]
    assert '<prosody rate="-4%">' in sent["ssml"]
    # the namespace, without which Azure rejects express-as outright
    assert 'xmlns:mstts="https://www.w3.org/2001/mstts"' in sent["ssml"]

    # ...and a voice with no style degrades to plain speech rather than a 400
    adapter.synthesize("Plain.", locale="en-US", voice="en-US-GuyNeural")
    assert "express-as" not in sent["ssml"]
    assert "prosody" not in sent["ssml"]
