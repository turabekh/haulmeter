"""AI-CONTEXT: Public interface for F9 AI Gateway.

The ONLY import surface other packages may use to reach F9 (import-linter
enforced). Single wrapper for ALL model calls — no module calls a model API
directly. Prompt/version registry, per-module cost budgets, embeddings, and
structured-output enforcement. Consumed by M2, M3, M4, M5, M8, M9, M11, M12.
"""

from .domain.enums import AiTask
from .domain.models import AiCall, Embedding, ModuleBudget, Prompt, PromptFixture
from .domain.provider import (
    EMBED_DIM,
    CompletionResult,
    EmbeddingResult,
    FakeModelProvider,
    ModelProvider,
    StructuredResult,
    StubModelProvider,
    deterministic_vector,
)
from .domain.service import (
    BudgetExceeded,
    PromptNotFound,
    StructuredOutputError,
    add_fixture,
    budget_remaining,
    budget_used,
    complete,
    embed_and_store,
    get_active_prompt,
    list_fixtures,
    parse_structured,
    register_prompt,
    search_similar,
    set_module_budget,
    synthesize,
    transcribe,
)

__all__ = [
    "AiTask",
    "AiCall",
    "Embedding",
    "ModuleBudget",
    "Prompt",
    "PromptFixture",
    "EMBED_DIM",
    "CompletionResult",
    "EmbeddingResult",
    "StructuredResult",
    "ModelProvider",
    "FakeModelProvider",
    "StubModelProvider",
    "deterministic_vector",
    "BudgetExceeded",
    "PromptNotFound",
    "StructuredOutputError",
    "add_fixture",
    "budget_remaining",
    "budget_used",
    "complete",
    "embed_and_store",
    "get_active_prompt",
    "list_fixtures",
    "parse_structured",
    "register_prompt",
    "search_similar",
    "set_module_budget",
    "synthesize",
    "transcribe",
]
