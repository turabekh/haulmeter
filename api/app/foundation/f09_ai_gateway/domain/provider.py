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
