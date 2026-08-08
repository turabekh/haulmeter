from datetime import UTC, datetime

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
# AI-CONTEXT: the cap that had never governed a call (audit F-17), on a period that had
# never been written down (F-18). The two had to be fixed together: seeding budgets while
# `budget_used` still summed every call ever made would have turned an inert guard into a
# time bomb — each module going permanently dark the first time it crossed its lifetime
# number, on a box with no monitoring, looking exactly like a broken feature.
#
# Micros are millionths of a US dollar: COST_PER_INPUT/OUTPUT_TOKEN_MICROS are 3 and 15,
# which is $3 and $15 per million tokens. So the default below is $25 per module per
# calendar month — roughly 3,300 lumper-receipt extractions, generous enough that a real
# driver in testing is never cut off, small enough that a runaway loop stops at the price
# of a dinner rather than a mortgage payment. It is an F13 config key, so a box can be
# retuned from the admin console without a deploy.
DEFAULT_MONTHLY_BUDGET_MICROS = 25_000_000
CONFIG_MONTHLY_BUDGET = "f09_default_monthly_budget_micros"


def period_start(now: datetime) -> datetime:
    """The first instant of `now`'s calendar month, UTC.

    Calendar month rather than a rolling 30 days, because a cost control is read against
    an invoice and invoices are monthly. A rolling window would put the reset on a
    different day for every module.
    """
    at = now if now.tzinfo else now.replace(tzinfo=UTC)
    at = at.astimezone(UTC)
    return at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def set_module_budget(db: Session, module: str, monthly_budget_micros: int) -> ModuleBudget:
    budget = db.get(ModuleBudget, module)
    if budget is None:
        budget = ModuleBudget(module=module, monthly_budget_micros=monthly_budget_micros)
        db.add(budget)
    else:
        budget.monthly_budget_micros = monthly_budget_micros
    db.flush()
    return budget


def budget_used(db: Session, module: str, now: datetime | None = None) -> int:
    """Spend THIS calendar month. It was every call ever made (F-18)."""
    since = period_start(now or datetime.now(UTC))
    return db.scalar(
        select(func.coalesce(func.sum(AiCall.cost_micros), 0)).where(
            AiCall.module == module, AiCall.created_at >= since
        )
    )


def budget_micros(db: Session, module: str) -> int:
    """The cap in force for `module` — its own row, or the compiled default.

    AI-CONTEXT: there is NO state in which spend is uncapped, and that is the fix for
    F-17. `_check_budget` used to return silently when no `ModuleBudget` row existed,
    and nothing in the product ever wrote one, so the guard's own precondition was
    something that never happened and the safest-looking branch was the one that spent
    money.

    Refusing an unbudgeted module was the other obvious answer and it is worse. Boot
    registration in `main.py` only WARNS if it fails, so one bad startup would take every
    AI feature in the product dark on a box with no monitoring — turning a missing
    configuration row into an outage. Falling back to the default means a cap always
    applies; seeding rows at boot is then about making the number VISIBLE and editable in
    the admin console, not about whether a limit exists at all.
    """
    row = db.get(ModuleBudget, module)
    return row.monthly_budget_micros if row is not None else DEFAULT_MONTHLY_BUDGET_MICROS


def budget_remaining(db: Session, module: str, now: datetime | None = None) -> int:
    return budget_micros(db, module) - budget_used(db, module, now)


def _check_budget(db: Session, module: str, now: datetime | None = None) -> None:
    if budget_used(db, module, now) >= budget_micros(db, module):
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
    schema: dict | None = None,
) -> dict:
    """AI-CONTEXT: `schema` turns structured output from a request into a guarantee.

    Without one, the provider asks the model to return only JSON and then hunts for
    braces in the reply — which works until it doesn't, on a document someone is about
    to build a money claim from. Every caller should bring a schema; the schema-less
    path stays for providers that cannot constrain output at all.

    Note what `required_keys` does and does not do: it checks a key is PRESENT, not
    that it holds a value. A model that answers every field with null passes this gate,
    so a caller who needs "did we actually read anything" has to ask that itself.
    """
    prompt = get_active_prompt(db, prompt_key)
    if prompt is None:
        raise PromptNotFound(prompt_key)
    _check_budget(db, module)
    if schema is not None:
        context = {**context, "json_schema": schema}
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
