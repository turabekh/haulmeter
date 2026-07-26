import uuid

import pytest

from app.foundation.f09_ai_gateway import public as ai


def test_prompt_registry_returns_latest_active_version(db):
    ai.register_prompt(db, "rate_con_parse", ai.AiTask.document_parse, "parse v1", version=1)
    ai.register_prompt(db, "rate_con_parse", ai.AiTask.document_parse, "parse v2", version=2)
    active = ai.get_active_prompt(db, "rate_con_parse")
    assert active.version == 2


def test_evaluation_fixtures(db):
    ai.register_prompt(db, "classify_facility", ai.AiTask.classify, "classify {name}")
    ai.add_fixture(db, "classify_facility", {"name": "Loves"}, {"type": "truck_stop"})
    ai.add_fixture(db, "classify_facility", {"name": "Dock 7"}, {"type": "shipper_receiver"})
    assert len(ai.list_fixtures(db, "classify_facility")) == 2


def test_completion_records_cost(db):
    ai.register_prompt(db, "draft_notice", ai.AiTask.drafting, "Draft to {broker}")
    provider = ai.FakeModelProvider()
    text = ai.complete(db, provider, "m03", "draft_notice", {"broker": "Acme"})
    assert text.startswith("[draft]")
    assert ai.budget_used(db, "m03") > 0


def test_missing_prompt_raises(db):
    provider = ai.FakeModelProvider()
    with pytest.raises(ai.PromptNotFound):
        ai.complete(db, provider, "m03", "nonexistent", {})


def test_per_module_budget_enforced(db):
    ai.register_prompt(db, "draft", ai.AiTask.drafting, "draft {x}")
    provider = ai.FakeModelProvider()
    ai.set_module_budget(db, "m03", budget_micros=1)  # effectively one call then blocked
    ai.complete(db, provider, "m03", "draft", {"x": "one"})
    assert ai.budget_used(db, "m03") >= 1
    with pytest.raises(ai.BudgetExceeded):
        ai.complete(db, provider, "m03", "draft", {"x": "two"})


def test_budget_isolated_per_module(db):
    ai.register_prompt(db, "draft", ai.AiTask.drafting, "draft {x}")
    provider = ai.FakeModelProvider()
    ai.set_module_budget(db, "m03", budget_micros=1)
    ai.complete(db, provider, "m03", "draft", {"x": "one"})
    with pytest.raises(ai.BudgetExceeded):
        ai.complete(db, provider, "m03", "draft", {"x": "two"})
    # a different module with no budget is unaffected
    assert ai.complete(db, provider, "m04", "draft", {"x": "ok"}).startswith("[draft]")


def test_structured_output_enforced(db):
    ai.register_prompt(db, "rate_con", ai.AiTask.document_parse, "parse {doc}")
    good = ai.FakeModelProvider(structured_output={"rate_cents": 250000, "free_time_minutes": 120})
    parsed = ai.parse_structured(
        db, good, "m03", "rate_con", {"doc": "..."}, required_keys=["rate_cents"]
    )
    assert parsed["rate_cents"] == 250000

    bad = ai.FakeModelProvider(structured_output={"free_time_minutes": 120})
    with pytest.raises(ai.StructuredOutputError):
        ai.parse_structured(
            db, bad, "m03", "rate_con", {"doc": "..."}, required_keys=["rate_cents"]
        )


def test_embeddings_stored_and_similarity_search(db):
    provider = ai.FakeModelProvider()
    fac_a = uuid.uuid4()
    fac_b = uuid.uuid4()
    ai.embed_and_store(
        db,
        provider,
        "m02",
        "facility_review",
        fac_a,
        "receiver unloads overnight, quick turnaround",
    )
    ai.embed_and_store(
        db,
        provider,
        "m02",
        "facility_review",
        fac_b,
        "slow dock, long detention",
    )
    results = ai.search_similar(
        db,
        provider,
        "m02",
        "facility_review",
        "receiver unloads overnight, quick turnaround",
        limit=2,
    )
    assert len(results) == 2
    # the exact-text match is the nearest (smallest cosine distance)
    assert results[0][0].owner_ref == fac_a
    assert results[0][1] <= results[1][1]


def test_stt_tts_through_gateway(db):
    provider = ai.FakeModelProvider()
    transcript = ai.transcribe(db, provider, "m11", "audio://clip1", locale="es")
    assert "transcript" in transcript
    audio = ai.synthesize(db, provider, "m11", "meter check", locale="uz")
    assert audio.startswith("audio://uz/")
    assert ai.budget_used(db, "m11") > 0


