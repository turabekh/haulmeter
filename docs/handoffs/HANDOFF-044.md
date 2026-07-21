# HANDOFF-044 — M10 earn rates wired to F13 config (the points economy is tunable)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, offline fully a mode, all three §18 web portals live, admin console operational with full accountability, M6 marketplace self-serve. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–043 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-043)

The **M10 points economy** is now operator-tunable: each contribution kind's earn rate reads the F13 config registry live, with the compiled `EARN_RULES` as fallback. This is the second "→ F13 config" seam (after the M6 take rate, HANDOFF-041), applying the same proven pattern — and it satisfies the PRD §8.10 DoD line that the economy parameters are "F13-config tunable at activation."

### Backend — `m10_community/domain/service.py`
- New `CONFIG_EARN_PREFIX = "m10_earn_"` and `_earn_points(db, kind)` → `int(flags.get_config(db, f"m10_earn_{kind}", EARN_RULES.get(kind, 0)))` — a **per-kind** key (`m10_earn_review`, `m10_earn_handoff`, `m10_earn_answer`), each a scalar that fits the admin config editor's inline numeric input.
- `award_contribution(...)` now resolves points via `_earn_points` instead of reading `EARN_RULES` directly. Every earn path (review, handoff-relay both sides, Q&A answer) picks up the live rate automatically.
- `CONFIG_EARN_PREFIX` exported via `m10_community.public` (import-linter clean; F13 import is a function-local `public` import, foundation ← module — no boundary change).

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 298 passed** (was 297; +1: a configured `m10_earn_review=25` is awarded instead of the 15 default, while an un-configured kind keeps its compiled default).
- UI: **unchanged** this increment (backend wiring only) — vitest still **97**, six locales at **261 keys**.
- **Live smoke** (seeded admin): `POST /admin/config {m10_earn_review: 25, scope: rewards}` → M10's `_earn_points(db, "review")` resolves **25** (default 15); `handoff` still resolves **10** (un-configured). The knob is set in the admin console and read by the award path — audited in the HANDOFF-043 log.

## 2. Decisions made (append to Decision Log)

161. **Earn rates are per-kind scalar config keys (`m10_earn_<kind>`), not one JSON blob.** A single `m10_earn_rules` dict would be one knob but the admin config editor edits scalars inline (numeric coercion) — a dict value renders as `[object Object]` and can't be edited there. Per-kind keys keep each rate a first-class, editable, individually-audited value. The compiled `EARN_RULES` remains the fallback for any kind without a config row.
162. **`_earn_points` reads config per award, not cached.** Each `award_contribution` resolves the current config value, so an operator's change applies to the very next contribution with no restart or cache bust — the same immediacy as the M6 take-rate knob. Contribution volume is low enough that the extra `get_config` (a single PK lookup) is negligible.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input):
- **Wire the last obvious F13-config seams** — M3 detention free-time default / rate default, or the M10 `RATE_LIMIT_PER_DAY` and `REDEEM_CENTS_PER_POINT`. Each is the same small pattern. **Recommended next** (finish making the tunable activation params actually tunable), or stop here if the two exemplars (M6 take rate, M10 earn) are enough to demonstrate the pattern.
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`; approved-review snippets on the public scorecard; fold moderation decisions into the audit feed.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6 booking charge + owner payout SETTLEMENT, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), brand name. Flip these on in the admin console once gates are satisfied. **M10 params→F13 is now partly done** (earn rates); redeem rate + rate-limit remain if desired.

**Recommendation:** either finish the remaining config seams (M10 `REDEEM_CENTS_PER_POINT` / `RATE_LIMIT_PER_DAY`, M3 free-time) for completeness, or pivot to the small backend-polish items (counterparty names, `GET /load/active`) which improve existing surfaces. Both are low-risk; pick by preference.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · locale native review (F15, gate green at **261 keys**). M10 economy params are now partly F13-tunable (earn rates live).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**Live earn knob:** in `/admin` (platform_admin) set config `m10_earn_review` (scope `rewards`) → the next review contribution earns that many points; the change shows in the audit log. Defaults: review 15, handoff 10, answer 5.
Suite: **pytest 298 · vitest 97 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; offline fully a mode; five surfaces (driver app + fleet/admin/public-scorecard/owner portals); admin console operational with full accountability; M6 marketplace self-serve; two F13-config knobs live (M6 take rate, M10 earn rates).** Hardening to date: M10 earn config (044), audit-log view (043), owner spot CRUD (042), config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`1375a72` audit-log view → this session: M10 earn rates → F13 config (+ this handoff). **108 commits** on `main`, never pushed.

*— End of session. Next: finish the remaining F13-config seams (M10 redeem/rate-limit, M3 free-time) or pivot to small backend polish (counterparty names, GET /load/active). Activation seams await owner/BD inputs (§4).*
