# CLAUDE.md — LONGHAUL working context

LONGHAUL is a consolidated, mobile-first platform for US truck drivers: a
truck-aware live map, GPS-verified detention/accessorial recovery, parking,
fuel, and fleet layers. Driver pays $0, forever. Public brand: **Haulmeter**
(haulmeter.online).

## Read these first, every session, in this order

1. **`docs/handoffs/HANDOFF.md`** — a pointer to `docs/handoffs/HANDOFF-<latest>.md`, which holds the
   current state, decisions, exact next task, blockers. (Session-0 bootstrap: `HANDOFF-000.md`.)
2. **`docs/trucker-platform-prd.md`** — the product PRD (v1.0), **as amended by**
3. **`docs/trucker-platform-prd-v2-amendment.md`** — the v2.0 amendment. **Where they
   disagree, v2.0 wins.** It replaced §6's work ordering with the validation law and holds
   the live owner-decision registry (D-series) and the Phase DoD.
4. **`docs/design-prd.md`** — the **design constitution**, §0–§22. Governs EVERY UI decision.
   **37 KB, and that is deliberate:** §23's decision log was split out on 2026-08-16 at
   372 KB — 91% of a file every session had to read in full. The log lives in
   **`docs/decisions/`** and is not a read-first document; go there when you need to know
   *why* something is the way it is, or to append. §23 itself still holds the rules for
   how to write to it.

If code and these documents disagree, **the documents win.** Doc changes require an
explicit owner decision logged in `docs/decisions/` (design-prd §23) / the v2.0 §6 registry.

**`docs/TRAPS.md` — read the relevant section before you touch something**, not cover to
cover. 80+ things that have already cost this project time, each with what it cost: the
migration that reports success and applies nothing, the harness state that measures the
wrong screen, the deploy that changes nothing, the zero that means "not measured". It
replaces the "things a later session will trip over" section nine handoffs each rewrote —
so **new traps go there**, and a handoff carries only what was specific to that session.

## The two governing laws

- **Validation law (v2.0):** work is ordered by **distance to a validated driver outcome**.
  A requirement is done when a person who is not the owner has used it and the outcome is
  observable in the database — a green suite clears nothing on that list. Every FR names
  its validation, not just its tests. **A deferral that cannot fail is indistinguishable
  from a finished feature; nothing "sends" that didn't actually leave the system.**
  (The *how* of the retired build law survives in the working rules: modules in order,
  each behind its own F13 flag to its DoD, tests alongside every change, plan-first.)
- **Design law (design-prd §1, LAW 0):** **MOBILE FIRST, non-negotiable.** Every driver-app
  screen is designed, built, and tested at **360 × 800 dp portrait first** (mid-range Android;
  iPhone 375 dp second). **`min-width` media queries only.** Wider viewports may only
  re-arrange and add breathing room — never add features. The only non-mobile-first surfaces
  are the web portals (design-prd §18).

## design-prd governs ALL UI decisions

Before writing or changing ANY user-facing code (screens, components, styles, copy,
notifications, PDFs, emails): consult `design-prd.md`. If it answers the question, follow it
exactly — no reinterpretation. If it is silent, apply the **§22 Decision Protocol** and compose
from existing tokens/rules. **Never improvise** a new color, type size, spacing, component
pattern, navigation structure, or notification class — those categories are never invented:
**STOP and ask the owner, logging a decision-log proposal.** Every UI change passes the §22.3
Definition of Done (mobile-first, tokens-only, all locales, offline, DRIVING-state, four
states, a11y, layout-harness registration in the same commit) before it is "done."

## Working rules (non-negotiable — HANDOFF §4)

1. **Plan first.** Written plan → owner approval → code. No speculative building.
2. **Docker-only.** Nothing runs outside containers; dev = CI parity.
3. **Commit locally without asking; push and deploy only when the owner asks.** Small,
   frequent, well-messaged commits are the default and need no permission. `git push`
   (`github.com/turabekh/haulmeter`, **public**) and `./scripts/deploy.sh` are the
   owner's call each time — never a step you add to the end of a task on your own.
   The repo being public is part of the rule: check a diff for secrets before it leaves.
