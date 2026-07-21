# HANDOFF-052 — M3 detention terms wired to F13 config (third knob)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, full authz posture, dev tooling excluded from prod, offline fully a mode, admin console operational, M6 self-serve, three F13-config knobs live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–051 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-051)

The **default detention terms for a new load** — free time and rate — are now operator-tunable via F13 config, with the design-prd §9 industry standard (2h free / $75/h) as the fallback. This is the third "→ F13 config" seam (after M6 take rate and M10 earn rates), and the one closest to the money: it sets what every driver's Meter counts down from and accrues at when they don't specify terms.

### Backend
- **M3 domain** (`m03_detention`): new `DEFAULT_FREE_TIME_MINUTES = 120`, `DEFAULT_RATE_CENTS_PER_HOUR = 7500`, keys `CONFIG_FREE_TIME_KEY = "m03_free_time_minutes"` / `CONFIG_RATE_KEY = "m03_rate_cents_per_hour"`, and resolvers `default_free_time_minutes(db)` / `default_rate_cents_per_hour(db)` → `int(flags.get_config(db, KEY, DEFAULT))`. Exported via `m03_detention.public` (import-linter clean; F13 import is a function-local `public` import — no boundary change).
- **`POST /load`** (`api/app/api/load.py`): `CreateLoadIn.free_time_minutes` / `rate_cents_per_hour` are now `int | None = None`; when omitted the endpoint resolves the **live M3-config defaults** (M3 owns detention-term semantics). An explicit value in the request still overrides.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 306 passed** (was 305; +1: unset terms → 120 default; after `set_config(m03_free_time_minutes=60, m03_rate_cents_per_hour=9000)` a new load's Meter reads 60/9000; an explicit `free_time_minutes: 180` still overrides).
- UI: **unchanged** — vitest **101**, six locales at **261 keys**.
- **Live smoke** (seeded admin): a new load defaults to free 120 / rate 7500; after the admin sets `m03_free_time_minutes=90` + `m03_rate_cents_per_hour=9000`, the next load's Meter reads free 90 / rate 9000.

## 2. Decisions made (append to Decision Log)

178. **M3 owns the detention-term defaults; the API resolves them when the request omits terms.** The 120/7500 defaults previously lived as literals on the API `CreateLoadIn` model. Pydantic class defaults can't read live config, so the fields became `None` and the endpoint resolves via `m3.default_free_time_minutes(db)` / `default_rate_cents_per_hour(db)`. Semantics live in the detention module (design-prd §9), not the transport layer; an explicit request value still wins.
179. **Three config knobs now share one pattern and one editor.** M6 take rate (`pricing`), M10 earn rates (`rewards`), and M3 detention terms (`detention`) all follow `CONFIG_*_KEY` + `int(get_config(..., DEFAULT))` + `None`-means-config, edited in the same F14 admin console and captured in the same audit log. `PRE_DETENTION_THRESHOLD` / `DUNNING_DAYS` remain compiled (still marked "→ F13 config") and can follow the same shape if an operator ever needs them live.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input) — security, dev-safety, and the money-critical config seams are done; what's left is small polish:
- **Public-scorecard review snippets** — surface a few approved review excerpts (M2, aggregate-safe) on the public scorecard, enriching the only outward-facing surface. **Recommended next**.
- **Fold moderation decisions into the admin audit feed** — moderation approvals/rejections already carry a moderator; surface them alongside flag/config actions.
- Optional remaining config seams: M10 `REDEEM_CENTS_PER_POINT`/`RATE_LIMIT_PER_DAY`, M3 `PRE_DETENTION_THRESHOLD`/`DUNNING_DAYS`.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), brand name.

**Recommendation:** the **public-scorecard review snippets** — it improves the outward-facing surface (the public face of the platform) and is a small, aggregate-safe read. Then fold moderation into the audit feed.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · locale native review (F15, gate green at **261 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**Live detention-terms knob:** in `/admin` (platform_admin) set `m03_free_time_minutes` / `m03_rate_cents_per_hour` (scope `detention`) → the next load created without explicit terms uses them; the change is in the audit log. Defaults: 120 min free / 7500¢ ($75)/h.
Suite: **pytest 306 · vitest 101 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; full authz posture; dev tooling excluded from prod; integration e2e green; offline fully a mode; five product surfaces + a dev-only directory; admin console operational; M6 self-serve; three F13-config knobs live (M6 take rate, M10 earn, M3 detention terms).** Hardening to date: M3 terms config (052), gate /dev (051), fleet membership gate (050), M3/M5 authz sweep (049), load authz gate (048), end-load (047), GET /load/active (046), dev directory + counterparty names (045), M10 earn config (044), audit-log view (043), owner spot CRUD (042), config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`0fde6af` gate /dev → this: M3 detention-terms config (+ this handoff). **117 commits** on `main`, never pushed.

*— End of session. Next: public-scorecard review snippets, then fold moderation into the audit feed. Activation seams await owner/BD inputs (§4).*
