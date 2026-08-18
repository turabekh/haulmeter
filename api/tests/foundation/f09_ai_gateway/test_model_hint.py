"""AI-CONTEXT: `Prompt.model_hint` reaching the REQUEST, not just the cost row.

The column existed from the start and the service passed it to `_record_call` alone — so a
hint did not merely fail to take effect, it made `AiCall` report a model that never ran.
The bug was invisible because every caller left it null and the deployment default happened
to be right for all of them.

It stopped being right when the roadside officer needed the fast model to sound like a
conversation while the rate-con extractor and the scoring rubric must stay on the bigger
one — one reads a contract a driver builds a money claim from, the other decides what a
driver is told about their English.
"""

import httpx
import pytest

from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f09_ai_gateway.domain import provider as prov


class _Resp:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "content": [{"type": "text", "text": '{"ok": true}'}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }


@pytest.fixture
def sent(monkeypatch):
    captured = {}

    def _post(url, headers=None, json=None, timeout=None):
        captured.clear()
        captured.update(json)
        return _Resp()

    monkeypatch.setattr(httpx, "post", _post)
    return captured


def test_a_prompt_with_a_hint_is_answered_by_the_model_it_names(db, sent):
    ai.register_prompt(
        db, "probe_hinted", ai.AiTask.drafting, "say something", model_hint="claude-haiku-4-5"
    )
    db.flush()
    ai.parse_structured(
        db,
        prov.AnthropicModelProvider("k", "claude-opus-5"),
        "m15",
        "probe_hinted",
        {},
        required_keys=["ok"],
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    )
    assert sent["model"] == "claude-haiku-4-5"


def test_a_prompt_without_a_hint_still_uses_the_deployment_model(db, sent):
    ai.register_prompt(db, "probe_plain", ai.AiTask.drafting, "say something")
    db.flush()
    ai.parse_structured(
        db,
        prov.AnthropicModelProvider("k", "claude-opus-5"),
        "m15",
        "probe_plain",
        {},
        required_keys=["ok"],
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    )
    assert sent["model"] == "claude-opus-5"


def test_effort_is_withheld_from_the_model_that_rejects_it(sent):
    """RED-FIRST, and it is a 400 rather than a soft failure.

    AI-CONTEXT: `parse_structured` sends `effort=low` whenever a schema is present, and
    Haiku 4.5 rejects `output_config.effort` outright. Pointing the officer at the fast
    model would have turned every improvised line into a 400 — which the caller catches as
    `OfficerUnavailable` and degrades to the scripted loop, so the symptom would have been
    "the fast officer is oddly robotic" rather than an error anyone could see.
    """
    provider = prov.AnthropicModelProvider("k", "claude-opus-5")
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    provider.parse_structured("x", {"json_schema": schema, "model": "claude-haiku-4-5"})
    assert "effort" not in sent["output_config"]
    assert sent["output_config"]["format"]["schema"] == schema

    provider.parse_structured("x", {"json_schema": schema})
    assert sent["output_config"]["effort"] == "low"
