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


def test_a_configured_adapter_names_its_remainder(monkeypatch):
    """The network call is a named remainder, and it says so rather than returning ''."""
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-present")
    get_settings.cache_clear()
    with pytest.raises(NotImplementedError, match="NAMED REMAINDER"):
        speech.resolve_stt().transcribe(b"audio", locale="en")


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
