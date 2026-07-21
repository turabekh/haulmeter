# HANDOFF-049 — Authz sweep: M3 detention + M5 protection IDORs closed

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live and browser-reachable via /dev, active-load lifecycle owner-gated, offline fully a mode, admin console operational, M6 self-serve, two F13-config knobs live. Post-build hardening (security). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–048 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-048)

Continuing the authz sweep the load fix (048) started. Audited every ID-scoped API endpoint; found and closed **three more private-data IDORs** in M3 and M5. (Facility-scoped endpoints — m02 reviews, m08 risk, m10 questions, m12 benchmark — are shared community/aggregate data by design and are *not* IDORs.)

### Backend fixes
- **M3 detention** (`GET /detention/{claim}/clock`, `POST /detention/{claim}/pack`): `_load_claim` now takes the account and **403s a claim that isn't the caller's** (`claim.account_id != account.id`). Before, any driver could read another's detention clock (dollars owed) or generate/file their pack.
- **M5 protection** (`POST /protection/condition/{capture}/photo`): **403 if the capture isn't the caller's** — this was the worst gap, letting another account **append photos to someone's hash-chained legal evidence chain** (tampering). Also `GET /protection/summary/{stop}` now checks the stop's load owner.

### Still open (next increment)
- **M12 fleet** `GET /{fleet}/report`, `GET /{fleet}/claims`, `POST /{fleet}/invite` — **no membership check**: any authenticated user can read any fleet's financials/roster or invite to it. Needs a member/role gate (a small product decision on who may view — any member vs. managers). Flagged as the immediate next task.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 304 passed** (ownership 403 assertions folded into the existing detention-flow and condition-capture tests; owner paths still 200/201).
- UI: **unchanged** — vitest **100**, six locales at **261 keys**.
- **Live smoke:** owner `/detention/{claim}/clock` → 200; a second account → **403** on both `/clock` (read) and `/pack` (mutation).

## 2. Decisions made (append to Decision Log)

171. **Every private, ID-scoped resource is gated to its owner at the API layer; shared/facility-scoped ones stay open.** The rule: if the row is one user's private data (a detention claim, an evidence capture, a stop's protection summary), resolve it to an owner and 403 non-owners (404 first for missing). If it's community/aggregate keyed by facility (reviews, dwell risk, Q&A, public benchmark), it stays readable — that's the product. This keeps the sweep principled rather than blanket-locking everything.
172. **The M5 condition-photo gap was the highest severity in the sweep.** Appending to a hash-chained F4 evidence log is exactly the artifact that protects a driver in a cargo dispute; letting another account inject into it is evidence tampering, not just an info leak. Fixed first-class (403 before the offline.ingest handler runs, so a replayed key from a non-owner never writes).
173. **M12 fleet financials remain the open gap and need a role decision.** `report`/`claims` expose fleet-wide money and roster; `invite` mutates membership. Gating them needs "who counts as authorized" — any active member, or only owner/manager roles. Deferred to its own increment so the choice is deliberate (and testable) rather than assumed here.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input):
- **M12 fleet membership gate** — `report`/`claims` require an active member; `invite` requires owner/manager role (use `list_members` / the membership role). **Recommended next** (the last known IDOR, and the most financially sensitive).
- **More F13-config seams** — M3 free-time/rate default, M10 `REDEEM_CENTS_PER_POINT`/`RATE_LIMIT_PER_DAY`.
- Small polish: approved-review snippets on the public scorecard; fold moderation decisions into the audit feed; **gate `/dev` behind a dev-mode flag before any deploy**.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), brand name.

**Recommendation:** the **M12 fleet membership gate** — it's the last open IDOR from the audit and the one exposing money (fleet recovered/owed rollups). Gate `report`/`claims` to active members and `invite` to owner/manager; then the authz posture is complete platform-wide.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · locale native review (F15, gate green at **261 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

M3 detention clock/pack and M5 condition-photo/summary now require the caller to own the resource (403 otherwise). No change for the legitimate driver.
Suite: **pytest 304 · vitest 100 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live and browser-reachable via /dev; active-load lifecycle + M3/M5 private resources owner-gated; integration e2e green; offline fully a mode; five product surfaces + a dev directory; admin console operational; M6 self-serve; two F13-config knobs live.** Hardening to date: M3/M5 authz sweep (049), load authz gate (048), end-load (047), GET /load/active (046), dev directory + counterparty names (045), M10 earn config (044), audit-log view (043), owner spot CRUD (042), config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`403a0e3` load authz gate → this: M3/M5 authz sweep (+ this handoff). **114 commits** on `main`, never pushed.

*— End of session. Next: M12 fleet membership gate (the last open IDOR), then config seams / small polish. Activation seams await owner/BD inputs (§4).*
