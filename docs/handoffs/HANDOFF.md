# HANDOFF.md — Session 0 (Initial Handoff)

**Project codename:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Greenfield. Nothing built. This is the bootstrap context for the first Claude Code session and the template for every handoff after it.

---

## 1. Authoritative documents — read in this order, every session

1. `HANDOFF.md` (latest in `docs/handoffs/`) — current state, next task, blockers.
2. `docs/trucker-platform-prd.md` — the product PRD. Governing build law: **Common Ground (F1–F15) first, then modules M1 → M12, in order, to the end. One continuous build. No v1/v2 phasing.** (PRD §6.)
3. `docs/design-prd.md` — the **design constitution**. Governs EVERY design decision: visual, layout, interaction, copy, notifications, PDFs. **LAW 0: MOBILE FIRST — 360×800 dp baseline, min-width queries only.** When any UI question arises, the answer is in this document or derived by its §22 Decision Protocol. Never improvised.

If code and these documents disagree, the documents win. Changes to the documents require an explicit owner decision logged in `design-prd.md §23` / PRD §17.

## 2. CRITICAL — Port allocations (other apps run on this machine)

The owner's machine runs multiple other projects. **Never bind default ports** (5432, 6379, 8000, 3000, 9000, 1025, etc.). This project's ports are **LOCKED** as follows and must be used everywhere (compose, .env, docs, tests):

| Service | Port | Status |
|---|---|---|
| PostgreSQL (PostGIS + pgvector) | **5438** | LOCKED (owner-assigned) |
| API (FastAPI) | **8008** | LOCKED (owner-assigned) |
| Frontend dev server (Quasar) | **9008** | PRIMARY (owner-approved; **3008** is the approved fallback if 9008 is taken) |
| Redis | 6438 | proposed — verify free before binding |
| MinIO (S3 dev) API / console | 9018 / 9019 | proposed — verify free before binding |
| Mailpit SMTP / UI (dev email) | 1038 / 8038 | proposed — verify free before binding |

Rules:
- All ports are parameterized in `.env` (committed `.env.example` with these values); nothing hardcoded in compose files or app config.
- A preflight script (`make preflight` / `scripts/check_ports.sh`) verifies every configured port is free **before** `docker compose up`, and fails loudly with the conflicting PID if not.
- If a proposed port conflicts, choose the nearest free port in the same family (x38 / x0x8 pattern), update `.env.example`, and record the change in the session handoff. The three LOCKED ports are never changed without the owner.

## 3. Fixed stack (do not deviate)

FastAPI **modular monolith** (one deployable; `foundation/f01…f15` + `modules/m01…m12` packages; import-linter enforced boundaries — modules → foundation allowed, modules → earlier-module public interfaces allowed, lateral/reach-in forbidden; core/UI split enforced) · PostgreSQL 16 + PostGIS + pgvector (single DB, schema-per-module ownership) · Redis + background workers · Quasar/Vue 3 + Capacitor (driver app; swappable-UI discipline — business logic in core, zero Quasar visual defaults per design-prd §19) · Docker Compose for everything (dev = CI parity; nothing runs outside containers) · S3-compatible object storage (MinIO in dev) · Stripe/Twilio/FCM/Mapbox behind adapters, stubbed locally · All LLM/STT/TTS calls exclusively via the F9 AI Gateway.

## 4. Working rules (non-negotiable, from the owner's standard practice)

1. **Plan first.** Every session: written plan → owner approval → code. No speculative building.
2. **Docker-only.** No bare-metal processes, no global installs.
3. **Local commits only. NEVER push.** Small, frequent, well-messaged commits.
4. **Tests with every change.** No FR without a test; red CI blocks everything.
5. **No code comments** except `AI-CONTEXT:` markers where future sessions need orientation.
6. **Maximum modularity.** Respect the import-linter contracts from the first file.
7. **Design constitution supremacy.** Any UI work passes design-prd §22.3 DoD, including the mobile-first checks, before it is "done."
8. **Session handoff docs.** Every session ends by writing `docs/handoffs/HANDOFF-<n>.md` (state reached, decisions made, next task, blockers, port/env changes). The next session starts by reading it.
9. **No secrets in the repo.** `.env.example` only; real keys live outside version control.

## 5. Target repository layout

```
longhaul/
  CLAUDE.md                  # points to the three governing docs + rules summary
  HANDOFF.md                 # symlink/copy of latest handoff
  docs/
    trucker-platform-prd.md
    design-prd.md
    handoffs/HANDOFF-000.md  # this file
  infra/
    docker-compose.yml       # all ports from .env
    .env.example
  scripts/check_ports.sh
  api/
    foundation/ f01_identity … f15_localization
    modules/    m01_map … m12_fleet          # scaffolds only until foundation DoD
    tests/                                    # mirrors packages
    importlinter.ini
  ui/
    src/core/                # tokens.scss, state machine, The Meter, core components
    src/surfaces/            # map / load / money / docs / more
```

## 6. Current milestone & first session scope

**Milestone: Common Ground F1–F15** to the Foundation Definition of Done (PRD §7.16). No module UI before that (PRD §6).

Session 1 scope (subject to the plan-first review): repo scaffold per §5 · `CLAUDE.md` · Docker Compose with §2 ports + preflight script · import-linter contracts live · `ui/tokens.scss` seeded exactly from design-prd §6 · test harness + CI skeleton (compose-based) · begin **F1 Identity** and **F2 Facility Registry** schemas with tests, in that order.

**Auth decision (LOCKED, owner-set):** launch auth is regular **email/password with no activation/verification step**. Build F1 as a pluggable auth-method registry (one account, multiple linked methods) so **social OAuth and email/SMS OTP** can be added later with zero schema or session-model rework. Do not build verification emails, OAuth, or OTP now — only leave clean seams for them.

## 7. Open items (owner input needed, non-blocking for session 1)

Brand name (LONGHAUL is internal only) · collection-partner shortlist (M3 activation) · Mapbox/Stripe/Twilio test credentials when integration work starts · fuel-price data route (PRD §17).

## 8. Handoff protocol reminder

End of every session, no exceptions: write the next `HANDOFF-<n>.md` covering (a) what exists and passes tests now, (b) decisions made + Decision Log entries added, (c) exact next task, (d) blockers/owner questions, (e) any port or env change. Sessions that end without a handoff are considered unfinished.

*— End of Session 0 handoff. First action of Session 1: read §1 documents, then present the plan.*
