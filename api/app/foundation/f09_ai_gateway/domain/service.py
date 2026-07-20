from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .enums import AiTask
from .models import AiCall, Embedding, ModuleBudget, Prompt, PromptFixture
from .provider import ModelProvider

COST_PER_INPUT_TOKEN_MICROS = 3
COST_PER_OUTPUT_TOKEN_MICROS = 15
DEFAULT_MODEL = "unset"


class PromptNotFound(Exception):
    pass


class BudgetExceeded(Exception):
    pass


class StructuredOutputError(Exception):
    pass


def _cost(input_tokens: int, output_tokens: int) -> int:
    return input_tokens * COST_PER_INPUT_TOKEN_MICROS + output_tokens * COST_PER_OUTPUT_TOKEN_MICROS


# --- Prompt registry + evaluation fixtures ---
def register_prompt(
    db: Session,
    key: str,
    task: AiTask,
    template: str,
    version: int = 1,
    model_hint: str | None = None,
    active: bool = True,
) -> Prompt:
    prompt = Prompt(
        key=key,
        task=task,
        template=template,
        version=version,
        model_hint=model_hint,
        active=active,
    )
    db.add(prompt)
    db.flush()
    return prompt


def get_active_prompt(db: Session, key: str) -> Prompt | None:
    return db.scalar(
        select(Prompt)
        .where(Prompt.key == key, Prompt.active.is_(True))
        .order_by(Prompt.version.desc())
        .limit(1)
    )


def add_fixture(db: Session, prompt_key: str, input: dict, expected: dict) -> PromptFixture:
    fixture = PromptFixture(prompt_key=prompt_key, input=input, expected=expected)
    db.add(fixture)
    db.flush()
    return fixture


def list_fixtures(db: Session, prompt_key: str) -> list[PromptFixture]:
    return list(db.scalars(select(PromptFixture).where(PromptFixture.prompt_key == prompt_key)))


# --- Cost tracking + per-module budgets ---
def set_module_budget(db: Session, module: str, budget_micros: int) -> ModuleBudget:
    budget = db.get(ModuleBudget, module)
    if budget is None:
        budget = ModuleBudget(module=module, budget_micros=budget_micros)
        db.add(budget)
    else:
        budget.budget_micros = budget_micros
    db.flush()
    return budget


def budget_used(db: Session, module: str) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(AiCall.cost_micros), 0)).where(AiCall.module == module)
    )


def budget_remaining(db: Session, module: str) -> int | None:
    budget = db.get(ModuleBudget, module)
    if budget is None:
        return None
    return budget.budget_micros - budget_used(db, module)


def _check_budget(db: Session, module: str) -> None:
    budget = db.get(ModuleBudget, module)
    if budget is not None and budget_used(db, module) >= budget.budget_micros:
        raise BudgetExceeded(module)


def _record_call(
    db: Session,
    module: str,
    task: AiTask,
    model: str,
    input_tokens: int,
    output_tokens: int,
    prompt_key: str | None = None,
    account_id=None,
) -> AiCall:
    call = AiCall(
        module=module,
        account_id=account_id,
        task=task,
        prompt_key=prompt_key,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_micros=_cost(input_tokens, output_tokens),
    )
    db.add(call)
    db.flush()
    return call


def _render(template: str, context: dict) -> str:
    for key, value in context.items():
        template = template.replace("{" + key + "}", str(value))
    return template


# --- Capabilities (all go through the provider seam) ---
def complete(
    db: Session,
    provider: ModelProvider,
    module: str,
    prompt_key: str,
    context: dict,
    account_id=None,
) -> str:
    prompt = get_active_prompt(db, prompt_key)
    if prompt is None:
        raise PromptNotFound(prompt_key)
    _check_budget(db, module)
    result = provider.complete(_render(prompt.template, context), context)
    _record_call(
        db,
        module,
        prompt.task,
        prompt.model_hint or DEFAULT_MODEL,
        result.input_tokens,
        result.output_tokens,
        prompt_key,
        account_id,
    )
    return result.text


def parse_structured(
    db: Session,
    provider: ModelProvider,
    module: str,
    prompt_key: str,
    context: dict,
    required_keys: list[str],
    account_id=None,
) -> dict:
    prompt = get_active_prompt(db, prompt_key)
    if prompt is None:
        raise PromptNotFound(prompt_key)
    _check_budget(db, module)
    result = provider.parse_structured(_render(prompt.template, context), context)
    missing = [k for k in required_keys if k not in result.data]
    if missing:
        raise StructuredOutputError(f"missing required keys: {missing}")
    _record_call(
        db,
        module,
        prompt.task,
        prompt.model_hint or DEFAULT_MODEL,
        result.input_tokens,
        result.output_tokens,
        prompt_key,
        account_id,
    )
    return result.data


def embed_and_store(
    db: Session,
    provider: ModelProvider,
    module: str,
    owner_kind: str,
    owner_ref,
    text: str,
    model: str = DEFAULT_MODEL,
) -> Embedding:
    _check_budget(db, module)
    result = provider.embed(text)
    _record_call(db, module, AiTask.embedding, model, result.input_tokens, 0)
    embedding = Embedding(
        owner_kind=owner_kind, owner_ref=owner_ref, model=model, vector=result.vector
    )
    db.add(embedding)
    db.flush()
    return embedding


def search_similar(
    db: Session,
    provider: ModelProvider,
    module: str,
    owner_kind: str,
    query_text: str,
    limit: int = 5,
) -> list[tuple[Embedding, float]]:
    _check_budget(db, module)
    result = provider.embed(query_text)
    _record_call(db, module, AiTask.embedding, DEFAULT_MODEL, result.input_tokens, 0)
    distance = Embedding.vector.cosine_distance(result.vector).label("distance")
    rows = db.execute(
        select(Embedding, distance)
        .where(Embedding.owner_kind == owner_kind)
        .order_by(distance)
        .limit(limit)
    ).all()
    return [(row[0], float(row[1])) for row in rows]


def transcribe(
    db: Session, provider: ModelProvider, module: str, audio_ref: str, locale: str = "en"
) -> str:
    _check_budget(db, module)
    text = provider.transcribe(audio_ref, locale)
    _record_call(db, module, AiTask.stt, DEFAULT_MODEL, 0, len(text) // 4 or 1)
    return text


def synthesize(
    db: Session, provider: ModelProvider, module: str, text: str, locale: str = "en"
) -> str:
    _check_budget(db, module)
    audio_ref = provider.synthesize(text, locale)
    _record_call(db, module, AiTask.tts, DEFAULT_MODEL, len(text) // 4 or 1, 0)
    return audio_ref
