# HANDOFF-057 — F9 real Claude provider (AI gateway activation, key-gated)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, M1 map on Mapbox, F9 real-provider adapter wired (key-gated), full authz posture, admin console complete, three F13-config knobs live. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–056.

---

## 1. What now exists and passes (delta since HANDOFF-056)

The **F9 AI gateway can now run on a real Claude model** (owner chose "turn on real AI"). Adapter + factory are wired **key-gated** (like Mapbox): with `ANTHROPIC_API_KEY` set it uses live Claude; without it, the deterministic `FakeModelProvider` (today's canned output). **Owner still needs to drop in a key** (see §6) to light it up.

### Backend
- **`AnthropicModelProvider`** (`f09_ai_gateway/domain/provider.py`): real **`complete`** and **`parse_structured`** via the Anthropic **Messages API** (called through `httpx` — no new dependency, no image rebuild). `parse_structured` asks for a strict JSON object and parses it (fence/prose tolerant; unparseable → `{}` so the service's `required_keys` check raises `StructuredOutputError`). **`embed`/`transcribe`/`synthesize` delegate to a deterministic fallback** — Anthropic has no embeddings/STT/TTS API, so those stay separate provider seams (M2 semantic search + M11 voice audio remain placeholder; M11's text reply and M4/M9 doc extraction go real).
- **`resolve_provider()`**: returns `AnthropicModelProvider(key, model)` when `settings.anthropic_api_key` is set, else `FakeModelProvider`. Reads `app.core.config` (foundation→core, import-linter clean).
- **`app/core/config.py`**: `anthropic_api_key` (default `""`) + `f9_model` (default `claude-haiku-4-5-20251001`). The api service already loads `infra/.env` via `env_file`, so a key in `.env` reaches Settings with **no compose change**.
- **Wiring**: `app/api/m02_facility_intel.py`, `m04_accessorial.py`, `m11_voice.py` now use `ai.resolve_provider()` instead of a hardcoded `FakeModelProvider()`. (M9's doc-parser isn't wired to an endpoint yet — dormant.)

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 312 passed** (was 309; +3: `resolve_provider` → Fake without a key; `AnthropicModelProvider.complete`/`parse_structured` shape a mocked Messages response and delegate embed/STT/TTS to the fallback; `_extract_json` tolerates prose and returns `{}` on garbage). No real network calls in tests (the Messages call is a monkeypatchable module function).
- **Not yet live-smoked against the real API** — needs the owner's key (§6). With no key, the app runs exactly as before (Fake).

## 2. Decisions made (append to Decision Log)

188. **F9 real provider = Anthropic Messages API via httpx, key-gated, defaulting to the Fake without a key.** Same activation shape as Mapbox: a real adapter behind the existing `ModelProvider` Protocol, chosen by `resolve_provider()` from env. Using `httpx` directly (already installed) avoids adding the `anthropic` SDK and an image rebuild. Default model `claude-haiku-4-5-20251001` (cheap/fast for a high-volume gateway) — override via `F9_MODEL` (e.g. `claude-sonnet-5` for higher-stakes extraction).
189. **Only text intelligence is activated; embeddings and voice audio stay placeholder.** Anthropic serves `complete` + `parse_structured` (M11 ghostwriter/text, M4/M9 doc extraction). It has no embeddings (M2 semantic search) or STT/TTS (M11 voice audio), so those delegate to the deterministic fallback rather than break. They are their own future seams (e.g. Voyage embeddings, a speech provider) — an honest partial activation, not a fake-complete one.

## 3. Exact next task — continue the backlog

- **Owner: add the Anthropic key** (§6) → then live-smoke M11 ghostwriter / M4 extraction for a real reply, and confirm F9 budget accounting records real token counts.
- **Embeddings + voice seams** (separate activations): Voyage/OpenAI embeddings for M2 semantic search (needs a migration to the real `EMBED_DIM` + a pgvector ANN index); a speech provider for M11 STT/TTS.
- **Other activation seams**: Stripe/Connect (M6), fuel partner (M7), collections+legal (M3/M4), IFTA (M9), brand name.

**Recommendation:** owner drops the key; I live-smoke and tune the model/prompts. Then pick the next seam (Stripe or brand name) or the embeddings activation.

## 4. Blockers / owner questions

**F9 needs the owner's Anthropic API key** (§6) to go live; until then it runs on the Fake. Other **activation inputs**: Stripe/Connect · fuel partner (M7) · collections+legal (M3/M4) · IFTA (M9) · brand name · F15 locale review. **Mapbox: DONE.**

## 5. Port / env changes

**`infra/.env`**: add `ANTHROPIC_API_KEY` (+ optional `F9_MODEL`). **`infra/.env.example`**: placeholders added. No compose/port change (api already loads `.env`). Restart the api container after adding the key.

## 6. How to run (all Docker) — stack is UP

**Activate real AI (owner, ~2 min):**
1. Create an API key at **console.anthropic.com** → API keys (starts with `sk-ant-`).
2. Add to **`infra/.env`** (gitignored): `ANTHROPIC_API_KEY=sk-ant-…` (optionally `F9_MODEL=claude-sonnet-5` for higher quality).
3. Restart the API: `docker compose -f infra/docker-compose.yml restart api`.
4. Tell me — I'll live-smoke a real completion (M11 ghostwriter) and confirm token/budget accounting.

Without a key, everything runs as before (Fake). Suite: **pytest 312 · vitest 101 · 29 contracts · ruff clean**.

## 7. Build progress

**F1–F15 + M1–M12 complete; M1 on Mapbox; F9 real-provider adapter wired (key-gated); full authz posture; admin console complete; M6 self-serve; three F13-config knobs live.** Recent: F9 real provider (057), map GPS+style (056), Mapbox tiles (055), moderation in audit (054), scorecard snippets (053), M3 terms config (052), gate /dev (051), fleet gate (050), M3/M5 authz (049), load authz (048), end-load (047), /load/active (046) … (M1–M12 complete at 025). Remaining: activation inputs §4.

## 8. Commits this session (local only, never pushed)

`ac5ddab` map GPS+style → this: F9 real Claude provider (+ this handoff). **122 commits** on `main`, never pushed.

*— End of session. F9 adapter wired + tested; awaiting the owner's Anthropic key to go live. Then embeddings/voice seams or the next activation seam.*
