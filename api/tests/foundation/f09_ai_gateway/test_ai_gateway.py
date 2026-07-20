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