def test_stub_provider_is_a_seam(db):
    stub = ai.StubModelProvider()
    with pytest.raises(NotImplementedError):
        stub.complete("x", {})


# --- Real Anthropic adapter (F9 activation) ---
def test_resolve_provider_falls_back_to_fake_without_key():
    # no ANTHROPIC_API_KEY in the test env -> deterministic Fake (today's behavior)
    provider = ai.resolve_provider()
    assert isinstance(provider, ai.FakeModelProvider)


def test_anthropic_provider_complete_and_structured(monkeypatch):
    from app.foundation.f09_ai_gateway.domain import provider as prov

    calls = []

    def fake_messages(
        api_key, model, system, user, max_tokens=8192, document=None, schema=None, effort=None
    ):
        calls.append(
            {
                "model": model,
                "system": system,
                "user": user,
                "document": document,
                "schema": schema,
                "effort": effort,
            }
        )
        if system:  # parse_structured asks for JSON
            return '```json\n{"lines": [{"kind": "detention", "amount_cents": 15000}]}\n```', 40, 12
        return "Per our rate confirmation, $150 detention is owed.", 30, 18

    monkeypatch.setattr(prov, "_anthropic_messages", fake_messages)

    p = prov.AnthropicModelProvider("sk-test", "claude-haiku-4-5-20251001")

    completion = p.complete("Draft a notice.", {})
    assert completion.text == "Per our rate confirmation, $150 detention is owed."
    assert (completion.input_tokens, completion.output_tokens) == (30, 18)

    structured = p.parse_structured("Extract the pay lines.", {})
    assert structured.data == {
        "lines": [{"kind": "detention", "amount_cents": 15000}]
    }  # fence stripped
    assert calls[-1]["model"] == "claude-haiku-4-5-20251001"
    assert calls[-1]["document"] is None  # a text-only parse attaches nothing

    # AI-CONTEXT: a caller that puts the DOCUMENT in the context gets it attached.
    # Without this, document_parse could only ever describe a document in words — which
    # is how the rate-con import first shipped a SHA-256 hash to the model and got back
    # a form of nulls the screen then called "read from your rate con".
    p.parse_structured("Read it.", {"document_b64": "aGk=", "document_media_type": "image/png"})
    assert calls[-1]["document"] == ("image/png", "aGk=")

    # AI-CONTEXT: a schema makes structured output a GUARANTEE rather than a request.
    # Without one the provider asks for JSON and then hunts for braces in the reply —
    # a parser that works until it doesn't, on a document a money claim is built from.
    schema = {"type": "object", "additionalProperties": False,
              "required": ["amount_cents"], "properties": {"amount_cents": {"type": "integer"}}}
    p.parse_structured("Extract.", {"json_schema": schema})
    assert calls[-1]["schema"] == schema
    # and the plea not to wrap it in prose is dropped: asking for what the format
    # already guarantees only gives the model a second, weaker instruction to weigh
    assert calls[-1]["system"] is None
    assert calls[-1]["effort"] == "low"  # extraction is where low effort belongs

    # embeddings/STT/TTS have no Anthropic API -> deterministic fallback, not a crash
    assert len(p.embed("hello").vector) == ai.EMBED_DIM
    assert p.synthesize("hi", "en").startswith("audio://")


def test_extract_json_tolerates_prose_and_returns_empty_on_garbage():
    from app.foundation.f09_ai_gateway.domain.provider import _extract_json

    assert _extract_json('Here you go: {"a": 1} — hope that helps') == {"a": 1}
    assert _extract_json("no json here") == {}  # -> service raises StructuredOutputError


# --- Real Voyage embeddings adapter (F9 embeddings activation) ---
def test_fake_embedding_is_the_platform_dimension():
    # the Fake produces EMBED_DIM-wide vectors so search works without a key,
    # and the DB column (migration 0026) matches.
    assert len(ai.FakeModelProvider().embed("dock notes").vector) == ai.EMBED_DIM
    assert ai.EMBED_DIM == 1024


def test_voyage_provider_maps_embedding_response(monkeypatch):
    from app.foundation.f09_ai_gateway.domain import provider as prov

    captured = {}

    def fake_voyage(api_key, model, text, dim):
        captured.update(api_key=api_key, model=model, dim=dim)
        return [0.1] * dim, 7

    monkeypatch.setattr(prov, "_voyage_embed", fake_voyage)
    result = prov.VoyageEmbeddingProvider("pa-test", "voyage-3.5").embed("quick turnaround")
    assert len(result.vector) == ai.EMBED_DIM
    assert result.input_tokens == 7
    assert captured == {"api_key": "pa-test", "model": "voyage-3.5", "dim": ai.EMBED_DIM}


