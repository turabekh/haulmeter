# HANDOFF-070 — Fuel nudge · points-farming cooldown · MAASTO TPIMS registry · HANDOFF.md pointer

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 24 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).
**State in one line:** F1–F15 + M1–M12 complete; a regional-only fuel station now **leads with a
"be the first to report the diesel price here" nudge**, the F10 **points award is cooldown-gated**
(belief still spam-proof and still updates), the TPIMS probe now carries the **authoritative MAASTO
state registry** (IL remains the only live feed), and root **`HANDOFF.md` is a pointer** to the latest.

**Read order each session:** `HANDOFF.md` (pointer → this file) → PRD §6/§12/§8.7 → design-prd
§11.2/§11.5/§11.7/§22 → this file → HANDOFF-069 (live data + honesty) → 068 (live activation) →
067 (fuel) → 066 (viewport map).

---

## 0. Current data state (dev DB, live — UNCHANGED this session)

| Thing | Value |
|---|---|
| Facilities | **4154** — OSM 2321 · NTAD 1827 · TPIMS 54 (IL) · admin/DEV_SEED 11 |
| EIA regional baseline | **6 regions**, week_of **2026-07-20** (PADD1 $5.19 · PADD2 $4.99 · PADD3 $4.94 · PADD4 $4.93 · PADD5 $5.88 · US $5.13) |
| TPIMS parking beliefs | 17 (IL feed, feed-timestamped) |
| Ingest flags ON | `m07_ingest_eia` (weekly) · `f02_ingest_tpims_static` (daily) · `f02_ingest_tpims_dynamic` (~3 min) |
| New F13 config | `f10_award_cooldown_seconds` (default **21600 / 6h**, unset in DB → default applies) |
| Migrations | head now **0031_f10_award_cooldown** (adds `f10.submission.awarded`) |
| Tests | **pytest 386 · vitest 131 · ruff clean · import-linter 29/29** |

No ingest ran this session, so facility/belief/EIA counts are unchanged from HANDOFF-069.

---

## 1. What this session built (newest first)

### Task 4 — root `HANDOFF.md` is now a pointer (housekeeping)
`HANDOFF.md` had frozen Session-0 content while the layout described it as "a copy of the latest
handoff." **Decision: it becomes a one-line pointer** to `docs/handoffs/HANDOFF-<latest>.md` (a copy
would duplicate content and silently drift; a pointer can't go stale). Read-order references in
`CLAUDE.md` and `KICKOFF-PROMPT.md` were reconciled to the same convention: start at root `HANDOFF.md`,
which points to the latest numbered handoff.

### Task 3 — TPIMS state expansion probe (no new state activated)
`make probe-tpims` now carries the **authoritative MAASTO feed registry**, transcribed from the WisDOT/
TOPS-Lab developer page `transportal.cee.wisc.edu/tpims/parking-data-devs.html` (the single source of
truth). Confirmed the IL Travel Midwest feed is **IL-only** (all 51 rows siteId `IL…`), so each other
state needs its own endpoint. **Only 4 of the 8 non-IL states publish a public URL; the other 4 are
registration-gated.** Per-state probe results below (§3). **No feed reported LIVE spec-shaped**, so
nothing was added to `data_sources` config, no ingest ran, no fixtures committed, and the ingest runner
was **not** generalized to multi-state (that would be speculative build ahead of a live feed) — IL stays
the only live TPIMS source.

### Task 2 — F10 points-farming cooldown (`d221c88`)
`submit()` still records every submission and the belief still moves on a re-report (already spam-proof
via distinct-contributor aggregation), but **points now issue at most once per driver/facility/signal
per cooldown window**. New `awarded` flag (migration 0031) anchors the cooldown on the last real AWARD,
so intermediate cooled-down reports can't slide the window forward. Duration is F13-tunable
(`f10_award_cooldown_seconds`, default 6h). Authoritative/feed submissions never award → unaffected.
5 new tests (block-within-window + belief-still-updates, resume-after-window, per-driver, F13-config,
authoritative-never-awards).

### Task 1 — regional-only fuel station "be the first" nudge (`320f4a3`, §15.3 / §11.7)
When a fuel station is priced **only** by the EIA regional estimate (`source === "regional"`, no network
feed, no crowd consensus), `FacilityCard` leads with an empty-state sentence **"Be the first to report
the diesel price here."** and makes **Report diesel price the primary action** into the existing price
sheet; Navigate demotes to secondary and the duplicate report affordance is dropped. The
`~$X.XX /gal · regional avg · wk of <date>` line **stays as secondary context** — the HANDOFF-069
honesty labels do not regress. New string `fuel.be_first` shipped in all six locales (pseudo
auto-covers). Composed from existing tokens only.

## 2. §22.3 DoD + §23 assessment

