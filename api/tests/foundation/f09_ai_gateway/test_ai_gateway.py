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

    def fake_messages(api_key, model, system, user, max_tokens=1024):
        calls.append({"model": model, "system": system, "user": user})
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
