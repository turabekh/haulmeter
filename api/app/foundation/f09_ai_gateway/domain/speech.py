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


# AI-CONTEXT: ONE CONNECTION POOL FOR SPEECH, for the same reason the model gateway has
# one. Measured on the box, a fresh connection costs ~0.08s of TCP and TLS over a pooled
# one — and the roadside officer pays it twice per spoken turn, once to transcribe the
# driver and once to speak back. Lazy and module-level: `httpx.Client` is thread-safe, and
# building it at import time would make importing this module do network setup that the
# test suite and every CLI script would pay for without making a request.
_HTTP = None


def _http():
    global _HTTP
    if _HTTP is None:
        import httpx

        _HTTP = httpx.Client(timeout=60.0, limits=httpx.Limits(max_keepalive_connections=8))
    return _HTTP


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

    def synthesize(
        self,
        text: str,
        *,
        locale: str,
        voice: str | None = None,
        style: str | None = None,
        rate: str | None = None,
    ) -> bytes: ...


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

    def synthesize(
        self,
        text: str,
        *,
        locale: str,
        voice: str | None = None,
        style: str | None = None,
        rate: str | None = None,
    ) -> bytes:
        # AI-CONTEXT: accepts the full signature deliberately. Callers wrap synthesis in
        # `except Exception: return None`, so an adapter that rejects a keyword does not
        # raise anywhere a human sees — it silently produces an officer with no voice.
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

    # AI-CONTEXT: nova-2 with punctuation off. Punctuation is a rendering choice made by
    # the recogniser, and the scorer matches FACTS — a trailing full stop that changes
    # whether "Chicago." matches "Chicago" would be the recogniser deciding a driver's
    # score. `_normalize` in m15's scorer strips it anyway; not asking for it is cheaper
    # and keeps the transcript closer to what was actually said.
    ENDPOINT = "https://api.deepgram.com/v1/listen"

    def transcribe(self, audio: bytes, *, locale: str) -> tuple[str, float]:
        resp = _http().post(
            self.ENDPOINT,
            params={"model": "nova-2", "language": locale, "punctuate": "false"},
            headers={
                "Authorization": f"Token {self._key}",
                "Content-Type": "audio/wav",
            },
            content=audio,
        )
        resp.raise_for_status()
        payload = resp.json()
        try:
            best = payload["results"]["channels"][0]["alternatives"][0]
        except (KeyError, IndexError) as exc:
            raise SpeechUnavailable(
                f"Deepgram returned no alternative to read: {payload!r}"
            ) from exc
        # AI-CONTEXT: confidence travels with the transcript because Q-2 is built on it.
        # A transcript without its confidence cannot be floored, and an unfloored
        # transcript is scored — which is how a driver the recogniser could not hear ends
        # up marked wrong.
        return best.get("transcript", ""), float(best.get("confidence", 0.0))


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

    # 24 kHz mono MP3: small enough for a driver's data plan, good enough that an
    # officer line does not sound like a telephone.
    OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"

    def synthesize(
        self,
        text: str,
        *,
        locale: str,
        voice: str | None = None,
        style: str | None = None,
        rate: str | None = None,
    ) -> bytes:
        """AI-CONTEXT: SSML, not a bare string — the difference between speaking and
        reading aloud.

        The owner's words were "now it is reading a text", and the plain-text path was
        most of why. Two things are sent now that were not:

          · **`<mstts:express-as style=…>`** — a speaking style, where the voice has one.
            `en-US-KaiNeural` ships a `conversation` style and `en-US-DavisNeural` a
            `chat` style; without it every voice defaults to its neutral read-aloud
            register, which is exactly the complaint.
          · **`<prosody rate=…>`** — Azure's default pace is a shade brisk for someone
            standing at a window with a clipboard, and a small slowdown reads as
            deliberate rather than as slow.

        Both are OPTIONAL and the SSML degrades to what it used to be when they are not
        given, because not every voice supports a style and sending one that a voice does
        not have is a 400 rather than a shrug.
        """
        import html

        voice_name = voice or "en-US-GuyNeural"
        # AI-CONTEXT: the text is ESCAPED into the SSML. Officer lines and coach
        # explanations are authored content today, but they will one day carry a slot
        # fragment built from a driver's own words — and an unescaped apostrophe or
        # ampersand in that position is a malformed request at best.
        body = html.escape(text)
        if rate:
            body = f'<prosody rate="{html.escape(rate)}">{body}</prosody>'
        if style:
            body = f'<mstts:express-as style="{html.escape(style)}">{body}</mstts:express-as>'
        ssml = (
            f'<speak version="1.0" xml:lang="{locale}" '
            f'xmlns:mstts="https://www.w3.org/2001/mstts">'
            f'<voice name="{voice_name}">{body}</voice></speak>'
        )
        resp = _http().post(
            f"https://{self._region}.tts.speech.microsoft.com/cognitiveservices/v1",
            headers={
                "Ocp-Apim-Subscription-Key": self._key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": self.OUTPUT_FORMAT,
                "User-Agent": "haulmeter-m15",
            },
            content=ssml.encode("utf-8"),
        )
        resp.raise_for_status()
        if not resp.content:
            raise SpeechUnavailable("Azure returned an empty audio body")
        return resp.content


