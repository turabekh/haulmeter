# HANDOFF-048 — Ownership gate on all stop-scoped load endpoints (authz fix)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live and browser-reachable via /dev, active-load lifecycle resumable + closable + owner-gated, offline fully a mode, admin console operational, M6 self-serve, two F13-config knobs live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–047 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-047)

Closes the **authz gap** surfaced by HANDOFF-047 (Decision 168): the stop-scoped load endpoints (`meter`, `arrive`, `notice`, `claim`) operated on a `stop_id` with **no ownership check** — any authenticated driver could read or drive another driver's load (a real IDOR: detention state, facility/counterparty, and mutating the M3 clock/claim). All of them are now gated to the load's owner.

### Backend — `api/app/api/load.py`
- Replaced `_stop_or_404` with **`_owned_stop(db, stop_id, account)`**: 404 if the stop doesn't exist, **403 if the load isn't the caller's** (`load.account_id != account.id`), else the stop.
- Applied to **every stop-scoped endpoint** — `GET /meter`, `POST /arrive`, `POST /notice`, `POST /claim`, `POST /end` (the last already had an inline check, now unified through the helper). `GET /load/active` was already per-account.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 304 passed** (was 303; +1: every stop-scoped endpoint returns 403 for a non-owner, and the real owner still passes). The full-platform e2e and all existing single-owner flows stay green (the check is transparent to the legitimate owner).
- UI: **unchanged** this increment (backend authz only) — vitest still **100**, six locales at **261 keys**.
- **Live smoke:** owner `GET /meter` → 200; a second account → **403** on both `/meter` (read) and `/arrive` (mutation).

## 2. Decisions made (append to Decision Log)

169. **Ownership is enforced at the API layer via one helper, keyed by `load.account_id`.** A stop belongs to a load which belongs to an account; `_owned_stop` resolves stop→load and compares to the caller. Centralizing it in one helper (rather than per-endpoint inline checks) means every current and future stop-scoped route gets the same 404-then-403 semantics. 404 precedes 403 so a missing stop reads as not-found regardless of caller.
170. **This was a genuine IDOR, not a theoretical one.** Before this, a driver holding any other driver's `stop_id` could pull their detention Meter (facility, counterparty, dollars owed) and even fire `arrive`/`notice`/`claim` on it. The fix is data-isolation-positive and has no effect on the legitimate owner. A broader audit of other stop/ID-scoped endpoints across modules (e.g. M5 condition/incident by capture_id, M3/M4 by claim/receivable id) is worth a dedicated pass — noted below.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input):
- **Authz audit across other ID-scoped endpoints** — sweep M5 (condition/incident), M3/M4 (claim/receivable), M6 booking, M9/M11 for the same IDOR pattern and gate by owner. **Recommended next** (finishes the data-isolation posture the load fix started).
- **More F13-config seams** — M3 free-time/rate default, M10 `REDEEM_CENTS_PER_POINT`/`RATE_LIMIT_PER_DAY`.
- Small polish: approved-review snippets on the public scorecard; fold moderation decisions into the audit feed; **gate `/dev` behind a dev-mode flag before any deploy**.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), brand name.

**Recommendation:** the **authz audit across other ID-scoped endpoints** — the load fix proved the pattern; sweeping the rest (M5 capture/incident, M3/M4 receivables, M6 bookings) closes the same class of gap platform-wide before any activation. High-integrity, and each is the same one-helper-plus-check shape.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · locale native review (F15, gate green at **261 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Stop-scoped load endpoints (`/load/{stop}/meter|arrive|notice|claim|end`) now require the caller to own the load (403 otherwise). No change for the legitimate driver.
Suite: **pytest 304 · vitest 100 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live and browser-reachable via /dev; active-load lifecycle resumable, closable, and owner-gated; integration e2e green; offline fully a mode; five product surfaces + a dev directory; admin console operational with full accountability; M6 marketplace self-serve; two F13-config knobs live; fleet claims desk shows broker names.** Hardening to date: load authz gate (048), end-load (047), GET /load/active (046), dev directory + counterparty names (045), M10 earn config (044), audit-log view (043), owner spot CRUD (042), config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`028618d` end-load → this: load ownership gate (+ this handoff). **113 commits** on `main`, never pushed.

*— End of session. Next: authz audit across other ID-scoped endpoints (M5/M3/M4/M6), then M3 config seam / small polish. Activation seams await owner/BD inputs (§4).*