def test_voyage_provider_delegates_text_to_fallback():
    # Voyage does embeddings only; complete/parse/transcribe/synthesize still work
    p = ai.VoyageEmbeddingProvider("pa-test", "voyage-3.5")
    assert p.complete("draft this", {}).text
    assert p.transcribe("audio://x", "en")
    assert p.synthesize("hi", "en").startswith("audio://")


def test_voyage_embed_retries_on_429_then_succeeds(monkeypatch):
    import time as _time

    import httpx

    from app.foundation.f09_ai_gateway.domain import provider as prov

    calls = {"n": 0}

    class _Resp:
        def __init__(self, status):
            self.status_code = status

        def json(self):
            return {"data": [{"embedding": [0.0] * prov.EMBED_DIM}], "usage": {"total_tokens": 5}}

        def raise_for_status(self):
            if self.status_code != 200:
                raise httpx.HTTPStatusError("err", request=None, response=None)

    def fake_post(url, **kw):
        calls["n"] += 1
        return _Resp(429 if calls["n"] < 3 else 200)  # rate-limited twice, then OK

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(_time, "sleep", lambda _s: None)  # no real backoff wait in tests
    vector, tokens = prov._voyage_embed("k", "voyage-3.5", "hi", prov.EMBED_DIM)
    assert len(vector) == prov.EMBED_DIM and tokens == 5 and calls["n"] == 3


def test_voyage_embed_raises_after_exhausting_retries(monkeypatch):
    import time as _time

    import httpx

    from app.foundation.f09_ai_gateway.domain import provider as prov

    calls = {"n": 0}

    class _Resp:
        status_code = 429

        def raise_for_status(self):
            raise httpx.HTTPStatusError("429", request=None, response=None)

    def fake_post(url, **kw):
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(_time, "sleep", lambda _s: None)
    with pytest.raises(httpx.HTTPStatusError):
        prov._voyage_embed("k", "voyage-3.5", "hi", prov.EMBED_DIM)
    assert calls["n"] == prov._EMBED_MAX_TRIES  # tried the bounded max, then raised


def test_resolve_provider_uses_voyage_for_embeddings(monkeypatch):
    from app.core.config import get_settings
    from app.foundation.f09_ai_gateway.domain import provider as prov

    get_settings.cache_clear()
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        resolved = prov.resolve_provider()
        assert isinstance(resolved, prov.VoyageEmbeddingProvider)
    finally:
        get_settings.cache_clear()


def test_resolve_provider_composes_anthropic_text_with_voyage_embed(monkeypatch):
    from app.core.config import get_settings
    from app.foundation.f09_ai_gateway.domain import provider as prov

    get_settings.cache_clear()
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    try:
        resolved = prov.resolve_provider()
        # Anthropic handles text; its embed fallback is the live Voyage provider
        assert isinstance(resolved, prov.AnthropicModelProvider)
        assert isinstance(resolved._fallback, prov.VoyageEmbeddingProvider)
    finally:
        get_settings.cache_clear()


def test_a_schema_stops_the_parser_salvaging_a_fragment(monkeypatch):
    """The brace-hunting path can SUCCEED on the wrong thing — quietly returning a
    fragment of a longer answer as though it were the whole. When the format was
    guaranteed and the text still will not parse, that is a fact worth surfacing."""
    from app.foundation.f09_ai_gateway.domain import provider as prov

    prose = 'Sure! Here are the lines: {"amount_cents": 1500} — let me know if that helps.'
    monkeypatch.setattr(prov, "_anthropic_messages", lambda *a, **k: (prose, 1, 1))
    p = prov.AnthropicModelProvider("sk-test", "claude-opus-5")

    # schema-less: scavenging is all we have, so the fragment is taken
    assert p.parse_structured("x", {}).data == {"amount_cents": 1500}

    # with a schema, prose means something went wrong -> empty, and the service's
    # required-keys check turns that into StructuredOutputError
    schema = {"type": "object", "additionalProperties": False, "required": [], "properties": {}}
    assert p.parse_structured("x", {"json_schema": schema}).data == {}


def test_the_model_id_carries_no_date_suffix():
    """A dated snapshot id is the shape that silently 404s when the snapshot retires;
    the alias is the complete string."""
    from app.core.config import get_settings

    model = get_settings().f9_model
    assert model == "claude-opus-5"
    assert not model[-9:].lstrip("-").isdigit()
