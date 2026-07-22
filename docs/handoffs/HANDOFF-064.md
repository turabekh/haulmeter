# HANDOFF-064 — Full project-state snapshot (Haulmeter)

**Project:** **Haulmeter** — consolidated, mobile-first platform for US truck drivers. Driver pays $0, forever.
**Date:** 22 July 2026 · **State:** **Feature-complete** — F1–F15 (Common Ground) + M1–M12 (all modules) built to DoD. Core is hardened by a real browser-testing pass; six external "activation seams" now built, four running on real providers. Stack is UP; working tree clean; **145 commits on `main`, never pushed.**
**Read order each session:** `HANDOFF.md` (Session 0) + `docs/trucker-platform-prd.md` (build law) + `docs/design-prd.md` (design law), then this file; HANDOFF-025 (M1–M12 complete), 026–063 for the detailed trail.

This is a **comprehensive snapshot** (requested) — it supersedes the incremental 058–063 handoffs as the entry point.

---

## 1. What Haulmeter is

A single app that replaces the fragmented stack of trucker point-tools: a **truck-aware live map**, **GPS-verified detention/accessorial recovery** (the wedge — get the driver the money they're owed for time stolen at docks, with a tamper-evident evidence chain), plus **parking, fuel, protection/document-wallet, community, and fleet** layers. The signature element is **The Meter** (the live detention clock → money owed). Six launch locales: en/es/pa/ru/uz/so. Dark-theme-first, mobile-first (360×800 dp).

## 2. Architecture (how it's built)

- **Backend:** FastAPI **modular monolith**. `api/app/foundation/f01…f15` + `api/app/modules/m01…m12`, **one Postgres schema per component** (schema-per-module). **import-linter** (`api/importlinter.ini`) is authoritative on boundaries: `core < foundation < modules`; a module imports `foundation.*.public` and **earlier** modules' `.public` only — no lateral imports, no reach-ins past `public.py`. **29 contracts, all KEPT.**
- **Frontend:** Quasar/Vue 3. Business logic in `ui/src/core/`; zero Quasar visual defaults; **`ui/src/core/tokens.scss` is the only source of visual truth**. Governed by `design-prd.md` (mobile-first LAW 0; every UI change passes the §22.3 DoD: mobile-first, tokens-only, six locales, offline, DRIVING-state, a11y).
- **Infra:** Docker-only (dev = CI parity). Postgres (PostGIS + pgvector), Redis, MinIO, Mailpit, api, ui, worker. Ports LOCKED & parameterized in `infra/.env` — Postgres **5438**, API **8008**, UI **9008** (never bind defaults; `scripts/check_ports.sh` preflights).
- **AI/model access:** all model calls go through the **F9 gateway** (prompt registry, per-module budgets, structured-output enforcement, embeddings, STT/TTS) — no module calls a provider directly. Provider adapters are **key-gated**: a deterministic Fake runs with no key (and in every test); real providers activate when their key is set.

## 3. Build status — feature-complete

- **Common Ground F1–F15:** complete to the Foundation DoD.
- **Modules M1–M12:** complete, each end-to-end behind its own F13 flag (M1 map, M2 facility intel, M3 detention, M4 accessorial, M5 protection/wallet, M6 parking, M7 fuel, M8 intelligence, M9 money, M10 community, M11 voice, M12 fleet).
- Full authz posture; admin console complete; M6 self-serve; three F13-config knobs live.

## 4. Activation seams — live vs. pending

External inputs that turn a deterministic seam into a real integration. **Built + running on real providers (4):**

| Seam | Status | Notes |
|---|---|---|
| **Mapbox** (M1 live map) | **LIVE** (real token) | real tiles, GPS geolocate, day/night preset |
| **F9 Claude** (M4/M9/M11 text intelligence) | **LIVE** (real key) | `AnthropicModelProvider`; model `claude-haiku-4-5` |
| **F6 image serving** (evidence photo thumbnails) | **LIVE** (MinIO) | no external key; bytes persist + serve, owner-gated |
| **F9 embeddings** (M2 semantic search) | **LIVE** (real Voyage key) | `voyage-3.5`, dim 1024, HNSW ANN index; free tier is 3 RPM until a payment method is added |
| **M11 voice** (STT/TTS) | **LIVE** (on-device) | browser Web Speech; $0, no key; voice-first while DRIVING |
| **FMCSA authority verification** | **BUILT, on Fake** | flag-enabled + dev-driver pre-verified, but **`FMCSA_WEBKEY` is empty** → runs on the deterministic Fake; add a real webKey (free, mobile.fmcsa.dot.gov) to go live |
| **Brand name** | **DECIDED: Haulmeter** | wired from `ui/src/core/brand.js`; trademark/domain clearance is the owner's step |

**Not yet built (need an external partner/account — owner decisions):**
- **Stripe/Connect** (M6 real payouts) · **fuel partner** (M7 merchant network) · **collections + legal** (M3/M4 recovery muscle) · **IFTA** (M9 fuel-tax engine) · **marketplace damage insurance** (M6 activation) · **commercial fuel-price feed** (M7, OPIS vs crowd).
- **F15 locale review** by native speakers (no partner needed — just review of shipped copy; now unblocked by the brand decision).

## 5. Quality baseline (last verified this session, current HEAD)

- Backend: **pytest 345 passed** · `ruff` clean · **lint-imports 29/29 KEPT**.
- UI: **vitest 116 passed** · `vite build` green.
- Migrations at head: **0026** (`f09.embedding` → vector(1024) + HNSW). 0024 (m03 start-notice), 0025 (f01 authority-verification cols) also applied.
- **Note:** don't run `make ci` while the stack is up — its preflight fails on the bound LOCKED ports. Run the suites in-container, or `make down` first.

## 6. Ports / env

LOCKED: Postgres 5438 · API 8008 · UI 9008 (fallback 3008). Also Redis 6438 · MinIO 9018/9019 · Mailpit 1038/8038. Keys live in `infra/.env` only (gitignored; `.env.example` has placeholders): `MAPBOX_TOKEN` ✅ · `ANTHROPIC_API_KEY` ✅ · `VOYAGE_API_KEY` ✅ · `FMCSA_WEBKEY` ⬜ empty · `F9_MODEL` · `EMBED_MODEL=voyage-3.5`. Internal identifiers (`longhaul` Docker/DB/MinIO creds, `longhaul-api`, the F4 `longhaul-evidence:` hash namespace) are infra, **not** the brand, and stay unchanged.

## 7. This session's arc (058 → this snapshot) — 6 commits since `a702ea0`

1. `1e2ca6f` **FMCSA authority verification** (F1) — key-gated MC#/DOT lookup; migration 0025.
2. `5fd3570` **F6 image serving** — real evidence-photo thumbnails from MinIO, owner-gated.
3. `5ed2768` **Voyage embeddings** (F9/M2) — real EMBED_DIM 1024 + HNSW ANN index; migration 0026.
4. `5336261` **Embeddings hardening** — retry/backoff + best-effort approval (surfaced by the real Voyage 429 free-tier limit).
5. `5fb0711` **M11 voice on-device** — browser Web Speech STT/TTS, motion-aware.
6. `d8c910b` **Brand = Haulmeter** — single source of truth; PRD §17.6 / design-prd §23 logged.

Decision Log now runs to **206** (190–206 in 058–063; §2 of each). Key ones: 190 authority=onboarding-declared; 191 filed-is-server-derived; 197 storage/enrichment never blocks the core action; 199 blob-fetch over presigned URLs; 204 voice on-device; 206 brand=Haulmeter.

## 8. Exact next task — owner names the next input

The build is done; every remaining item is an **owner input**, not a coding blocker:
- **Highest-leverage:** **Stripe/Connect** (turns on real payouts — needs a Stripe account to begin).
- **Cleanest non-partner task:** **F15 native-speaker locale review** (all shipped copy incl. the new `voice.*` / `authority.*` / `evidence.images_note` strings + the Haulmeter wordmark in each script).
- **Cheapest credibility win:** drop a real **`FMCSA_WEBKEY`** into `infra/.env` + recreate api → FMCSA verification goes live (already built).
- Others: fuel partner · collections+legal · IFTA · marketplace insurance · fuel-price feed · trademark/domain clearance for "Haulmeter."

## 9. Working rules (unchanged — HANDOFF §4)

Plan → owner approval → code · Docker-only · **local commits only, NEVER push** · tests with every change · no code comments except `AI-CONTEXT:` · maximum modularity (import-linter) · design-prd §22.3 DoD on all UI · session handoff docs · no secrets in the repo.

## 10. How to run (all Docker) — stack is UP

```
make up        # preflight + full stack
# suites (stack up): docker compose -f infra/docker-compose.yml exec api pytest -q
#                    docker compose -f infra/docker-compose.yml exec ui npx vitest run
make ci        # ONLY with the stack down (preflight needs the LOCKED ports free)
```
The driver app: **http://localhost:9008** — login reads **Haulmeter**; Mapbox + Claude + Voyage live; voice on-device; evidence photos serve real thumbnails.

*— Snapshot end. Haulmeter is feature-complete and hardened; four seams live on real providers, the rest gated on owner-provisioned partners/accounts. Next: owner names the input (Stripe / F15 locale review / FMCSA key).*
