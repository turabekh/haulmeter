"""AI-CONTEXT: server-side speech adapters (E3 §E3.4, D14). Decision 204's "later" is now.

THE FAKE IS NEVER SELECTED AUTOMATICALLY, and that single rule is what separates this file
from `provider.py` next to it. `resolve_provider()` falls back to `FakeModelProvider` when
no key is set, which is right for text: a canned parse is visibly canned, and the feature
degrades into something obviously not real.

Speech cannot degrade that way. A scoring control fed by a fake transcript produces a
band, and a band looks exactly like a real one — so the driver is told something about
their English on the strength of nothing. E3 §E3.4.5 therefore inverts the rule: an unset
key REFUSES. `resolve_stt` and `resolve_tts` raise; they never return a Fake. Tests get
their fakes by passing them in explicitly, which is also why the fakes live here rather
than being reachable by configuration — a fake you must name in a test is a fake that
cannot reach production by an absent environment variable.

THE PROVIDER IS ABSTRACTED because the choice is not made yet. Deepgram is E3's first
candidate, and §E3.4.1 is explicit that the decision (against Whisper-large) is made on
the accented-English benchmark built from PILOT sessions, not in advance. So the adapter
protocol is what m15 depends on and the vendor is what it does not.

AUDIO IS METERED IN MINUTES, not tokens. The F-17 invariant — no uncapped state exists —
already covers m15 through its `ModuleBudget` row; what audio needs is a rate that makes
minutes comparable to the token spend in the same budget, and an anomaly alert, because a
loop that re-transcribes one file is a bill rather than an error.
"""

from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import get_settings

from .enums import AiTask
from .service import _check_budget, _record_call

# AI-CONTEXT: micros of USD per audio minute, one number per direction, deliberately
# coarse. These exist so audio spends from the SAME per-module budget as text rather than
# from an unmetered side channel — a second budget nobody reads is how an uncapped state
# comes back. Real per-vendor rates land with the vendor decision (§E3.4.1); until then
# these are honest round numbers and the anomaly alert is the real guard.
STT_COST_PER_MINUTE_MICROS = 7_000
TTS_COST_PER_MINUTE_MICROS = 16_000

# minutes of audio for one module in one call that should never happen in normal use. A
# roadside check is minutes long; anything past this is a loop, a retry storm, or a file
# being re-processed, and all three are bills.
ANOMALY_MINUTES_PER_CALL = 30.0


class SpeechUnavailable(RuntimeError):
    """No speech key is configured — this deployment cannot transcribe or synthesize.

    Deliberately NOT a fallback. See the module docstring: a fake transcript produces a
    real-looking band about a real driver's English.
    """


class SpeechAnomaly(RuntimeError):
    """A single call asked for implausibly much audio — refused before it is billed."""


class SttAdapter(Protocol):
    """Streaming speech-to-text. `stream` yields interim text; `transcribe` is the whole."""

    name: str

    def transcribe(self, audio: bytes, *, locale: str) -> tuple[str, float]:
        """Returns (transcript, confidence). Confidence is what quality law Q-2 reads."""
        ...


class TtsAdapter(Protocol):
    """Batch text-to-speech, run as worker jobs at content release (§E3.4.2)."""

    name: str

    def synthesize(self, text: str, *, locale: str, voice: str | None = None) -> bytes: ...


class FakeSttAdapter:
    """AI-CONTEXT: reachable ONLY by a test that names it. Never returned by resolve_stt.

    It returns a fixed confidence a test can drive Q-2 with, and a transcript derived from
    nothing — which is exactly why it must never be selectable by configuration.
    """

    name = "fake"

    def __init__(self, transcript: str = "fake transcript", confidence: float = 0.99) -> None:
        self._transcript = transcript
        self._confidence = confidence

    def transcribe(self, audio: bytes, *, locale: str) -> tuple[str, float]:
        return self._transcript, self._confidence


