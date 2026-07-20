# HANDOFF-031 — Full-platform synthetic e2e (the twelve modules hold as one product)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–030 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-030)

A **full-platform synthetic end-to-end** test now exercises **all twelve modules through their public interfaces only**, as one driver's day — the counterpart to the Common Ground e2e (F1–F9/F12), now for M1–M12.

### `api/tests/e2e/test_full_platform_e2e.py`
One flow, one assertion chain:
1. **register all modules** (M1–M12 `register_module` — F13 flags + F14 admin views + F9 prompts together).
2. **F1/F2** owner-operator + facilities → **M1** map overlay shows them.
3. **M6** book a spot — the F7 ledger stays balanced (take + payout = price).
4. **M7** fuel net price on the corridor → pump code → settle → driver saved $25.
5. **Load loop (F5/F3/M3)**: arm → geofence ENTER (arrival) → EXIT (departure) → `start_claim` → `generate_pack` = **$75 detention, receivable opened** → transitioned to **recovered** (collected).
6. **M2/M8**: the receiver's dwell history → `detention_risk_flag` (100% exceed) + `true_profit` (M7 fuel + expected detention) + `where_to_sleep`.
7. **M9**: an owed layover the settlement missed → **audit flags $200** → **DDD = recovered $75 + fuel $25 + flagged $200** (the North Star reflects the whole day).
8. **M10**: earn points → **spot handoff** broadcast → claim → confirm (both earn on arrival).
9. **M11**: `route("what am I owed")` → `money_owed`; English ghostwriter draft.
10. **M12**: create fleet + consent → **fleet report rolls up the driver's recovered $75**; data benchmark **suppressed below the privacy floor** (1 sample); TMS `push_load`.

### Verified this session (in compose)
- **pytest 276 passed** (was 275; +1 the full-platform e2e) · `ruff` clean · `lint-imports` **29/29 KEPT**.
- No UI/migration change (test-only session): vitest unchanged at 81, migrations at `0023`.

## 2. Decisions made (append to Decision Log)

118. **The full-platform e2e composes publics, not HTTP.** Like the Common Ground e2e, it wires modules exactly as a caller would (`m*.public`), so it proves the *integration contract* (public surfaces compose into a coherent product) rather than the transport. Deterministic, fast (~1.4s), and it breaks loudly if any module's public shape drifts.
119. **The e2e's spine is the North Star.** The flow is arranged so the final `earnings_dashboard` (DDD) equals recovered (M3→ledger) + fuel saved (M7) + audit-flagged (M9) — a single number that can only be right if the detention loop, the fuel economics, and the auditor all worked. One assertion that transitively validates most of the platform.
120. **The e2e asserts the privacy floor, not a leak.** With one dwell sample, `dwell_benchmark` returns `None` (suppressed) — the test locks in that the data product never publishes below `MIN_BENCHMARK_SAMPLE`, so a future change that weakens the floor fails here.

## 3. Exact next task — continue the backlog

With every surface live and an integration e2e in place, remaining work is **cross-cutting hardening** (no owner input):
- **Offline read-cache (F12)** across Map/Docs/Booking/Fuel/Voice/Load/Fleet — the last big product-quality gap (design-prd §15.1: offline is a mode, not an error). **Recommended next.**
- **M5 condition-capture / incident flows** (camera-first capture; backend shipped since HANDOFF-017).
- **The other two web portals** (Property-Owner, Public Scorecard, §18) — reuse the `meta.portal` pattern.
- Small backend polish: resolve counterparty **names** in the fleet claims desk; a `GET /load/active` so the Load tab recovers its stop without localStorage.
- **A UI e2e** (Playwright-style) is out of scope without a browser harness; the vitest component suite + this backend e2e cover the seams.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name.

**Recommendation:** **offline read-cache (F12)** — the driver app's defining constraint is intermittent connectivity, and F12 (the offline foundation) is built but the UI surfaces don't yet cache reads. Wiring it makes the whole app usable in a dead zone, which is the product's core promise.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **171 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

`make test` runs both e2e suites (Common Ground F1–F9/F12 + full-platform M1–M12) inside the api container alongside the module tests.
Suite: **pytest 276 · vitest 81 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green.** Post-build hardening to date: full-platform e2e (031), fleet portal live (030), relay UI (029), detention loop closed (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog is cross-cutting hardening (§3), led by offline read-cache (F12).

## 8. Commits this session (local only, never pushed)

`4bbee8f` HANDOFF-030 → `3fa51d3` full-platform e2e (+ this handoff). **88 commits** on `main`, never pushed.

*— End of session. Next: offline read-cache (F12) across the driver surfaces (the app's core promise — usable in a dead zone), then M5 capture flows and the remaining §18 portals. Activation seams await owner/BD inputs (§4).*
