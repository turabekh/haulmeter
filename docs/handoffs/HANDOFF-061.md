# HANDOFF-061 — Real embeddings for M2 semantic search (activation seam #3)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 22 July 2026 · **State:** F1–F15 + M1–M12 complete. Mapbox live · F9 real Claude live · FMCSA verification live · F6 image serving live. **New this session: the embeddings seam — real (Voyage-AI) vectors for M2 semantic review search, behind a real EMBED_DIM migration + a pgvector HNSW ANN index, key-gated.** Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–060.

---

## 1. What now exists and passes (delta since HANDOFF-060)

HANDOFF-060 shipped F6 image serving and left the seam list for the owner to pick from. Owner said "use your best judgement" — I took the **embeddings seam** (the cleanest self-contained technical one: no external contract needed to prove it works, exactly the F9/FMCSA key-gated shape).

**The gap:** F9's `Embedding.vector` was `Vector(16)` — a placeholder dimension — and `search_similar` ran a brute-force `cosine_distance` order-by with no ANN index. No real embedding provider existed (Anthropic has no embeddings API; `AnthropicModelProvider.embed` delegated to the deterministic Fake). M2 embeds approved facility reviews (`embed_and_store`) and does semantic search over them (`search_reviews`).

### The embeddings adapter (F9, mirrors the Anthropic adapter)
- **`VoyageEmbeddingProvider`** (`f09/domain/provider.py`) — Voyage AI is Anthropic's recommended embeddings partner. Real `embed` via the Voyage REST API (`voyage-3.5`, `output_dimension = EMBED_DIM`, `httpx` in a monkeypatch-able `_voyage_embed`); `complete`/`parse_structured`/`transcribe`/`synthesize` delegate to a Fake fallback so it still satisfies the full `ModelProvider` protocol.
- **`resolve_provider()` now composes by capability** — Anthropic for text intelligence, Voyage for embeddings: when both keys are set it returns `AnthropicModelProvider(..., fallback=VoyageEmbeddingProvider(...))` (Anthropic's embed fallback becomes the live Voyage provider); Voyage-only, Anthropic-only, or the deterministic Fake as available. No key ⇒ Fake, the shape the app has always run on.
- **Config + env** — `voyage_api_key` + `embed_model` (default `voyage-3.5`); `.env.example` placeholder. Real key in `infra/.env` only.

### Real dimension + ANN index (the substantive infra work)
- **`EMBED_DIM` 16 → 1024** (voyage-3.5's default width). The Fake's `deterministic_vector` produces 1024-dim vectors, so search works identically with or without a key.
- **Migration 0026** — embeddings are a **regenerable cache** (derived from review text), so it `DELETE`s existing rows, `ALTER`s `f09.embedding.vector` to `vector(1024)`, and adds an **HNSW cosine index** (`USING hnsw (vector vector_cosine_ops)`). Rows re-embed lazily on the next `embed_and_store`/`search_similar`. Downgrade reverses. `search_similar` already orders by `cosine_distance` → the HNSW index accelerates it with no query change.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 342 passed** (was 337).
- UI: untouched — **vitest 112** / `vite build` green carry over from HANDOFF-060 (no UI in this seam).
- **Live-smoked**: migration 0026 applied; `f09.embedding.vector` is `vector(1024)` and `ix_embedding_vector_hnsw` exists; an embed→store→search round-trip on the running stack ranks the correct nearest match with 1024-wide vectors (provider = AnthropicModelProvider, embed via Fake fallback since no Voyage key yet).

## 2. Decisions made (append to Decision Log)

200. **Embeddings are a Voyage-AI seam composed into F9's provider by capability.** Anthropic handles text; Voyage handles embeddings (Anthropic has no embeddings API). `resolve_provider()` wires Voyage in as the Anthropic provider's embed fallback when `VOYAGE_API_KEY` is set — one `ModelProvider` still satisfies the whole protocol. Fake everywhere by default.
201. **The embedding table is a regenerable cache, so the dimension migration truncates rather than backfills.** Migration 0026 deletes rows and re-types the column to `vector(1024)`; rows re-embed on next use. No re-embedding job, no downtime concern — the vectors are derived from source text (reviews).
202. **`EMBED_DIM` is the platform embedding dimension (1024), fixed at the migration.** voyage-3.5's default output width; the model column and the ANN index both key off it, and Voyage is asked for exactly that dimension via `output_dimension`. No new F13 flag (completes an existing F9 capability, consistent with prior seams).

## 3. Exact next task — pick the next activation seam

Remaining seams (from HANDOFF-060 §3, minus FMCSA, F6 images, and embeddings):
- **Stripe/Connect** (M6 payouts) · **fuel partner** (M7) · **collections+legal** (M3/M4) · **IFTA** (M9).
- **Voice STT/TTS** seam (M11) — the sibling of this seam: a real speech provider behind the F9 `transcribe`/`synthesize` (currently the deterministic Fake). Same key-gated shape; the cleanest self-contained follow-on.
- **Brand name** (PRD §17.6) · **F15 locale review** by native speakers.

**Recommendation:** owner names the next seam. Stripe or brand name remain highest-leverage; **M11 voice** is the natural next self-contained technical seam now that embeddings are done.

**Embeddings follow-ons (noted, not built):** a UI entry point for M2 semantic review search (the `/facility/search` endpoint exists; no driver-facing search surface wires it yet — a design-prd §22 decision when M2 gets a search affordance); tuning `output_dimension`/model per cost once a real Voyage key is in; an M8/M11 embedding consumer beyond M2 if semantic recall is wanted elsewhere.

## 4. Blockers / owner questions

No code blockers — stack green, all suites pass. Embeddings run today on the deterministic Fake (1024-dim); to go live, drop a real `VOYAGE_API_KEY` into `infra/.env` and recreate the api container. Open activation inputs (owner decisions): Stripe/Connect · fuel partner · collections+legal · IFTA · M11 voice provider · brand name · F15 locale review.

## 5. Port / env changes

New settings **`VOYAGE_API_KEY`** (empty in `.env.example`; real value in `infra/.env` only) and **`EMBED_MODEL`** (default `voyage-3.5`). Migration **0026** (`f09.embedding` → `vector(1024)` + HNSW cosine index) applied to the dev DB. LOCKED ports unchanged (5438/8008/9008). After editing `infra/.env`, recreate api to reload env_file: `docker compose -f infra/docker-compose.yml up -d api`.

## 6. How to run (all Docker) — stack is UP

```
make up        # preflight + full stack
make ci        # preflight + lint + test (CI parity)
```
Suite: **pytest 342 · vitest 112 · 29 contracts · ruff clean · vite build OK.**
Live embeddings (optional): set `VOYAGE_API_KEY` in `infra/.env`, then `docker compose -f infra/docker-compose.yml up -d api`. Existing (Fake) embeddings re-embed with real vectors on next write — the dimension is unchanged (1024).

## 7. Build progress

**F1–F15 + M1–M12 complete; live: Mapbox · F9 Claude · FMCSA verification · F6 image serving · F9 embeddings (real EMBED_DIM 1024 + HNSW ANN index, Voyage-gated).** This session: the Voyage embeddings adapter, capability-composed `resolve_provider`, migration 0026 (re-dimension + HNSW), and the config/env plumbing. Remaining: activation inputs §3.

## 8. Commits this session (local only, never pushed)

Since `5fd3570` (F6 images): the embeddings seam (Voyage adapter + composed resolver + `EMBED_DIM` 1024 + migration 0026 HNSW ANN index + config/env + tests) → this handoff. See `git log` on `main`. Never pushed.

*— End of session. M2 semantic search now has a real embedding dimension and a scalable ANN index, live-verified; real vectors light up on a Voyage key. Next: owner names the seam (Stripe / brand name / M11 voice).*
