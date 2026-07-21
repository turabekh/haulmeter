# HANDOFF-053 — Public-scorecard review snippets (approved + de-identified)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, full authz posture, dev tooling excluded from prod, offline fully a mode, admin console operational, M6 self-serve, three F13-config knobs live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–052 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-052)

The **Public Scorecard** now shows up to three review excerpts under "What drivers say" — **moderation-approved text only, de-identified** (no author, no date, nothing that identifies the driver). This enriches the only outward-facing surface while honoring §13. **It reverses logged Decision 142** ("rating + count only, no review text") — the owner explicitly approved the reversal (see §2 / §23 below) and chose the approved-and-de-identified option over showing any author identity.

### Backend — `GET /public/facility/{id}` (`api/app/api/public.py`)
- Adds `reviews: [text, …]`: the `.text` of `m2.list_reviews(db, facility_id, only_approved=True)`, non-empty, **capped at `PUBLIC_REVIEW_SNIPPETS = 3`**. Only the text string crosses the wire — no `account_id`, no timestamp. Pending/rejected reviews never appear (they aren't `approved`).

### UI — `PublicScorecardSurface`
- A "What drivers say" block renders the snippets as italic quotes. Fixture demo carries three sample de-identified excerpts. `score.what_drivers_say` added to all six locales (**262 keys**).

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 308 passed** (was 306; +2: only-approved + de-identified snippets — pending/rejected excluded, no ids in payload; and the 3-snippet cap).
- UI: **vitest 101 passed** (scorecard test extended: "What drivers say" + `.snip` excerpts render) · `vite build` clean · six-locale completeness at **262 keys**.
- **Live smoke** (no-auth public endpoint, fresh data): a facility with one approved + one pending review returns `reviews: ["Quick in and out, great staff."]` — approved only, pending excluded, no author/date in the payload.

## 2. Decisions made (append to Decision Log — and a §23 reversal)

180. **§23 REVERSAL of Decision 142: the public scorecard MAY show review text, restricted to moderation-approved + de-identified excerpts (≤3).** Decision 142 (HANDOFF-037) chose rating+count only to stay strictly aggregate. The owner explicitly requested review snippets and, when shown the §13 trade-off, chose "approved + de-identified" over any author-identifying option. The guardrails that make this honor §13: **only `ReviewStatus.approved` text** (human-moderated, so no abuse/PII slips through), **no author/date/id** in the payload, and a **hard cap of 3**. This supersedes 142; the "rating+count only" rule no longer holds for the public scorecard.
181. **De-identification is enforced by shape, not trust: the endpoint emits bare text strings.** `reviews` is `list[str]`, built by projecting `.text` off approved reviews — there is no field on the wire that could carry an account or timestamp, so a future edit can't accidentally leak identity without changing the response shape. The moderation gate (approved-only) is the content guardrail; the string-only projection is the identity guardrail.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input) — small polish only:
- **Fold moderation decisions into the admin audit feed** — moderation approvals/rejections already record a moderator; surface them alongside flag/config actions in `GET /admin/audit`. **Recommended next**.
- Optional remaining config seams: M10 `REDEEM_CENTS_PER_POINT`/`RATE_LIMIT_PER_DAY`, M3 `PRE_DETENTION_THRESHOLD`/`DUNNING_DAYS`.
- M2's `REVIEW_POINTS` is still a literal marked "→ F13 config later" — a candidate knob.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), brand name.

**Recommendation:** **fold moderation into the audit feed** — it completes the admin accountability story (every operator content decision visible) and is a small read-side change; `decide_moderation` already writes the moderator + reason.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · locale native review (F15, gate green at **262 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**Public scorecard:** http://localhost:9008/scorecard (no login) → search a facility → dock time + rating + up to 3 approved, de-identified "What drivers say" excerpts. API `GET /public/facility/{id}` (no auth).
Suite: **pytest 308 · vitest 101 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; full authz posture; dev tooling excluded from prod; public scorecard now shows approved de-identified snippets; integration e2e green; offline fully a mode; five product surfaces + a dev-only directory; admin console operational; M6 self-serve; three F13-config knobs live.** Hardening to date: scorecard snippets (053), M3 terms config (052), gate /dev (051), fleet membership gate (050), M3/M5 authz sweep (049), load authz gate (048), end-load (047), GET /load/active (046), dev directory + counterparty names (045), M10 earn config (044), audit-log view (043), owner spot CRUD (042), config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`c567a84` M3 terms config → this: public-scorecard review snippets (+ this handoff). **118 commits** on `main`, never pushed.

*— End of session. Next: fold moderation into the admin audit feed, then optional config seams (M2 review points, M10 redeem/rate-limit). Activation seams await owner/BD inputs (§4).*
