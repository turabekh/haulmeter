# HANDOFF-042 — Owner spot CRUD (the Property-Owner portal is now read-write)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, offline fully a mode, all three §18 web portals live, admin console operational, first F13-config knob live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–041 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-041)

The **Property-Owner portal** (HANDOFF-038) went from read-only to a **self-serve supply-side workspace**: an owner can create a listing, add spots, re-price them, and pause/resume them (M6-FR1) — giving the take-rate knob (HANDOFF-041) real inventory to price.

### Backend
- **M6 domain** (`m06_parking/domain/service.py`): new `get_property`, `get_spot`, and `update_spot(db, spot, price_cents_per_night=None, active=None)` — re-price and/or pause a listing. A paused spot drops out of `bookable_near` (which filters `active`) but keeps its history. Exported via `m06_parking.public` (import-linter clean, 29/29).
- **`/owner` API** (`api/app/api/owner.py`), all session-required and **ownership-enforced**:
  - `POST /owner/property` — create a listing (starts un-vetted; vetting is a platform step).
  - `POST /owner/property/{id}/spot` — add a spot.
  - `PATCH /owner/spot/{id}` — re-price and/or pause/resume.
  - Ownership helpers `_owned_property` / `_owned_spot` return **403** if the property (or the spot's parent property) isn't the caller's — a spot's ownership is checked via its parent.

### UI — `OwnerPortalSurface` (`/owner`)
- Read-write when live: an **add-property** form (name + lat/lon), a per-listing **add-spot** row, an inline **$ price input** (re-price on change → PATCH with cents), and a **Pause/Resume** button. The **fixture demo stays strictly read-only** (write controls are `v-if="!demo"`; a "sign in to manage" note shows). Money Mono/tabular. Six-locale `owner.*` keys added (**+10 → 256 keys/locale**).

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 295 passed** (was 292; +3: create→add→reprice→pause round-trips on the dashboard, cross-owner 403, write requires auth).
- UI: **vitest 97 passed** (+1: create property → add spot → reprice → pause, asserting the POST/PATCH bodies; the live-view price assertion updated to the editable input) · `vite build` clean · six-locale completeness at **256 keys**.
- **Live smoke:** Alice creates a property, adds spot A1, re-prices to $26 + pauses → round-trips on her dashboard (`active:false`, `2600`); **Bob PATCHing Alice's spot → 403**.

## 2. Decisions made (append to Decision Log)

156. **Spot ownership is enforced through the parent property, not a denormalized owner column on the spot.** `ParkingSpot` has no `owner_account_id`; `_owned_spot` loads the spot, then checks `_owned_property(spot.property_id)`. One source of truth for ownership (the property), no denormalization to keep in sync.
157. **Pause is a soft state (`active=False`), not a delete.** Owners pause/resume rather than remove listings; a paused spot leaves `bookable_near` (it filters `active`) but keeps its bookings/history and can be resumed. No delete endpoint — the marketplace never loses a spot's record, and there's no cascade to reason about.
158. **The owner portal's write controls are gated on live mode; the demo is read-only.** The fixture demo (unauthenticated/offline) can't write, so `v-if="!demo"` hides every form/button and shows a "sign in to manage" note. The portal is honest about when it's a demo vs. a live workspace — no dead buttons.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input):
- **Admin audit-log view** — surface `admin.list_actions` in the console (who changed which flag/config, when); the data's already written (config_set + flag toggles). **Recommended next** (small, completes the admin cockpit's accountability story).
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`; approved-review snippets on the public scorecard; wire more "→ F13 config" seams using the HANDOFF-041 pattern (M3 thresholds, M10 point values).

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6 booking charge + owner payout SETTLEMENT, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name. Flip these on in the admin console once gates are satisfied.

**Recommendation:** the **admin audit-log view** — flag toggles and config edits already write `AdminAction` rows; surfacing `list_actions` in the console closes the accountability loop (every operator mutation is visible) and is a small, self-contained increment. Then continue wiring config seams.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **256 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**Owner portal (self-serve):** http://localhost:9008/owner (login) → add a property (name + lat/lon), add spots, re-price inline, Pause/Resume. APIs: `POST /owner/property`, `POST /owner/property/{id}/spot`, `PATCH /owner/spot/{id}` (session + ownership-gated).
Suite: **pytest 295 · vitest 97 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; offline fully a mode; five surfaces (driver app + fleet/admin/public-scorecard/owner portals); admin console operational; M6 marketplace fully self-serve (owner CRUD + live take-rate knob).** Hardening to date: owner spot CRUD (042), config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3, led by the admin audit-log view.

## 8. Commits this session (local only, never pushed)

`33db780` config consumer → this session: owner spot CRUD (+ this handoff). **106 commits** on `main`, never pushed.

*— End of session. Next: the admin audit-log view (surface list_actions), then more F13-config seams and small backend polish. Activation seams await owner/BD inputs (§4).*
