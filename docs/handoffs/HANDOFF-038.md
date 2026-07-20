# HANDOFF-038 — Property-Owner portal (the §18 portal set is complete)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, offline fully a mode, all three §18 web portals live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–037 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-037)

The **Property-Owner portal** — the last of the three design-prd §18 web-first portals — is live. It closes the marketplace loop from the supply side: a parking-property owner sees their M6 listings + spots, their bookings, and the accrued payable the platform owes them (F7 `owner_payable`). This completes the portal trio (fleet, admin, public-scorecard, **owner**) — one SPA, differentiated only by route meta.

### Backend — `/owner` API (`api/app/api/owner.py`)
Session-required (`current_account`); composes M6 + F7 publics:
- **`GET /owner/dashboard`** — returns `{payout_cents, properties:[{id,name,vetted,spots:[{label,price_cents_per_night,active}]}], bookings:[{id,nights,price_cents,owner_payout_cents,state}]}`.
- New M6 owner-side publics (`m06_parking.public`): `owner_properties`, `property_spots`, `owner_bookings`, `owner_payable_cents`. The payable reads the F7 `owner_payable` ledger account (credit balance negated → owed-to-owner). **Payout SETTLEMENT is the deferred Stripe/Connect seam** — this is the *view* of what's owed, not the transfer.

### UI — `OwnerPortalSurface` (`/owner`)
- A **web-first portal**: `meta.portal` widens the frame (1200 dp), no tab chrome, login required (auth guard). Payable KPI (Mono/tabular, shield color) with a "settlement activates when payments go live" note; properties with vetted badge + per-spot price/active state; a bookings ledger table with friendly state labels. Fixture demo (`SAMPLE_OWNER`) when unauthenticated/offline.
- `api.js`: `fetchOwnerDashboard` (via `apiGet`, read-cache key `owner-dashboard`). Six-locale `owner.*` keys added (**+21 → 229 keys/locale**).

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 287 passed** (was 284; +3: auth-required, live listing/bookings/payout, empty dashboard).
- UI: **vitest 92 passed** (+2: fixture-demo fallback, live listings/bookings/payout) · `vite build` clean · six-locale completeness at **229 keys**.
- **Live smoke:** `GET /owner/dashboard` → **401 without auth**, `{"payout_cents":0,"properties":[],"bookings":[]}` for a fresh authed account.

**All three §18 portals now live** (fleet, admin, public scorecard, owner) — the portal set is complete.

## 2. Decisions made (append to Decision Log)

144. **The owner's accrued payable is read straight off the F7 `owner_payable` ledger, not a new balance table.** The ledger is already the source of truth (booking credits owner_payable at book time, debits it on refund); `owner_payable_cents` just negates the credit balance. No duplicate money state — settlement (Stripe/Connect payout) will *debit* the same account when wired, so the figure stays correct through activation.
145. **The Property-Owner portal requires a session (unlike the public scorecard).** An owner's listings, bookings, and payable are private business data — `current_account`, not `meta.public`. It reuses the same portal-meta mechanism (`chrome:false, portal:true`) as fleet/admin.
146. **Portal trio → quartet, one mechanism confirmed at scale.** Driver app + four portal surfaces (fleet, admin, public scorecard, owner) live in one SPA/build, differentiated only by route meta and shared `ui/core` tokens. §18 portal set complete; no separate builds, no driver-screen imports into portals.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input):
- **Incident capture sheet** (M5-FR4) — small: kind + note → `/protection/incident` (idempotent, already wired). **Recommended next** (smallest closed gap).
- **Richer admin console** — analytics funnels + config editing (F14 `funnel`/`set_config` ready).
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`; approved-review snippets on the public scorecard; owner spot **CRUD** (add/pause a listing) — currently read-only.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6 booking charge + owner payout SETTLEMENT, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name. Flip these on in the admin console once gates are satisfied.

**Recommendation:** the **incident capture sheet** (M5-FR4) — the endpoint is live and idempotent; it just needs the driver-app sheet, closing the last M5 UI gap. Then the richer admin console (analytics + config), and owner spot CRUD to make the owner portal read-write.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **229 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**Property-Owner portal (login required):** http://localhost:9008/owner — listings, bookings, accrued payable. API `GET /owner/dashboard` (session). Other portals: `/fleet`, `/admin` (login), `/scorecard` (public).
Suite: **pytest 287 · vitest 92 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; offline fully a mode; five surfaces (driver app + fleet/admin/public-scorecard/owner portals — the §18 set is complete).** Hardening to date: owner portal (038), public scorecard (037), evidence-sync (036), admin console (035), M5 capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3, led by the incident capture sheet.

## 8. Commits this session (local only, never pushed)

`3483742` HANDOFF-037 → this session: Property-Owner portal (+ this handoff). **102 commits** on `main`, never pushed.

*— End of session. Next: the incident capture sheet (M5-FR4, endpoint live), then the richer admin console and owner spot CRUD. Activation seams await owner/BD inputs (§4).*
