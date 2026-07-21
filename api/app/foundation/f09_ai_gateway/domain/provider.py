"""AI-CONTEXT: Model-provider adapter seam for F9 (PRD §7.9).

Every LLM/STT/TTS/embedding call in the whole platform goes through this
protocol — no module ever calls a model API directly. The gateway logic
(prompt registry, cost/budget accounting, structured-output enforcement,
similarity search) is real and fully tested against FakeModelProvider, which is
deterministic (no randomness). The real adapter targets the latest Claude
models; when wiring it, consult the `claude-api` skill for current model ids and
params rather than hardcoding — StubModelProvider fails loudly until then.
"""

import hashlib
from dataclasses import dataclass
from typing import Protocol

# AI-CONTEXT: placeholder dimension; the real embedding model's dimension is
# set at F9 activation (a migration + a pgvector ANN index at that point).
EMBED_DIM = 16


@dataclass
class CompletionResult:
    text: str
    input_tokens: int
    output_tokens: int


@dataclass
class StructuredResult:
    data: dict
    input_tokens: int
    output_tokens: int


@dataclass
class EmbeddingResult:
    vector: list[float]
    input_tokens: int


class ModelProvider(Protocol):
    def complete(self, prompt: str, context: dict) -> CompletionResult: ...

    def parse_structured(self, prompt: str, context: dict) -> StructuredResult: ...

    def embed(self, text: str) -> EmbeddingResult: ...

    def transcribe(self, audio_ref: str, locale: str) -> str: ...

    def synthesize(self, text: str, locale: str) -> str: ...


def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


def deterministic_vector(text: str, dim: int = EMBED_DIM) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    values: list[float] = []
    i = 0
    while len(values) < dim:
        byte = digest[i % len(digest)]
        values.append(((byte + i) % 256) / 255.0)
        i += 1
    return values


class FakeModelProvider:
    """Deterministic test double. `structured_output` lets a test control the
    parsed result so structured-output enforcement can be exercised both ways."""

    def __init__(self, structured_output: dict | None = None) -> None:
        self._structured = structured_output or {}

    def complete(self, prompt: str, context: dict) -> CompletionResult:
        text = f"[draft] {prompt}"
        return CompletionResult(text, _tokens(prompt), _tokens(text))

    def parse_structured(self, prompt: str, context: dict) -> StructuredResult:
        return StructuredResult(dict(self._structured), _tokens(prompt), len(self._structured))

    def embed(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(deterministic_vector(text), _tokens(text))

    def transcribe(self, audio_ref: str, locale: str) -> str:
        return f"[{locale}] transcript of {audio_ref}"

    def synthesize(self, text: str, locale: str) -> str:
        return f"audio://{locale}/{hashlib.sha256(text.encode()).hexdigest()[:12]}"


class StubModelProvider:
    def complete(self, prompt: str, context: dict) -> CompletionResult:
        raise NotImplementedError("model provider adapter is a seam; wired at activation")

    def parse_structured(self, prompt: str, context: dict) -> StructuredResult:
        raise NotImplementedError("model provider adapter is a seam; wired at activation")

    def embed(self, text: str) -> EmbeddingResult:
        raise NotImplementedError("model provider adapter is a seam; wired at activation")

    def transcribe(self, audio_ref: str, locale: str) -> str:
        raise NotImplementedError("STT adapter is a seam; wired at activation")

    def synthesize(self, text: str, locale: str) -> str:
        raise NotImplementedError("TTS adapter is a seam; wired at activation")


# --- Real adapter: Anthropic Messages API (the F9 activation) ---
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


def _anthropic_messages(
    api_key: str, model: str, system: str | None, user: str, max_tokens: int = 1024
) -> tuple[str, int, int]:
    # single HTTP call to the Messages API; kept as a module function so tests can
    # monkeypatch it without hitting the network. Returns (text, in_tok, out_tok).
    import httpx

    body: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user}],
    }
    if system:
        body["system"] = system
    resp = httpx.post(
        _ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        json=body,
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    usage = data.get("usage", {})
    return text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))


def _extract_json(text: str) -> dict:
    import json

    s = text.strip()
    if s.startswith("```"):  # tolerate a ```json fence
        s = s.strip("`")
    start, end = s.find("{"), s.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(s[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            pass
    return {}  # unparseable -> service's required_keys check raises StructuredOutputError


class AnthropicModelProvider:
    """Live Claude adapter. Real `complete` + `parse_structured` (text intelligence);
    `embed`/`transcribe`/`synthesize` delegate to a deterministic fallback because
    Anthropic has no embeddings/STT/TTS API — those stay separate provider seams."""

    def __init__(
        self, api_key: str, model: str, fallback: "FakeModelProvider | None" = None
    ) -> None:
        self._key = api_key
        self._model = model
        self._fallback = fallback or FakeModelProvider()

    def complete(self, prompt: str, context: dict) -> CompletionResult:
        text, i, o = _anthropic_messages(self._key, self._model, None, prompt)
        return CompletionResult(text, i, o)

    def parse_structured(self, prompt: str, context: dict) -> StructuredResult:
        system = "Return ONLY a single valid JSON object — no prose, no markdown."
        text, i, o = _anthropic_messages(self._key, self._model, system, prompt)
        return StructuredResult(_extract_json(text), i, o)

    def embed(self, text: str) -> EmbeddingResult:
        return self._fallback.embed(text)

    def transcribe(self, audio_ref: str, locale: str) -> str:
        return self._fallback.transcribe(audio_ref, locale)

    def synthesize(self, text: str, locale: str) -> str:
        return self._fallback.synthesize(text, locale)


def resolve_provider() -> ModelProvider:
    # the live provider when ANTHROPIC_API_KEY is set (F9 activated), else the
    # deterministic Fake — the same shape the app has always run on without a key.
    from app.core.config import get_settings

    settings = get_settings()
    if settings.anthropic_api_key:
        return AnthropicModelProvider(settings.anthropic_api_key, settings.f9_model)
    return FakeModelProvider()
