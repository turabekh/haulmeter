# HANDOFF-021 — F1 Login UI + session gate (the live-API switch)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete. **M1–M8 built**; **F1 driver login UI now landed**. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–020 (M1–M8).

---

## 1. What now exists and passes (delta since HANDOFF-020)

**New: F1 driver login/register UI + a session gate.** The driver app had been running unauthenticated (fixtures only); the live M6/M7/M8 APIs existed but nothing hit them. This lands the onboarding surface + session layer, so the app now runs against the **live backend behind a real F1 session** — the top-leverage fold-in flagged in HANDOFF-020 §4.

- **api.js session layer:** the F1 bearer token + account_id + email persist to **localStorage** (a session survives reload — a phone app the driver doesn't re-log every trip). Exposes `isAuthenticated`, `account`, `email`, `register()`, `login()`, `logout()`. Requests still fall back to fixtures when they fail offline (design-prd §15.1).
- **AuthSurface** (`/login`): a **full-screen onboarding flow** (NAV-3), email/password only, **no activation step** (PRD §7.1 — onboard in under 60 s). §202 form (56 dp inputs, labels above, one primary CTA), errors specific + unblaming (§12.4). Login ⇄ Create-account toggle.
- **Router auth guard** (`installAuthGuard`): no session → `/login`; signed in → never sit on `/login`; `/login` carries `meta.chrome:false` so **App.vue hides the tab shell** for the flow.
- **MoreSurface** replaces the `/more` placeholder: account email + **Log out** (clears the session → `/login`).

### Verified this session
- **Live smoke test** (against the running stack): `POST /auth/register` → token → authenticated `/map/overlay` and `/fuel/analytics` return **200**; unauthenticated `/map/overlay` returns **401**. The login surface now turns M6 booking, M7 fuel, and M8 intel live in-app.
- UI: **vitest 67 passed** (was 61; +6: login success/persist, unblaming error, login⇄register toggle, guard redirect, guard allow, MoreSurface logout) · `vite build` clean · six-locale completeness at **100 keys**.
- Backend untouched: **pytest 224** still green (sanity).

## 2. Decisions made (append to Decision Log)

79. **The app is gated behind F1 auth; the session persists to localStorage.** A driver signs in once; the token survives reload. This flips the default from "unauthenticated fixtures" to "live APIs behind a session", while keeping fixtures as the **offline fallback** (§15.1) — not the primary path.
80. **Login is a full-screen flow with no tab chrome** (`route.meta.chrome:false`, NAV-3 onboarding). App.vue reads the meta to suppress StatusStrip + TabBar; the same hook is reusable for any future full-bleed flow.
81. **Brand string "LONGHAUL" shown on the login header as a placeholder.** design-prd does not lock a brand name (still a §4 open seam); using the codename is the smallest reversible choice — swap when the owner sets the brand.
82. **`register()` needs no email-verification/activation** (PRD §7.1). The F1 backend already attaches the driver role + issues a session on register; the UI mirrors that — create-account is a single submit.

## 3. Exact next task

**Resume module order → M9.** Plan **M9 — Financial Rails / earnings** (PRD §8.9 — verify the exact title/FRs against the PRD before building), plan-first:
- **Earnings dashboard / North Star (Driver Dollars Delivered):** dollars recovered (M3/M4) + dollars saved (M7 fuel) in one view; the Money tab already shows recovered + fuel-saved — M9 completes it.
- **IFTA-ready fuel export** (the M7-FR4 hook lands here); settlement/document handling on F6; earnings rollups on F7.
- Backend `m09_money` (imports foundation + earlier module publics). F13 flag. Then UI — an earnings/DDD surface.

**Fold-in follow-ups (owner priority):** **Mapbox token**, active-load API, **offline read-cache (F12)**, **M8 sleep-solver UI**, M5 capture flows, M6/M7 owner portals, brand name.

## 4. Blockers / owner questions

1. **Brand name** — "LONGHAUL" is the codename placeholder on the login header; owner to set the real brand (design-prd §4 seam).
2. **Fuel payment-partner + merchant agreements + spread ¢/gal** (M7 activation).
3. **Stripe/Connect structure + take rate; refund/damage-liability posture** (M6 activation).
4. **Mapbox token** (M1 live tiles). **Collection-partner + legal sign-off** (M3/M4 activation).
5. **Locale wording** — new F1 auth strings (12 keys × 6 locales) native review pending (F15); completeness gate green at **100 keys**.
6. Standing seams: timestamping/PDF (F4), Twilio/FCM/email (F8), model keys + budgets + embedding dim (F9), MinIO bucket (F6).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged. (`API_BASE` in `ui/src/core/api.js` remains the LOCKED `http://localhost:8008`.)

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 → **now opens on `/login`** (register or log in; dev API is live) → Map · `/facility/:id` · `/book/:spotId` · `/fuel/:stationId` · `/load` · `/load/calc` · `/money` · `/docs` · **`/more`** (account + log out). API http://localhost:8008 (`/auth/*`, `/map/*`, `/facility/*`, `/detention/*`, `/accessorial/*`, `/protection/*`, `/parking/*`, `/fuel/*`, `/intel/*`). Admin seed: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 224 · vitest 67 · 29 contracts · ruff clean**, migrations through `0020`.

## 7. Build progress

**Common Ground F1–F15: complete** (F1 now has its driver UI too). Modules: **M1–M8 done.** Next: **M9** → M10 → M11 → M12. The app now onboards a driver in one screen and runs live end-to-end.

## 8. Commits this session (local only, never pushed)

`15f084d` HANDOFF-020 → `b94454a` F1 login UI + session gate (+ this handoff). **59 commits** on `main`.

*— End of session. Next: plan M9 (Financial Rails / earnings — the DDD dashboard consuming M3/M4 recovered + M7 fuel savings, IFTA export), plan-first.*
