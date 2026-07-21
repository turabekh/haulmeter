# HANDOFF-041 — Config consumer wired (the take rate is now a live knob)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, offline fully a mode, all three §18 web portals live, admin console operational. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–040 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-040)

The runtime config editor built in HANDOFF-040 is no longer write-only: **M6's booking take rate now reads the F13 config registry live**, with the compiled constant as its fallback. This closes the loop the editor opened — an operator changes `m06_take_rate_bps` in the admin console (§21.8) and the next booking prices with it, no deploy. It's the reference implementation of the F13-config activation pattern for every "→ F13 config" seam.

### Backend — `api/app/modules/m06_parking/domain/service.py`
- New `CONFIG_TAKE_RATE_KEY = "m06_take_rate_bps"` and `_configured_take_rate(db)` → `int(flags.get_config(db, CONFIG_TAKE_RATE_KEY, DEFAULT_TAKE_RATE_BPS))`.
- `book(...)` now defaults `take_rate_bps=None`; when unset it resolves the **live config rate** (falling back to the compiled default). An explicit argument still overrides — callers can force a rate; tests and future flows keep that control.
- `CONFIG_TAKE_RATE_KEY` exported via `m06_parking.public` (import-linter clean; the F13 import is a function-local `public` import, foundation ← module, no boundary change).

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 292 passed** (was 291; +1: config knob honored → take = 10% of price when set to 1000 bps, explicit arg still overrides at 2000 bps).
- UI: **unchanged** this increment (backend wiring only) — vitest still **96**, six locales at **246 keys**.
- **Live smoke** (against the dev DB, where the admin console set `m06_take_rate_bps=1500` in HANDOFF-040): `m6._configured_take_rate(db)` resolves to **1500 bps**, not the compiled default 1750 — the booking path reads the operator-set value.

## 2. Decisions made (append to Decision Log)

153. **`book()` resolves the take rate from F13 config when the argument is unset (`None`), not via a module default constant.** Python default args evaluate once at import, so a live config value can't be a default; `take_rate_bps=None` + in-body resolution gives "config unless explicitly overridden." Every current caller (API, M10, tests) used the default, so they all pick up the live rate automatically; the override path stays for anything that must pin a rate.
154. **`get_config` is keyed by name, scope is metadata.** `ConfigEntry.key` is the primary key, so `get_config(db, "m06_take_rate_bps")` returns the value regardless of the scope it was written under; the admin console writes it under `pricing` for organization, but the consumer doesn't filter by scope. If scoped lookups are ever needed, `get_scope` already exists.
155. **This is the template for the remaining "→ F13 config" seams.** Any activation parameter (M3 thresholds, M10 point values, notice timing) follows the same shape: a `CONFIG_*_KEY` constant, an `int(flags.get_config(..., DEFAULT))` resolver, and an argument default of `None`. The config editor + audit log already exist, so wiring a new knob is now backend-local.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input):
- **Owner spot CRUD** — make the Property-Owner portal read-write (add a property, add/pause a spot, edit nightly price); currently read-only. **Recommended next** (turns the owner portal into a working supply-side workspace and gives the take-rate knob real inventory to price).
- **Admin audit-log view** — surface `admin.list_actions` in the console (who changed which flag/config, when); the data's already being written.
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`; approved-review snippets on the public scorecard.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name. Flip these on in the admin console once gates are satisfied.

**Recommendation:** **owner spot CRUD** — the Property-Owner portal (HANDOFF-038) is read-only and the take-rate knob (this session) needs listings to price. Owner-side create/edit endpoints (`POST /owner/property`, `POST /owner/property/{id}/spot`, `PATCH /owner/spot/{id}`) on the existing M6 publics, plus the portal UI, make the marketplace supply side fully self-serve. Then the admin audit-log view.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **246 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**Live take-rate knob:** in `/admin` (platform_admin) set config `m06_take_rate_bps` (scope `pricing`) → the next M6 booking prices with it. Default remains 1750 bps (17.5%) when unset.
Suite: **pytest 292 · vitest 96 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; offline fully a mode; five surfaces (driver app + fleet/admin/public-scorecard/owner portals); admin console operational; first F13-config knob live (M6 take rate).** Hardening to date: config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3, led by owner spot CRUD.

## 8. Commits this session (local only, never pushed)

`94e4f15` richer admin console → this session: config consumer wired (+ this handoff). **105 commits** on `main`, never pushed.

*— End of session. Next: owner spot CRUD (make the Property-Owner portal read-write), then the admin audit-log view. Activation seams await owner/BD inputs (§4).*