class FakeTtsAdapter:
    name = "fake"

    def synthesize(self, text: str, *, locale: str, voice: str | None = None) -> bytes:
        return b"FAKEAUDIO:" + text.encode()


class DeepgramSttAdapter:
    """E3 §E3.4.1's first candidate. The network call lands with the vendor decision.

    AI-CONTEXT: this refuses at CONSTRUCTION when the key is absent rather than at first
    use. A half-built adapter that raises later is one that can be handed to a scheduler
    and fail in a worker log nobody reads.
    """

    name = "deepgram"

    def __init__(self) -> None:
        key = get_settings().deepgram_api_key
        if not key:
            raise SpeechUnavailable(
                "DEEPGRAM_API_KEY is not set: this deployment cannot transcribe. Refusing "
                "rather than degrading — a fake transcript scores a real driver (E3 §E3.4.5)."
            )
        self._key = key

    def transcribe(self, audio: bytes, *, locale: str) -> tuple[str, float]:
        raise NotImplementedError(
            "the Deepgram network call is a NAMED REMAINDER of Session A: the adapter seam, "
            "its refusal and its metering are built and tested on fixtures; live smoke "
            "waits on the account (E3 §E3.8 key-tolerant start)."
        )


class AzureTtsAdapter:
    """Officer and Uzbek coach voices (§E3.4.2), synthesized at content release."""

    name = "azure"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.azure_speech_key or not settings.azure_speech_region:
            raise SpeechUnavailable(
                "AZURE_SPEECH_KEY / AZURE_SPEECH_REGION are not set: this deployment "
                "cannot synthesize. Refusing rather than degrading (E3 §E3.4.5)."
            )
        self._key = settings.azure_speech_key
        self._region = settings.azure_speech_region

    def synthesize(self, text: str, *, locale: str, voice: str | None = None) -> bytes:
        raise NotImplementedError(
            "the Azure network call is a NAMED REMAINDER of Session A; the Uzbek voices "
            "additionally need a native spot-check before any driver hears them."
        )


def stt_configured() -> bool:
    return bool(get_settings().deepgram_api_key)


def tts_configured() -> bool:
    settings = get_settings()
    return bool(settings.azure_speech_key and settings.azure_speech_region)


def resolve_stt() -> SttAdapter:
    """The configured STT adapter, or a refusal. NEVER a Fake."""
    return DeepgramSttAdapter()


def resolve_tts() -> TtsAdapter:
    """The configured TTS adapter, or a refusal. NEVER a Fake."""
    return AzureTtsAdapter()


def record_audio_minutes(
    db: Session,
    module: str,
    task: AiTask,
    minutes: float,
    *,
    model: str = "speech",
) -> int:
    """Meter audio against the module's existing budget. Returns the cost in micros.

    AI-CONTEXT: the budget is CHECKED BEFORE and the anomaly BEFORE that, in that order
    and for different reasons. The anomaly guard is not a budget guard — a single 40-minute
    transcription may sit well inside a monthly cap and still be a retry loop. Catching it
    at the call is the only place the distinction is visible; by the month's end both look
    like spend.
    """
    if minutes > ANOMALY_MINUTES_PER_CALL:
        raise SpeechAnomaly(
            f"{module} asked to process {minutes:.1f} audio minutes in one call "
            f"(limit {ANOMALY_MINUTES_PER_CALL}); refusing before it is billed"
        )
    _check_budget(db, module)

    rate = STT_COST_PER_MINUTE_MICROS if task is AiTask.stt else TTS_COST_PER_MINUTE_MICROS
    cost = int(minutes * rate)
    # recorded through F9's own call log so audio and text share one budget and one
    # place an operator looks. Tokens are the wrong unit here, so the cost is carried
    # as output "tokens" priced at 1 micro each would be a lie — instead the row is
    # written with zero tokens and the cost stated directly.
    _record_call(db, module, task, model, 0, 0, cost_micros_override=cost)
    return cost
