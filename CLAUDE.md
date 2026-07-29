# CLAUDE.md — LONGHAUL working context

LONGHAUL is a consolidated, mobile-first platform for US truck drivers: a
truck-aware live map, GPS-verified detention/accessorial recovery, parking,
fuel, and fleet layers. Driver pays $0, forever.

## Read these first, every session, in this order

1. **`docs/handoffs/HANDOFF.md`** — a pointer to `docs/handoffs/HANDOFF-<latest>.md`, which holds the
   current state, decisions, exact next task, blockers. (Session-0 bootstrap: `HANDOFF-000.md`.)
2. **`docs/trucker-platform-prd.md`** — the product PRD. **Governing build law.**
3. **`docs/design-prd.md`** — the **design constitution**. Governs EVERY UI decision.

If code and these documents disagree, **the documents win.** Doc changes require an
explicit owner decision logged in `design-prd.md §23` / PRD §17.

## The two governing laws

- **Build law (PRD §6):** Build the **Common Ground F1–F15 first**, in full, to the
  Foundation Definition of Done (PRD §7.16). Only then build modules **M1 → M12 in order**,
  each end-to-end behind its own F13 feature flag to its DoD, tests alongside every change.
  One continuous build — a dependency sequence, **not** v1/v2/v3 phasing. No module UI before
  the Common Ground is production-quality.
- **Design law (design-prd §1, LAW 0):** **MOBILE FIRST, non-negotiable.** Every driver-app
  screen is designed, built, and tested at **360 × 800 dp portrait first** (mid-range Android;
  iPhone 375 dp second). **`min-width` media queries only.** Wider viewports may only
  re-arrange and add breathing room — never add features. The only non-mobile-first surfaces
  are the three web portals (design-prd §18).

## design-prd governs ALL UI decisions

Before writing or changing ANY user-facing code (screens, components, styles, copy,
notifications, PDFs, emails): consult `design-prd.md`. If it answers the question, follow it
exactly — no reinterpretation. If it is silent, apply the **§22 Decision Protocol** and compose
from existing tokens/rules. **Never improvise** a new color, type size, spacing, component
pattern, navigation structure, or notification class — those four categories are never invented:
**STOP and ask the owner, logging a §23 proposal.** Every UI change passes the §22.3 Definition
of Done (mobile-first, tokens-only, six locales, offline, DRIVING-state, a11y) before it is "done."

## Working rules (non-negotiable — HANDOFF §4)

1. **Plan first.** Written plan → owner approval → code. No speculative building.
2. **Docker-only.** Nothing runs outside containers; dev = CI parity.
3. **Commit locally without asking; push and deploy only when the owner asks.** Small,
   frequent, well-messaged commits are the default and need no permission. `git push`
   (`github.com/turabekh/haulmeter`, **public**) and `./scripts/deploy.sh` are the
   owner's call each time — never a step you add to the end of a task on your own.
   The repo being public is part of the rule: check a diff for secrets before it leaves.
4. **Tests with every change.** No FR without a test; red CI/tests block everything.
5. **No code comments** except `AI-CONTEXT:` markers for future-session orientation.
6. **Maximum modularity.** Respect the import-linter contracts from the first file.
7. **Design constitution supremacy.** All UI passes design-prd §22.3 DoD, mobile-first checks included.
8. **Session handoff docs.** Every session ends by writing the next `docs/handoffs/HANDOFF-<n>.md`.
9. **No secrets in the repo.** `.env.example` only; real keys live outside version control.

## Ports — LOCKED (other apps run on this machine)

Never bind default ports (5432/6379/8000/3000/9000/1025…). All ports are parameterized in
`infra/.env` (from committed `infra/.env.example`); nothing hardcoded. `scripts/check_ports.sh`
runs as a compose preflight (`make up`) and fails loudly with the conflicting PID before any
container starts. The three LOCKED ports are never changed without the owner.

| Service | Port | Status |
|---|---|---|
| PostgreSQL (PostGIS + pgvector) | **5438** | LOCKED |
| API (FastAPI) | **8008** | LOCKED |
| Frontend dev (Quasar) | **9008** | PRIMARY (fallback **3008**) |
| Redis | 6438 | verified free |
| MinIO API / console | 9018 / 9019 | verified free |
| Mailpit SMTP / UI | 1038 / 8038 | verified free |

## Architecture & boundaries

FastAPI **modular monolith** — `api/app/foundation/f01…f15` + `api/app/modules/m01…m12`,
one Postgres schema per component (schema-per-module). **import-linter** (`api/importlinter.ini`)
is authoritative on boundaries: `core` < `foundation` < `modules`; a module may import
`foundation.*.public` and **earlier** modules' `.public` only — no lateral imports, no reach-ins
past `public.py`, no `core → foundation/modules`. UI: Quasar/Vue 3, business logic in
`ui/src/core/`, zero Quasar visual defaults (design-prd §19); tokens in `ui/src/core/tokens.scss`
are the only source of visual truth.

## Common commands (all via Docker)

```
make env         # create infra/.env from example
make preflight   # verify all host ports free (fails loud with PID)
make up          # preflight, then start the full stack
make test        # full suite (api pytest + ui vitest) in compose
make lint        # ruff + import-linter in the api container
make ci          # preflight + lint + test (CI parity)
```
