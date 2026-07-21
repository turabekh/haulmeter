# HANDOFF-050 — M12 fleet membership gate (authz sweep complete)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live and browser-reachable via /dev, all known IDORs closed, offline fully a mode, admin console operational, M6 self-serve, two F13-config knobs live. Post-build hardening (security). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–049 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-049)

Closes the **last open IDOR** from the audit — and the most financially sensitive: the M12 fleet endpoints (`report`, `claims`, `invite`) had **no membership check**, so any authenticated user could read any fleet's money + roster or invite drivers to it. They're now gated to **fleet management (owner/dispatcher)**.

### Backend
- **M12 domain** `member_role(db, fleet_org_id, account_id) -> FleetRole | None` — the account's role if an **active** member of the fleet, else None. Exported via `m12_fleet.public`.
- **`api/app/api/m12_fleet.py`** `_require_manager(db, fleet_id, account)` — 403 unless the caller is an active **owner or dispatcher** of that fleet. Applied to `GET /{fleet}/report`, `GET /{fleet}/claims`, `POST /{fleet}/invite`. (`GET /fleet/mine` and `POST /fleet` stay open — they're the caller's own.)

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 305 passed** (+1: report/claims/invite return 403 for a non-member; the owner still passes). Existing owner-flow tests unchanged (owner = management).
- UI: **vitest 100 passed** (unchanged — the Fleet Workspace is used by the fleet owner, who is management) · six locales at **261 keys**.
- **Live smoke:** owner `GET /fleet/{id}/report` → 200; an outsider → **403** on `/report` and `/claims`.

## 2. Decisions made (append to Decision Log)

174. **Fleet-wide money + roster is management-only (owner/dispatcher), not every member.** The report/claims desk shows per-member recovered/owed across the whole fleet — a regular driver member seeing every colleague's financials is itself a privacy problem, so the gate is management roles, not "any active member." A driver uses the phone app; the Fleet Workspace is a §18 manager portal. `invite` (a membership mutation) is likewise management-only.
175. **The authz sweep is complete: every private, ID-scoped endpoint is owner/role-gated; shared facility data stays open.** Closed across 048–050: load (meter/arrive/notice/claim/end), M3 detention (clock/pack), M5 protection (condition-photo/summary), M12 fleet (report/claims/invite). Facility-keyed community/aggregate endpoints (m02 reviews, m08 risk, m10 Q&A, m12 benchmark, public scorecard) remain readable by design. Owner portal + admin were already gated. No known IDOR remains.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input) — security posture is now complete; what's left is polish/features:
- **More F13-config seams** — M3 free-time/rate default, M10 `REDEEM_CENTS_PER_POINT`/`RATE_LIMIT_PER_DAY` (the HANDOFF-041 pattern). **Recommended next** (small, each makes another activation param a live audited knob).
- Small polish: approved-review snippets on the public scorecard; fold moderation decisions into the audit feed; **gate `/dev` behind a dev-mode flag before any deploy**; a `member_role`-based gate could later let dispatchers (not just owners) manage — already supported.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), brand name.

**Recommendation:** with the security sweep done, pivot back to **F13-config seams** (M3 free-time is the next high-value knob) or the small polish items (gate `/dev`, scorecard snippets). All low-risk.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · locale native review (F15, gate green at **261 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Fleet `report`/`claims`/`invite` now require the caller to be an owner/dispatcher of that fleet (403 otherwise). The Fleet Workspace (`/fleet`) is used by the owner, so no UX change.
Suite: **pytest 305 · vitest 100 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live and browser-reachable via /dev; full authz posture (all private ID-scoped endpoints owner/role-gated, no known IDOR); integration e2e green; offline fully a mode; five product surfaces + a dev directory; admin console operational; M6 self-serve; two F13-config knobs live.** Hardening to date: fleet membership gate (050), M3/M5 authz sweep (049), load authz gate (048), end-load (047), GET /load/active (046), dev directory + counterparty names (045), M10 earn config (044), audit-log view (043), owner spot CRUD (042), config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`a1a2216` M3/M5 authz sweep → this: M12 fleet membership gate (+ this handoff). **115 commits** on `main`, never pushed.

*— End of session. Security sweep complete. Next: F13-config seams (M3 free-time) or small polish (gate /dev, scorecard snippets). Activation seams await owner/BD inputs (§4).*
