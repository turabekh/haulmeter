# HANDOFF-037 — Public Scorecard portal (the outward-facing surface; 100 commits)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, offline fully a mode, admin console live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–036 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-036)

The **Public Scorecard** — the outward-facing web portal (design-prd §18) and the **only unauthenticated surface** — is live. It's the public face of the M2 facility data: search a facility, see its objective dock time + driver rating, aggregate-only and min-sample suppressed (§13).

### Backend — `/public` API (`api/app/api/public.py`)
The only router with **no `current_account`** (public):
- **`GET /public/facilities?q=`** — name search over the facility directory.
- **`GET /public/facility/{id}`** — the aggregate scorecard: objective dwell median/p90 **with sample size** (§11.7), driver rating + review count. **Dwell is suppressed below `PUBLIC_MIN_SAMPLE=3`** — never a small-n figure, never identifiable driver data (§13). Composes F2 + M2.

### UI — `PublicScorecardSurface` (`/scorecard`)
- A **web-first PUBLIC portal**: `meta.public` **bypasses the auth guard** (a visitor with no session can view it), `meta.portal` widens the frame, no tab chrome. Search box → results list → an aggregate scorecard (dock time in Mono + sample size, driver rating). Fixture demo when the API is unreachable.
- `api.js`: `searchFacilities` + `fetchScorecard` — the only **token-free** fetchers.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 284 passed** (was 281; +3: no-auth access, min-sample suppress→publish, 404).
- UI: **vitest 90 passed** (+2: search+scorecard, dwell suppression) · `vite build` clean · six-locale completeness at **208 keys**.
- **Live smoke:** `GET /public/facilities` returns **with no Authorization header** (public access confirmed); unknown facility → 404.

**Milestone: 100 commits on `main`** (local only, never pushed) — the full F1–F15 + M1–M12 build plus twelve hardening sessions.

## 2. Decisions made (append to Decision Log)

141. **The Public Scorecard is the only unauthenticated route, gated by `meta.public`.** The router guard already had the mechanism (login uses it); the scorecard reuses it so a public visitor bypasses login while every other route still requires a session. Its API fetchers are the only ones that don't require a token.
142. **Public dwell is suppressed below its own floor (`PUBLIC_MIN_SAMPLE=3`), independent of M12's data-product floor (5).** The free public scorecard and the paid data product are different products with different thresholds; both honor §13 (aggregate-only, never small-n), but the public view can show a lower bar than the commercial benchmark. No reviews text is exposed — rating + count only — to keep the public surface strictly aggregate.
143. **Portal trio complete via one shared mechanism.** Driver app + three web portals (fleet, admin, public scorecard) all live in one SPA, differentiated only by route meta (`portal`, `chrome`, `public`) and shared `ui/core` tokens — no separate builds, no driver-screen imports into portals (§18).

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input):
- **Property-Owner portal** (design-prd §18) — the last of the three §18 portals: a parking-property owner's view of their M6 listings, bookings, and payouts (ledger owner_payable). Composes M6 + F7. **Recommended next** (completes the §18 portal set).
- **Incident capture sheet** (M5-FR4) — small: kind + note → `/protection/incident` (idempotent).
- **Richer admin console** — analytics funnels + config editing (F14 `funnel`/`set_config` ready).
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`; approved-review snippets on the public scorecard.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name. Flip these on in the admin console once gates are satisfied.

**Recommendation:** the **Property-Owner portal** — it's the last §18 surface, and it gives the parking-supply side (M6 owners) their own workspace, closing the loop on the marketplace (drivers book, owners see payouts). Note: full payout *settlement* is the Stripe/Connect seam (deferred), but the owner's view of listings + bookings + accrued payable is buildable now on the F7 ledger.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **208 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**Public Scorecard (no login):** http://localhost:9008/scorecard — search a facility, view its dock-time + rating. API `GET /public/facilities`, `GET /public/facility/{id}` (no auth). Other portals: `/fleet`, `/admin` (login required).
Suite: **pytest 284 · vitest 90 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; offline fully a mode; four surfaces (driver app + fleet/admin/public-scorecard portals).** Hardening to date: public scorecard (037), evidence-sync (036), admin console (035), M5 capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3, led by the Property-Owner portal.

## 8. Commits this session (local only, never pushed)

`10db240` HANDOFF-036 → `7c4ada2` Public Scorecard portal (+ this handoff). **100 commits** on `main`, never pushed.

*— End of session. Next: the Property-Owner portal (§18, on M6 + F7 publics) — the last §18 surface — then the incident sheet and richer admin console. Activation seams await owner/BD inputs (§4).*