# AI-CONTEXT: WHICH LANGUAGES DEEPGRAM CAN ACTUALLY HEAR, measured against the live API
# on 2026-08-18 rather than remembered from documentation.
#
#   nova-2  uz -> 400 "No such model/language/tier combination found"
#   nova-2  pa -> 400        nova-2  so -> 400
#   nova-2  en/es/ru -> 200
#
# THREE OF SIX LAUNCH LOCALES, including the primary audience. The copilot passed the
# driver's locale straight through and 400ed on every Uzbek question — which is what
# "not working" was. M15 never hit it because the roadside officer is always English and
# it hardcodes `locale="en"`.
#
# Deepgram's fallbacks were measured too and are not good enough: nova-3 `multi` heard
# "Menga qancha qarz bor?" as "menge cancha karlsborne" (0.71), whisper-large as
# "ming yakancha qarzbo" (0.56). Azure heard "Menga qancha qarzi bor." — so the split is
# by capability, not by preference.
DEEPGRAM_LANGUAGES = frozenset({"en", "es", "ru"})


class AzureSttAdapter:
    """Speech-to-text for the languages Deepgram has no model for (uz, pa, so).

    AI-CONTEXT: IT TAKES BROWSER AUDIO UNCHANGED, and that was the open question — Azure's
    short-audio REST documents WAV-PCM and OGG-OPUS, while `MediaRecorder` in Chrome emits
    `audio/webm;codecs=opus` and iOS Safari emits mp4. Measured with genuine
    browser-recorded bytes: webm/opus, ogg/opus and wav all returned 200. So there is no
    transcoding step, and there is no ffmpeg in this image to do one with.

    The container is declared honestly in `Content-Type` rather than mislabelled — the
    Deepgram adapter's hardcoded `audio/wav` works only because Deepgram sniffs, and
    copying that habit into a second vendor is how it stops being harmless.
    """

    name = "azure_stt"
    LOCALES = {
        "uz": "uz-UZ",
        "pa": "pa-IN",
        "so": "so-SO",
        "en": "en-US",
        "es": "es-US",
        "ru": "ru-RU",
        "tg": "tg-TJ",
    }

    def __init__(self) -> None:
        settings = get_settings()
        if not (settings.azure_speech_key and settings.azure_speech_region):
            raise SpeechUnavailable(
                "AZURE_SPEECH_KEY/REGION are not set: this deployment cannot transcribe "
                "the locales Deepgram has no model for. Refusing rather than degrading — "
                "recognising Uzbek speech as English produces confident nonsense, which a "
                "copilot would then act on."
            )
        self._key = settings.azure_speech_key
        self._region = settings.azure_speech_region

    def transcribe(
        self, audio: bytes, *, locale: str, content_type: str = "audio/webm; codecs=opus"
    ) -> tuple[str, float]:
        language = self.LOCALES.get((locale or "").split("-")[0], "en-US")
        resp = _http().post(
            f"https://{self._region}.stt.speech.microsoft.com"
            f"/speech/recognition/conversation/cognitiveservices/v1",
            params={"language": language},
            headers={
                "Ocp-Apim-Subscription-Key": self._key,
                "Content-Type": content_type,
            },
            content=audio,
        )
        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("RecognitionStatus")
        if status == "NoMatch":
            # heard audio, resolved nothing — an empty transcript at zero confidence,
            # which the caller's floor already treats as "say that again"
            return "", 0.0
        if status != "Success":
            raise SpeechUnavailable(f"Azure STT returned {status!r}: {payload!r}")
        # AI-CONTEXT: THE SHORT-AUDIO REST API RETURNS NO CONFIDENCE at all — `DisplayText`
        # and nothing to floor it with. Reporting a made-up number would defeat the floor
        # that exists to stop the copilot acting on a guess, so a successful recognition
        # reports 1.0 and the honesty lives in `RecognitionStatus`: Azure says Success or
        # it says NoMatch. This is a REAL difference in guarantee from Deepgram and is the
        # reason it is written down rather than smoothed over.
        return payload.get("DisplayText", ""), 1.0


def stt_configured() -> bool:
    return bool(get_settings().deepgram_api_key)


def tts_configured() -> bool:
    settings = get_settings()
    return bool(settings.azure_speech_key and settings.azure_speech_region)


def resolve_stt(locale: str = "en") -> SttAdapter:
    """The adapter that can hear THIS language, or a refusal. NEVER a Fake.

    AI-CONTEXT: the locale argument defaults to English so every existing caller keeps its
    behaviour — M15 transcribes a US officer's stop and passes nothing. Only callers that
    serve a driver in their own language need to say which one, and those are exactly the
    ones Deepgram cannot always serve.
    """
    base = (locale or "en").split("-")[0]
    if base in DEEPGRAM_LANGUAGES:
        return DeepgramSttAdapter()
    return AzureSttAdapter()


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
