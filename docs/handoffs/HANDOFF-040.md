# HANDOFF-040 — Richer admin console (North Star funnel + runtime config)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, offline fully a mode, all three §18 web portals live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–039 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-039)

The **admin console** went from a flags/moderation panel to a real operator cockpit: it now shows the **North Star detention funnel** (live analytics) and a **runtime config editor** (F13 config registry, every change audited). This required instrumenting the funnel at the real load lifecycle — previously only `map_open` was emitted.

### Backend
- **Funnel instrumentation** (`api/app/api/load.py`): the detention value loop now emits F14 analytics events at its three real milestones — `load_added` (create load), `arrived` (geofence ENTER starts the clock), `claim_sent` (filed GPS-backed claim), all module `m03`, attributed to the account.
- **`GET /admin/analytics`** — the North Star funnel via `admin.funnel(db, ["load_added","arrived","claim_sent"], module="m03")` (per-account, monotonic-step drop-off) + top-line `count_events` totals. Event keys only; labels are i18n'd on the frontend.
- **`GET /admin/config?scope=`** — the F13 config scope as `{scope, entries}` (via `flags.get_scope`).
- **`POST /admin/config`** `{key, value, scope}` — `flags.set_config`, then an **F14 audit-log entry** (`admin.record_action("config_set", actor=…, detail={key,scope,value})`) so every runtime change is attributed. All three new endpoints are `platform_admin`-gated.

### UI — `AdminConsoleSurface` (`/admin`)
- **Funnel panel:** each step as a bar (width relative to step 1) with its count and the **conversion % from the previous step** (where drop-off happens).
- **Config panel:** a scope field, editable value rows (change → POST, numeric coercion so `1500` stays an int), and an add-key row. Six-locale `admin.*` keys added (**+9 → 246 keys/locale**).

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 291 passed** (was 287; +4: funnel reflects real create→arrive→claim, funnel drop-off after step 1, config set/get + audited, analytics/config require admin).
- UI: **vitest 96 passed** (+1 net: funnel bars + conversion + config value render folded into the flags test, plus a new config-edit POST test) · `vite build` clean · six-locale completeness at **246 keys**.
- **Live smoke** (seeded admin `admin@longhaul.local`): `POST /admin/config` → round-trips via `GET`; driving a real load lifecycle (`/load` create→arrive→claim) → `GET /admin/analytics` shows funnel `[1,1,1]`.

## 2. Decisions made (append to Decision Log)

150. **The North Star funnel is instrumented at the API layer (load.py), not in the M3 domain.** The load lifecycle spans F5 (load/stop) + F3 (geofence) + M3 (clock/claim); the API endpoint is the one place that already composes them and maps 1:1 to the user milestones (create / arrive / file). Emitting there keeps the funnel = actual product usage and avoids threading F14 through multiple domains. `m01` already emits `map_open` from its domain; that stays.
151. **Runtime config edits are audited in the F14 admin log, config values live in the F13 registry.** Config is a flag-adjacent runtime concern (F13 `ConfigEntry`), but *who changed it* is an operator action (F14 `AdminAction`). Splitting them keeps each foundation's responsibility clean; the console's POST does both in one transaction.
152. **Config values are JSON with client-side numeric coercion.** `ConfigEntry.value` is a JSON column; the editor coerces a bare numeric string to a number (so `m06_take_rate_bps` stays `1500`, not `"1500"`) and leaves everything else as text. Activation params (take rates, thresholds) are now editable without a deploy — the seams that said "→ F13 config" can be wired to `get_config` next.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input):
- **Wire a real config consumer** — make M6's take rate (or an M3 threshold) read `flags.get_config` with the hardcoded constant as the default, closing the loop the config editor opens. **Recommended next** (turns the editor from write-only into a live knob).
- **Owner spot CRUD** — make the Property-Owner portal read-write (add/pause a listing/spot); currently read-only.
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`; approved-review snippets on the public scorecard; an admin **audit-log view** (surface `list_actions`).

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name. Flip these on in the admin console once gates are satisfied.

**Recommendation:** **wire a real config consumer** — have `m06_parking.book` read `flags.get_config("m06_take_rate_bps", scope="pricing")` defaulting to `DEFAULT_TAKE_RATE_BPS`. It makes the new config editor a live pricing knob and demonstrates the F13-config activation pattern end-to-end. Then owner spot CRUD.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **246 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**Admin console:** http://localhost:9008/admin (login as a `platform_admin`; dev seed `admin@longhaul.local` / `longhaul-admin-dev`). Feature flags, the **detention funnel**, **runtime config editor**, module views, moderation. APIs: `GET /admin/analytics`, `GET|POST /admin/config` (admin-gated).
Suite: **pytest 291 · vitest 96 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; offline fully a mode; five surfaces (driver app + fleet/admin/public-scorecard/owner portals); admin console operational (flags + funnel + config + moderation).** Hardening to date: richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3, led by wiring a real config consumer.

## 8. Commits this session (local only, never pushed)

`69986b4` incident sheet → this session: richer admin console (+ this handoff). **104 commits** on `main`, never pushed.

*— End of session. Next: wire M6's take rate to `flags.get_config` (make the config editor a live knob), then owner spot CRUD and an admin audit-log view. Activation seams await owner/BD inputs (§4).*