- **Task 1 UI** passes §22.3: 360-first, tokens only (`--text-2`, `--type-body-*`, existing `.cta`), six
  locales + pseudo, offline (report queues via the unchanged confirm-price path, F12), DRIVING-safe
  (Corridor mode replaces the card while driving → no interactive prompt mid-drive, Forbidden #11),
  a11y (color+icon+label). **No new token/component/nav/notification** — only a copy string and an F13
  config value — so **no §23 escalation** (see Decision Log).
- **Task 2/3** are API/tooling, no UI surface.

## 3. TPIMS per-state probe results (`make probe-tpims`, 24 Jul 2026)

| State | Endpoint (per WisDOT dev page) | Result | Activated? |
|---|---|---|---|
| **IL** | truckparking.travelmidwest.com | already live (54 facilities, 17 beliefs) | ✅ (prior) |
| IN | content.trafficwise.org/json/{tpims,rest_area}.json | **unreachable** — 443/80 ConnectTimeout from host **and** container | ❌ |
| IA | — | **registration-gated** (email dev@tsps.io) — no public URL | ❌ |
| KS | https://tpims.ksdot.gov/ | **registration form**, no public JSON | ❌ |
| KY | trimarc.org/dat/tpims/TPIMS_*.json | HTTP 200 **text/html** (not spec JSON) — unchanged from 069 | ❌ |
| MI | — | **registration-gated** (email GormanJ4@michigan.gov) | ❌ |
| MN | iris.dot.state.mn.us/iris/TPIMS_* | **unreachable** ConnectTimeout — unchanged from 069 | ❌ |
| OH | ipsens.webhop.biz/ODOT/MaastoDataFeeds/TPIMS/* | **unreachable** — DNS does not resolve (dynamic-DNS host offline) | ❌ |
| WI | — | **registration-gated** (email Michael.Vanness@dot.wi.gov) | ❌ |

Net: **no new state activated.** Public feeds (IN/OH) are documented but unreachable from this network;
KY serves HTML; MN unreachable; IA/KS/MI/WI need registration credentials we don't have. All eight
endpoints/contacts are now encoded in `scripts/probe_tpims.py` so re-checking is one command.

## 4. Decision Log (PRD §17 / design-prd §23)

1. **Points-award cooldown default = 6h** (`f10_award_cooldown_seconds = 21600`, F13-tunable). Gates only
   the award, never the submission or the belief. Owner-approved default this session.
2. **Root `HANDOFF.md` = one-line pointer** to the latest numbered handoff (not a copy). Rationale: a copy
   drifts; a pointer can't. Read-order refs in CLAUDE.md + KICKOFF-PROMPT.md reconciled to match.
3. **TPIMS expansion source of truth = WisDOT/TOPS-Lab dev page.** Only IN/KY/MN/OH are public;
   IA/KS/MI/WI are registration-gated. No state activated (all unreachable / HTML / gated).
4. **No §23 UI escalation.** The fuel nudge is composed from existing tokens + one copy string
   (`fuel.be_first`) — none of the four never-improvise categories (color/type/spacing, component,
   nav, notification) were touched.

## 5. Exact next task (owner's call — nothing is blocking)

**Recommended next:** activate a second TPIMS state the moment a feed becomes reachable — the disciplined
path is (a) run `make probe-tpims`; (b) for any feed reporting LIVE spec-shaped, **generalize the ingest
runner to iterate multiple `data_sources` state feeds** (add `tpims_static_<st>` / `tpims_dynamic_<st>`
keys; the MAASTO V2.2 adapter is unchanged), config the URL, run static→dynamic, verify dedupe + belief,
and commit real-row fixtures. IA/KS/MI/WI require registering for credentials first (contacts in the
probe); IN/OH need network reachability that this environment lacks.

Alternatives (unchanged from 069): differentiate in-region fuel prices further (crowd nudge now shipped —
watch whether reports land); resume the PRD §6 module worklist if pivoting back to feature build.

## 6. Working rules (unchanged — non-negotiable)

Docker-only (dev = CI parity) · **local commits only, NEVER push** · plan-first for non-trivial work ·
**tests with every change** (no FR without a test; red CI blocks everything) · **live pulls never in CI**
(fixtures drive tests) · **AI-CONTEXT comments only** · maximum modularity (import-linter authoritative:
core < foundation < modules, `.public` only) · **design-prd governs ALL UI** (mobile-first 360dp, tokens
only, §22.3 DoD) · session ends by writing the next HANDOFF.
Commit messages end with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## 7. Blockers / questions for the owner

- **TPIMS credentials:** IA/KS/MI/WI feeds are registration-gated. Want me to draft the registration
  requests (contacts are in `scripts/probe_tpims.py`)? Activation needs owner sign-off on obtaining keys.
- **IN/OH reachability:** both publish public feeds but time out / don't resolve from this environment —
  is that a network/firewall limitation on the build host to resolve, or should these stay parked?
- **Cooldown default:** 6h assumed (approved). Say if you want a different window before points go live.

## 8. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-070 + root HANDOFF.md pointer, HANDOFF-000 restored, read-order reconciled
1f700cf TPIMS probe: authoritative MAASTO state feed registry + re-check
320f4a3 M7/M1: regional-only fuel station leads with a "be the first" price nudge
d221c88 F10: points-farming cooldown — gate the award, not the belief
```

## 9. Key files touched (by area)

```
CROWD/F10  api/app/foundation/f10_crowd/domain/{service,models}.py · public.py
           api/tests/foundation/f10_crowd/test_crowd.py
           api/migrations/versions/0031_f10_award_cooldown.py
FUEL UI    ui/src/core/components/FacilityCard.vue · ui/src/core/i18n/*.json (fuel.be_first ×6)
           ui/test/ui-components.test.js
TPIMS      api/scripts/probe_tpims.py (authoritative MAASTO registry)
DOCS       HANDOFF.md (→ pointer) · CLAUDE.md · KICKOFF-PROMPT.md · docs/handoffs/HANDOFF-070.md
```

## 10. Ports / env

No port or env changes this session. `f10_award_cooldown_seconds` is an F13 config row (DB, not env),
unset by default so the 6h code default applies. Migration 0031 applied to the dev DB (`alembic upgrade
head`). `EIA_API_KEY` still required in `infra/.env` for live EIA pulls (unchanged).