4. **Tests with every change.** No FR without a test; red CI/tests block everything.
   Red-first where a defect is claimed; sabotage-check what you fixed.
5. **No code comments** except `AI-CONTEXT:` markers for future-session orientation.
6. **Maximum modularity.** Respect the import-linter contracts from the first file.
7. **Design constitution supremacy.** All UI passes design-prd §22.3 DoD, mobile-first checks included.
8. **Session handoff docs.** Every session ends by writing the next `docs/handoffs/HANDOFF-<n>.md`.
9. **No secrets in the repo.** `.env.example` only; real keys live outside version control.

## LIVE-FIRE — email (and any activated transport) is real in EVERY environment

By owner decision (2026-08-15), Gmail SMTP as **claims@haulmeter.online** is the transport
everywhere — there is no Mailpit, no sandbox, no environment guard, and none may be
restored as a tidy-up. **Nothing is ever addressed to an inbox the owner does not
control** during build, test, or demo. Check the outbound queue **before** any container
recreate or worker sweep — a stale unsent message drains under whatever identity is live.

## Ports — LOCKED (other apps run on this machine)

Never bind default ports (5432/6379/8000/3000/9000…). All ports are parameterized in
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

## Architecture & boundaries

FastAPI **modular monolith** — `api/app/foundation/f01…f15` + `api/app/modules/m01…m14`,
one Postgres schema per component (schema-per-module). **import-linter** (`api/importlinter.ini`)
is authoritative on boundaries: `core` < `foundation` < `modules`; a module may import
`foundation.*.public` and **earlier** modules' `.public` only — no lateral imports, no reach-ins
past `public.py`, no `core → foundation/modules`. UI: Quasar/Vue 3, business logic in
`ui/src/core/`, zero Quasar visual defaults (design-prd §19); tokens in `ui/src/core/tokens.scss`
are the only source of visual truth.

## Delegation — subagents in `.claude/agents/`

Six specialists. Delegate the sweeps; keep the epistemics in this session.

- **`scout`** — every kickoff step-0 re-grep, reader census, claim verification, and
  "does this already exist?" **before building anything.** On this codebase, "build X"
  is often "assert X" — scout finds it first.
- **`test-runner`** — any test run longer than one file. Gate numbers in handoffs come
  from its **raw report**, never from memory. It reports; it never fixes or re-runs to
  coax a pass.
- **`i18n-auditor`** — every diff that touches driver-facing strings, before commit.
- **`reviewer`** — the staged diff before **every** commit: constitution DoD, TRAPS
  patterns, code-without-test, paperwork (DRIVE.md, decision entries, harness, edge
  routing), secrets.
- **`gate-verifier`** — read-only box proofs after deploys (alembic, information_schema,
  flags, registries, public-edge fetches, queue state). It never mutates anything;
  mutations happen in this session under the owner's eyes.
- **`counsel`** — the Fable advisor. Any fork the brief doesn't resolve, and **before
  presenting any plan for owner approval.** It advises from the tree.

**None of them carry owner authority.** D-decisions, never-improvise categories,
reversals, live-fire actions, and push/deploy stop for the owner, always. **Red-first
and sabotage loops are never delegated** — they are arguments, not runs, and they stay
in the main session. Don't delegate a single grep; subagents earn their keep on sweeps.

## Common commands (all via Docker)

```
make env         # create infra/.env from example
make preflight   # verify all host ports free (fails loud with PID)
make up          # preflight, then start the full stack
make test        # full suite (api pytest + ui vitest) in compose
make lint        # ruff + import-linter in the api container
make ci          # preflight + lint + test (CI parity)
```

## Current work queue

- **`docs/kickoffs/`** — session briefs, plan-first, use them verbatim.
- **`docs/validation/`** — the observation checklists only the world can fill
  (`j1-journey.md`, `m14-slice1.md`); a session never checks these boxes from a suite.
- **`docs/audits/OPEN-FINDINGS.md`** — the live defect queue (2026-08-07 audit: all
  criticals closed; update status when you close a remaining finding).
- `docs/audits/AUDIT-INDEX.md` — background and suggested order.

Findings marked OBSERVED were read from a dump, not a running system.
Re-grep before acting. Findings marked INFERRED need a command on the box first.