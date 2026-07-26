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

# AI-CONTEXT: the platform embedding dimension. voyage-3.5's default output
# dimension (also 256/512/2048-capable). The Fake produces deterministic vectors
# of this width, so search works identically with or without a Voyage key; the
# real vectors + the HNSW ANN index (migration 0026) light up at activation.
EMBED_DIM = 1024


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
    api_key: str,
    model: str,
    system: str | None,
    user: str,
    max_tokens: int = 8192,
    document: tuple[str, str] | None = None,
    schema: dict | None = None,
    effort: str | None = None,
) -> tuple[str, int, int]:
    # single HTTP call to the Messages API; kept as a module function so tests can
    # monkeypatch it without hitting the network. Returns (text, in_tok, out_tok).
    #
    # AI-CONTEXT: `document` is (media_type, base64) and is what makes document_parse
    # actually read a DOCUMENT. Without it, a caller can only describe the document in
    # words — which is how the first rate-con import shipped a SHA-256 hash to the
    # model and got back a form of nulls that the screen then called "read from your
    # rate con". A photographed contract has to travel as an image or a PDF; naming it
    # is not reading it.
    import httpx

    content: list | str = user
    if document is not None:
        media_type, data = document
        source = {"type": "base64", "media_type": media_type, "data": data}
        kind = "document" if media_type == "application/pdf" else "image"
        block = {"type": kind, "source": source}
        content = [block, {"type": "text", "text": user}]  # document first, then the ask
    body: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        body["system"] = system
    # AI-CONTEXT: `schema` is what makes structured output a GUARANTEE rather than a
    # request. Without it this asked the model to "return ONLY a single valid JSON
    # object" and then went hunting for braces in whatever came back — a parser that
    # works until the day it doesn't, on a document a driver is about to build a
    # detention claim from. `output_config.format` constrains the response itself.
    output_config: dict = {}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    if effort is not None:
        output_config["effort"] = effort
    if output_config:
        body["output_config"] = output_config
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


def _parse_json(text: str, strict: bool) -> dict:
    """AI-CONTEXT: `strict` means a schema was sent, so the response IS the object and
    `json.loads` is the whole job. The brace-hunting path below it exists only for
    schema-less callers — and the reason to keep the two apart is that scavenging for
    braces can SUCCEED on the wrong thing, quietly returning a fragment of a longer
    answer as though it were the whole. When the format was guaranteed and the text
    still will not parse, that is a fact worth surfacing, not one worth papering over.
    """
    import json

    if strict:
        try:
            parsed = json.loads(text.strip())
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}  # -> StructuredOutputError, rather than a salvaged fragment
    return _extract_json(text)


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
        # a caller that put the document itself in the context gets it ATTACHED rather
        # than described; callers that pass only text are unaffected
        data = context.get("document_b64")
        media_type = context.get("document_media_type")
        document = (media_type, data) if data and media_type else None

        schema = context.get("json_schema")
        # With a schema the response IS the object, so the plea not to wrap it in prose
        # is unnecessary — and asking for something the format already guarantees only
        # gives the model a second, weaker instruction to weigh. Without one we are
        # still asking nicely, which is why every caller should bring a schema.
        system = (
            None if schema else "Return ONLY a single valid JSON object — no prose, no markdown."
        )
        # extraction is the canonical low-effort task, and effort is the primary cost
        # lever — raise it per prompt if a document type proves too hard to read
        text, i, o = _anthropic_messages(
            self._key,
            self._model,
            system,
            prompt,
            document=document,
            schema=schema,
            effort="low" if schema else None,
        )
        return StructuredResult(_parse_json(text, strict=schema is not None), i, o)

    def embed(self, text: str) -> EmbeddingResult:
        return self._fallback.embed(text)

    def transcribe(self, audio_ref: str, locale: str) -> str:
        return self._fallback.transcribe(audio_ref, locale)

    def synthesize(self, text: str, locale: str) -> str:
        return self._fallback.synthesize(text, locale)


# --- Real embeddings adapter: Voyage AI (the F9 embeddings activation) ---
# Anthropic has no embeddings API; Voyage is its recommended embeddings partner.
_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_EMBED_MAX_TRIES = 3
_EMBED_BACKOFF_BASE = 0.5  # seconds; 0.5s, 1.0s between retries — bounded, request-safe


def _voyage_embed(api_key: str, model: str, text: str, dim: int) -> tuple[list[float], int]:
    # HTTP call to the Voyage embeddings API with bounded retry-with-backoff on 429
    # (free-tier rate limit) and 5xx. Kept as a module function so tests monkeypatch
    # it without touching the network. Returns (vector, tokens); raises on exhaustion.
    import time

    import httpx

    headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
    body = {"input": [text], "model": model, "output_dimension": dim, "input_type": "document"}
    for attempt in range(_EMBED_MAX_TRIES):
        resp = httpx.post(_VOYAGE_URL, headers=headers, json=body, timeout=60.0)
        retryable = resp.status_code == 429 or resp.status_code >= 500
        if retryable and attempt < _EMBED_MAX_TRIES - 1:
            time.sleep(_EMBED_BACKOFF_BASE * (2**attempt))
            continue
        resp.raise_for_status()  # raises on the final/non-retryable failure
        data = resp.json()
        vector = list(data["data"][0]["embedding"])
        tokens = int(data.get("usage", {}).get("total_tokens", 0)) or _tokens(text)
        return vector, tokens
    raise RuntimeError("unreachable")  # loop always returns or raises


class VoyageEmbeddingProvider:
    """Live embeddings adapter. Real `embed` via Voyage; `complete`/`parse_structured`/
    `transcribe`/`synthesize` delegate to a deterministic fallback so it still
    satisfies the full ModelProvider protocol (Voyage does embeddings only)."""

    def __init__(
        self, api_key: str, model: str, fallback: "FakeModelProvider | None" = None
    ) -> None:
        self._key = api_key
        self._model = model
        self._fallback = fallback or FakeModelProvider()

    def complete(self, prompt: str, context: dict) -> CompletionResult:
        return self._fallback.complete(prompt, context)

    def parse_structured(self, prompt: str, context: dict) -> StructuredResult:
        return self._fallback.parse_structured(prompt, context)

    def embed(self, text: str) -> EmbeddingResult:
        vector, tokens = _voyage_embed(self._key, self._model, text, EMBED_DIM)
        return EmbeddingResult(vector, tokens)

    def transcribe(self, audio_ref: str, locale: str) -> str:
        return self._fallback.transcribe(audio_ref, locale)

    def synthesize(self, text: str, locale: str) -> str:
        return self._fallback.synthesize(text, locale)


def resolve_provider() -> ModelProvider:
    # compose the live providers by capability: Anthropic for text intelligence,
    # Voyage for embeddings. Either (or both) activates when its key is set; with
    # no keys, the deterministic Fake — the shape the app has always run on.
    from app.core.config import get_settings

    settings = get_settings()
    embed_provider = (
        VoyageEmbeddingProvider(settings.voyage_api_key, settings.embed_model)
        if settings.voyage_api_key
        else None
    )
    if settings.anthropic_api_key:
        # Anthropic handles text; its fallback answers embed/STT/TTS -> Voyage when set
        return AnthropicModelProvider(
            settings.anthropic_api_key, settings.f9_model, fallback=embed_provider
        )
    if embed_provider is not None:
        return embed_provider
    return FakeModelProvider()
