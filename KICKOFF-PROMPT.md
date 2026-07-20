# Kickoff Prompt — paste this into Claude Code for Session 1

---

You are starting Session 1 of LONGHAUL, a greenfield consolidated trucker platform. Work inside the current directory. Follow this prompt exactly.

## Step 1 — Read the governing documents, in this order, before anything else
1. `docs/handoffs/HANDOFF-000.md` (initial handoff — current state, rules, ports)
2. `docs/trucker-platform-prd.md` (product PRD)
3. `docs/design-prd.md` (design constitution)

Then confirm back to me, in a few lines, the two governing laws:
- **Build law (PRD §6):** Common Ground F1–F15 first, to its Definition of Done (PRD §7.16); then modules M1 → M12 in order, each behind a feature flag to its DoD. One continuous build. No v1/v2 phasing.
- **Design law (design-prd §1):** MOBILE FIRST — every screen designed, built, and tested at 360×800 dp before any wider viewport; `min-width` media queries only; design-prd governs every design decision via its §22 protocol. Never improvise design.

## Step 2 — Ports (CRITICAL: other apps are running on this machine)
Never bind default ports (5432, 6379, 8000, 3000, 9000, …). Use ONLY these, parameterized via `.env` (commit `.env.example`):
- **PostgreSQL: 5438** (LOCKED)
- **API (FastAPI): 8008** (LOCKED)
- **Frontend (Quasar dev): 9008** (primary; **3008** is the approved fallback if 9008 is occupied)
- Redis 6438, MinIO 9018/9019, Mailpit 1038/8038 (proposed — verify each is free first; if occupied, pick the nearest free port in the same family and record it in the handoff)
Create `scripts/check_ports.sh` and wire it as a compose preflight: it must fail loudly, naming the conflicting PID, before any container starts. The three LOCKED ports are never changed without me.

## Step 3 — Plan first (do NOT write code yet)
Produce a written plan and WAIT for my approval. The plan must cover:
1. Repo scaffold per HANDOFF §5 (api/foundation f01–f15, api/modules m01–m12 as empty bounded contexts, ui/, infra/, docs/, tests mirroring packages).
2. `CLAUDE.md` content: pointers to the three governing docs, the working-rules summary, the port table, and the instruction that design-prd governs all UI decisions.
3. Docker Compose topology (Postgres 16 + PostGIS + pgvector, Redis, API, worker, MinIO, Mailpit, Quasar dev) using only §2 ports from `.env`.
4. import-linter contracts implementing PRD §10 boundaries (modules→foundation; modules→earlier-module public interfaces only; no lateral imports; core/UI split).
5. `ui/src/core/tokens.scss` seeded EXACTLY from design-prd §6 (colors, type scale, spacing, radius, elevation, motion, touch targets) — no values invented.
6. Test harness + compose-based CI skeleton, including the pseudo-locale (`xx-XL`, +40%) check stub and the six-locale string completeness check stub (design-prd §12.5).
7. Build order and per-component test strategy for F1 (Identity) and F2 (Facility Registry) — schemas, migrations, tests — as the first foundation work after scaffold approval. **F1 auth spec (LOCKED):** email/password only at launch, with NO activation/verification step; implement as a pluggable auth-method registry (one account → many linked methods) so social OAuth and email/SMS OTP can be added later without schema or session-model rework. Do not build OAuth, OTP, or verification emails now — leave clean seams only.

## Step 4 — Execute after approval
Implement the approved plan only. Rules in force at all times:
- Docker-only; nothing runs outside containers.
- Local commits only — NEVER push. Small, well-messaged commits.
- Tests accompany every change; red tests block progress.
- No code comments except `AI-CONTEXT:` markers.
- No secrets — `.env.example` only.
- Any design/UI question: answer from design-prd or its §22 protocol; if it requires a new token/component/nav/notification class, STOP and ask me, logging a proposal in design-prd §23 format.

## Step 5 — Close the session properly
Before ending: run the full test suite in compose; then write `docs/handoffs/HANDOFF-001.md` covering (a) what now exists and passes, (b) decisions made, (c) the exact next task, (d) blockers/questions for me, (e) any port or env changes. A session without a handoff is unfinished.

Begin with Step 1 now.
