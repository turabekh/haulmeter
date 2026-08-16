# PRD Extension E3 — M15 Roadside Readiness (ELP Training) + Platform Additions

**Status:** **APPROVED — D14 signed by the owner, 16 August 2026, scope (b): Session A only.** Sessions B and C require their own kickoffs against D14. D16, D17, and D20 are confirmed at their stated defaults; **D15, D18, and D19 remain OPEN.** Phase A carries **zero payment code paths** (M13 Phase A precedent); Phase B (`m15_billing`) and the formal-assessment mode (`m15_assessment`) are explicitly NOT scheduled and their flags do not exist — D15 and D19 gate their creation.
**Amends:** `docs/trucker-platform-prd.md` v1.0 (§8 module list, §9 monetization per §E3.5) · `docs/trucker-platform-prd-v2-amendment.md` (§4 non-goals, per the reversal named in §E3.6) · **Date:** 16 August 2026 (supersedes the 15 Aug draft that carried the E2/M14 numbering) · **Approved:** 16 August 2026, D14 scope (b) · **Owner:** Turaboy
**Leaves untouched:** PRD Extension E2 / **M14 Fleet Recovery Overlay** — approved as D8, deployed inert at `haulmeter.online` on 2026-08-15 (migrations 0078–0080, flag `m14_overlay`, import-linter contract 31). M15 imports nothing from m14 and shares nothing with it beyond the platform.
**Companion document:** **ClearRoad PRD v3.0 (14 Aug 2026)** remains the commercial authority — market, buyer, pricing, 45-day gate, content plan, scoring principles, regulatory copy discipline. This extension is the engineering law that folds that product into the platform as **M15**. Where the two conflict on engineering law, this extension governs.
**Origin:** FMCSA English-language-proficiency enforcement — 26,000+ drivers placed out of service since strict enforcement resumed (June 2025); NPRM **FMCSA-2026-0826** published 10 Aug 2026 proposing to codify ELP as an OOS violation (comments close 9 Oct 2026); EO 14286. The exposed population is the platform's own seed community (the same Uzbek / former-USSR driver community as M13's founding vendor). Assessment incumbents (ELPReady) find failing drivers and hand them Babbel; nobody closes the loop of **simulation → diagnosis → native-language teaching → measurable improvement → a dated record**. M15 is that loop.

**Naming note:** E1 was the M13 extension document (its internal §E2/§E3 were platform additions *within* it). E2 is the M14 Fleet Recovery Overlay. This is the **third** extension document; its module is **M15**. New owner decisions continue the v2.0 D-series (**D14–D20**) so one registry holds them all.

Both governing laws hold: the **v2.0 validation law** (work ordered by distance to a validated outcome; a requirement is done when a person who is not the owner has used it and the outcome is observable in the database — every FR below names its validation, not just its tests) and the **design law** (design-prd §1 — mobile-first 360×800, tokens only, §22 protocol, never improvise; §18 for the portal surface this touches). All nine working rules unchanged.

One naming law up front: the driver-facing name is **"Roadside Ready"** — a catalogue string, not a second wordmark. `core/brand.js` keeps its one home (HANDOFF-063); "ClearRoad" retires to the strategy document as an internal codename.

---

## E3.0 Gap analysis — ClearRoad v3 requirements vs. the platform as of the Journey-1 Session-B close-out (mid-Aug 2026; import-linter at 31 contracts, m15 becomes the 32nd)

Statuses follow audit discipline: **OBSERVED** = read in the dump / handoffs and cross-checked; a session plans against the tree, not this table — re-grep before acting.

| # | v3 requirement (§ref) | Status | Where / what's missing |
|---|---|---|---|
| 1 | Guest-first start + dual auth: Telegram and email/password (v3 §8.2) | **~80% built** (OBSERVED) | F1 email/password live, no-activation; the pluggable auth-method registry was designed for exactly this addition. **Missing:** `telegram` method (Login Widget + Mini App initData) → §E3.2; guest sessions with account-claim → §E3.2 + M15-FR1 |
| 2 | Carrier org, sponsored seats, owner reporting (v3 §3.1, §10) | **~85% built** (OBSERVED) | F1 `fleet` org + `fleet_admin` role; M12 fleet workspace + per-seat model; design-prd §18 portal family. **Missing:** readiness-seat entitlements; the privacy boundary at the interface level → M15-FR8, FR9 |
| 3 | Carrier verification for onboarding + the week-1 carrier list (v3 §3.3, §11) | **BUILT** (OBSERVED) | F1 MC/DOT + FMCSA verification (mig. 0025). The carrier-list legwork is a business track riding existing data — and it is the **same SAFER community list** E2 §E2.8 names as M14's pilot pipeline; one call serves both |
| 4 | Tamper-evident Training & Improvement Record (v3 §5.4) | **BUILT, stronger than the draft assumed** (OBSERVED) | F4 hash-chained log + Pack Composer produce verifiable PDFs today (M3/M5 packs), and the public tokenized-link pattern is proven **at the edge** — §23 entry 148 fixed `/pack/s/{token}` routing in production. **Missing:** the training-record template + a scope-limited `GET /verify/{token}` → M15-FR7 |
| 5 | Coaching in the driver's language; 7 locales incl. Tajik (v3 §7, decision 13) | **6 locales BUILT** (OBSERVED) | F15 complete for en/es/pa/ru/uz/so with hard completeness gates. **Missing:** `tg` locale → §E3.3. Per-intent coaching content is **module data**, not F15 catalogue strings → M15-FR5 |
| 6 | Evaluation LLM with budgets, prompt versioning, eval fixtures (v3 §5.5, §6) | **BUILT (F9)** (OBSERVED) | Claude live; the registry/eval-fixture pattern is proven by M11; per-call cost tracking and monthly budgets exist (F-17/F-18 closures). M15 registers its prompts and fixtures — nothing structural missing |
| 7 | Server-side streaming STT + batch TTS (v3 §8.1) | **Seam preserved, not activated** (OBSERVED) | Decision 204 kept F9 `transcribe`/`synthesize` stubs for exactly this. **Missing:** real providers + audio plumbing → §E3.4. (On-device Web Speech is NOT acceptable for M15 scoring: accented-English quality, logged transcripts, human review, and consistent evaluation all require the server path) |
| 8 | Audio storage, serving, retention (v3 §8.5) | **BUILT for images, richer than the draft assumed** (OBSERVED) | MinIO live; signed short-lived `/media` URLs and derivative thumbnails exist (§23 entries 145, 149), terminated at the API with the object store private. **Missing:** audio MIME/range serving + a 30-day retention TTL class → §E3.4.3 |
| 9 | Offline drill packs (v3 §8.3) | **Foundation BUILT (F12)** (OBSERVED) | Offline queue/replay with idempotency, read-cache, queued-item glyphs (entries 144/150/151), installable PWA with revisioned precache (entries 143/152). **Missing:** drill-audio prefetch policy → M15-FR6 |
| 10 | Parked-only interactive practice (v3 carry of v2 §46) | **LAW EXISTS** (OBSERVED) | design-prd DRIVING state + the motion policy (decision 94). M15 applies it more strictly than M11: sessions **refuse and pause**, nothing defers → M15-FR3 |
| 11 | SMS/Telegram invites, drill reminders (v3 §11, §8.3) | **Transports live or seamed** (OBSERVED) | Web Push is LIVE (VAPID, entries 111/143/152). Email is LIVE via Gmail SMTP **in every environment — every environment is live-fire** (HANDOFF-127 §2; the rule binds M15's invite testing, see §E3.7 build notes). Twilio SMS remains a seam. **Missing:** two new notification classes → §E3.1.7 proposals |
| 12 | Payments: carrier seats + driver one-time (v3 §10) | **Seam pending** (OBSERVED) | Stripe is a standing §17 activation input. **Resolution:** Phase A = zero payment code (off-platform payment links + audited F14 admin grants); Phase B = `m15_billing` (Checkout + Billing), gated on the §9 amendment (§E3.5 / D15) and the gate result |
| 13 | Voice session UX | **Partial reuse** (OBSERVED) | M11's mic affordance, §14 voice patterns, §13.4 audio-first. The continuous-conversation session surface is new → §E3.1.6 proposals |
| 14 | Scenario engine, scoring, SRS, phrase-family content, sign training | **NEW** | The module itself → §E3.1 |

**Net-new work = M15** (the module) **+ four platform additions** (§E3.2 F1 auth/guest, §E3.3 F15 Tajik, §E3.4 F9 speech activation + F6 audio, §E3.5 PRD §9 monetization amendment) **+ owner decisions D14–D20** (§E3.6).

---

## E3.1 M15 — Roadside Readiness

### E3.1.1 Scope and product shape

M15 is a **program with a beginning and an end**, not a feature of the map:

**Baseline Roadside Check** (free, guest-first) → **diagnostic** (what was missed and *why*, in the driver's language) → **30-Day Drill Plan** (daily 5–8 min, spaced repetition, offline-capable) → **reassessment on unseen variants** → **Training & Improvement Record** (dated, hashed, verifiable PDF).

Primary buyer: the small carrier owner (fleet org) sponsoring seats. Secondary: owner-operators and individual drivers (one-time program purchase, Phase B). The free Roadside Check is free for every driver forever — it is tier-1 utility under the amended §9 (§E3.5) and the module's acquisition engine.

**Explicitly out of scope for this extension:** formal internal ELP *assessment* mode and its evidence records (English-only interview, supervised mode, limited retries — ClearRoad v3 §12/v1.5). That is a separate flag `m15_assessment` which **does not exist**, gated per **D19**. M15 ships *training* records only, and the difference is load-bearing (quality law Q-7).

**What M15 deliberately does not touch:** the background location sensor. Sessions are foreground, parked, and consent-gated — the module neither depends on nor compounds Phase DoD #8's unproven mechanism.

### E3.1.2 Functional requirements

Per the v2.0 law, every FR names its **validation** — an observation about a person or the world, not the suite.

**M15-FR1 — Guest-first session and account claim.**
A Roadside Check starts with zero signup; target **<60 seconds from entry to the first officer line**. F1 issues a short-lived guest principal (§E3.2); the result screen offers claim via any F1 auth method; claiming merges session, turns, and skill state into the account. Unclaimed guest work expires in 7 days, warned on the result screen (Q-10). Auth is never placed in front of the free check.
*Validation:* a driver who is not the owner reaches the first officer line in under 60 seconds with zero signup, and later claims that session into an account — the merged rows are theirs in the database.

**M15-FR2 — Scenario engine: scripted trees + hidden state.**
A `scenario_version` carries hidden state (driver name, carrier, origin, destination, cargo, HOS numbers, trailer) from which questions and expected answers derive. Content is organized **intent-first**: each intent owns a phrase-variant pool (5–8 phrasings × difficulty 1–2 × 2 officer voices) plus repair/clarification branches ("I'm asking where you picked *up* this load"). Branch selection = F9 classification of the driver's turn against expected intent/slots; scoring is hybrid (deterministic slot validation + semantic rubric). Officer audio is **pre-synthesized and cached** (F6); only small dynamic slot fragments (names, cities, hours) touch TTS at runtime — this is what holds a full simulation to ≈$0.10–0.15 COGS and sub-1.3s latency. **Sign turns** are a first-class turn type: an original MUTCD-style rendering is shown (F6-served; never a copyrighted image) and the driver answers aloud; ~20 signs + dynamic-message examples at Phase A. Anti-memorization: variant pools, randomized scenario facts, and `holdout=true` variants reserved for reassessment (Q-5). Phase A ships **scenario 1 (routine stop, ~15 intents), scenario 2 (HOS/ELD, ~12 intents), and the sign module**; difficulty levels 1–2 only.
*Validation:* a driver who is not the owner completes scenario 1 unscripted and the recorded transcript shows branch selection following their actual answers — including at least one repair branch reached and recovered from.

**M15-FR3 — Live session loop.**
Module-owned WebSocket: mic capture → streaming STT (§E3.4) → endpoint detection → classify → cached-audio playback. Latency budget **≤1.3s perceived p75, ≤1.8s p95** on the dev stack. **Consent before any recording**: a localized consent screen (purpose, 30-day raw-audio retention, who can hear it, deletion) precedes the first session; no consent, no mic. **DRIVING state:** sessions refuse to start and hard-pause in motion with a one-line audio explanation (§13.4) — stricter than M11's defer-confirm, because there is nothing to defer (Q-4). ASR below the confidence threshold **never** produces a negative tag: the turn is marked `REVIEW_NEEDED`, excluded from bands, and the driver can flag any transcript in one tap (Q-2).
*Validation:* latency measured across a full real session on the dev stack meets p75/p95; the consent screen renders in all seven locales before any mic access; a session flipped to DRIVING mid-turn pauses with the audio line, observed on a real handset.

**M15-FR4 — Diagnostic engine and failure taxonomy.**
Four scored dimensions: comprehension, answer completeness (relevance + slots), task completion, intelligibility. **Accent is never a feature, score, or tag** (Q-1); latency and repetition counts are logged diagnostics only. Ten failure tags: `INTENT_MISUNDERSTOOD(intent)`, `SLOT_WRONG_FACT`, `MULTI_PART_PARTIAL`, `REPETITION_REQUIRED`, `TERMINOLOGY_UNKNOWN(term)`, `SIGN_INCORRECT`, `DYNAMIC_SIGN_INCORRECT`, `UNINTELLIGIBLE`, `IRRELEVANT`, `NO_RESPONSE`. Readiness bands Green/Yellow/Red render with a **"provisional"** label everywhere until the calibration gate is met (rolling human-agreement ≥85% on the F14 review sample, Q-8). The result surface shows strengths / needs-practice per phrase family — never a naked percentage.
*Validation:* rolling scorer agreement ≥85% on the F14 review sample — the band drops "provisional" only when the world says so, and the dashboard (FR10) is where it says it.

**M15-FR5 — Coaching and the teaching loop (the learning system).**
Every meaningful failure runs the full sequence: replay the missed question → native-language explanation of the *intent and the idiom* ("clock" is not soat; it is remaining HOS drive time) → phrase-family exposure (hear 3–6 equivalents) → listen drill → respond-aloud → **model-answer shadowing** (hear a clear model answer, repeat it; intelligibility-only feedback) → variation (different voice/phrasing) → mini-sim retest. Vocabulary the baseline shows as simply unknown (BOL, tandem, seal number) is **taught before it is ever tested**. Coaching content lives in module tables keyed per language (`coaching_content{uz, ru, tg, es, pa, so}`): **uz ships at Phase A; ru + tg text follow as content releases; es/pa/so by carrier demand** — adding a language is a content pass, never an engine change. The F15 glossary law applies inside coaching text: trucking jargon stays English. F9 may **draft** variants and explanations; nothing reaches a driver without human review and a version bump (Q-6). A driver whose coaching locale has no released content sees an honest "not yet in your language" state — never silent English (Q-9).
*Validation:* a driver who failed an intent at baseline passes its **holdout** variant after completing the loop — observed in `skill_state`, which is the Track B north star measured one driver at a time.

**M15-FR6 — 30-Day Drill Plan: spaced repetition + offline packs.**
Every failed phrase-family member enters an SRS queue (≈1/3/7/14-day intervals; reset on failure). Each daily 5–8 minute drill is assembled from due items plus 1–2 new variants, interleaved across intents. A per-skill progress strip (heard ✓ / understood ✓ / answered ✓) makes improvement visible daily. **F12 offline:** the day's due drill audio prefetches on Wi-Fi; drills run in dead zones; results queue and replay idempotently. Live sims require connectivity; the learning loop does not. Drill audio is 100% cached — practice is effectively free to serve and is never metered.
*Validation:* a driver who is not the owner completes a day's drill in airplane mode and the results replay idempotently when signal returns — exactly once, observed in the database.

**M15-FR7 — Reassessment and the Training & Improvement Record.**
At day 30 (or owner-triggered): a fresh simulation drawing **holdout variants and a different officer voice** on previously failed intents. Output via F4: a dated PDF — driver, carrier, dates, domains trained, before/after bands, drill completion, methodology note, hash + public verification URL (`GET /verify/{token}`, rate-limited). The record is titled a **training record**; the words *assessment, certificate, FMCSA approved, pass* are forbidden in its templates, and the ClearRoad v3 Appendix A disclaimer is rendered verbatim on every record (Q-7). Records are English (M11 ghostwriter precedent: counterparty-facing artifacts are English-out). The record is offered into the M5 docs wallet as a document type, **excluded from inspection mode** (D17).
*Validation:* a pilot carrier owner who is not the owner opens `GET /verify/{token}` from a record PDF **on the public internet** and it verifies — proven from outside the box at the edge, per the entry-148 lesson (a link correct in the process that mints it and wrong in the process that fetches it is this codebase's most-repeated defect class).

**M15-FR8 — Carrier sponsorship and the privacy boundary.**
The M12 fleet workspace gains a **Readiness section** (§18 portal family — composition inside the existing portal, not a sixth portal). Invite drivers (F8 SMS/email + Telegram links), grant seats, see roster status. The org-visible surface is exactly: invited · started · baseline band · drill-week completion · reassessment band · record issued. **Turns, transcripts, audio, and mistake-level detail are structurally unreachable from org contexts** — the m15 public interface exposes bands and aggregates only, enforced the M13/Q-3 way: the org-facing query path is a different function that takes no turn-level arguments, and a test asserts it (Q-3). Practice-mode sessions never appear in any org view at all.
*Validation:* a real carrier admin who is not the owner reads their roster's bands from the portal; the Q-3 test proves turn-level data unreachable from org context; a sponsored driver's practice session is invisible there entirely.

**M15-FR9 — Commerce: Phase A concierge, Phase B in-app.**
**Phase A: zero payment code paths are reachable** (M13 Phase A precedent; same DoD grep as E2). Pilot carriers pay $499 off-platform (payment link); a driver cohort may be granted the program the same way. Every entitlement is an audited F14 admin action (grantor, source, before/after). **Phase B (`m15_billing`, flag does not exist yet):** Stripe Checkout for the one-time driver program ($49; launch $29 first 100) + Stripe Billing for carrier seats ($12/driver/mo, $99/mo minimum; annual $120/driver) — activation gated on the §9 amendment (**D15**), a Stripe account (standing §17 input), and the 45-day gate result. Because the app is a PWA, one-time purchases carry no store tax; this is protected if Capacitor wrapping is ever revisited.
*Validation:* ≥3 pilot carriers have **paid** $499 by day 45 (Track A), and every live entitlement on the box traces to an audited F14 grant naming its grantor and source.

**M15-FR10 — Analytics and the gate dashboard.**
The v3 §8.6 event list ships in full (scenario_started … retry_completed, remediation funnel, upgrade/invite events). An F14 admin **gate dashboard** surfaces the Track B numbers live: baseline completion %, voluntary second session ≤7 days %, remediation start/completion %, holdout-variant improvement %, scorer-agreement %. The gate is the module's own Phase B trigger, so the module measures it.
*Validation:* the owner writes a weekly pilot report from the dashboard's numbers without hand-computing any of them — every figure traceable to event rows (the §11.7 rule pointed at the operator, as `running_ahead_of_gates` already does).

### E3.1.3 Deliberately thin at Phase A

Two difficulty levels (Clear, Natural). Two officer voices. No ambient-audio mixing. No generative free-form officer — the fully generative "exam mode" is a Phase B+ candidate reserved for reassessment realism where ~10× per-session cost is justified. No confidence-vs-competence matrix. No share cards.

### E3.1.4 Data model (schema `m15`)

- `scenario_version` (id, version, domain_mix, difficulty, allowed_intents[], environment, status)
- `intent` (id, key, domain, canonical_meaning, required_slots jsonb, difficulty_rating)
- `phrase_variant` (id, intent_id, text, difficulty, voice, audio_ref → F6, holdout bool, status: draft | reviewed | released, version)
- `sign_item` (id, key, rendering_ref → F6, meaning, dynamic bool, status, version)
- `coaching_content` (intent_id | sign_id, locale, explanation, glosses jsonb, version, review_status)
- `session` (id, account_id nullable, guest_token nullable, org_id nullable, scenario_version, mode: check | drill | reassessment | practice, consent_at, started_at, completed_at, band, provisional bool)
- `turn` (session_id, seq, speaker, audio_ref → F6 (TTL class), transcript, asr_confidence, intent_id, expected_slots, observed_slots, scores jsonb, failure_tags[], review_status)
- `skill_state` (account_id, variant_id, exposure_count, success_count, srs_interval, srs_due_at, difficulty_ceiling)
- `drill_plan` (account_id, plan_day, items jsonb, completed_at)
- `entitlement` (id, subject: account_id | org_id, kind: program | seat, source: admin | stripe, granted_by, starts_at, ends_at)
- `training_record` (id, account_id, org_id nullable, evidence_ref → F4, pdf_ref → F6, hash, verification_token, issued_at)
- `review_sample` (turn_id, ai_band, human_band, reviewer, agree bool, notes, created_at)

Retention laws: raw driver audio in `turn.audio_ref` carries the **30-day TTL class** (§E3.4.3), driver-deletable earlier; cached officer/drill/sign audio is permanent content; derived transcripts, scores, and skill state persist. **No voiceprints, no biometric matching, ever** — there is no column for one and no D-question that could add one.

Boundaries: m15 imports `foundation.*.public` + earlier modules' `.public` only (M12 fleet interface for org context; M5 wallet interface for record placement). **M14 is not imported.** import-linter contract added in the first commit (**31 → 32**). Uniqueness that matters (one live session per guest principal; one skill_state row per account × variant; one entitlement per subject × kind × window) is declared **on the model as well as the migration** — the test database is `create_all`, and a migration-only constraint is invisible to the entire suite (TRAPS §1.3; the 0077 lesson).

### E3.1.5 API

**Driver:** `POST /roadside/session` (guest or authed) · WS `/roadside/session/{id}/stream` · `GET /roadside/session/{id}/result` · `POST /roadside/claim` · `GET /roadside/plan/today` · `POST /roadside/drill/{id}/result` (offline-idempotent) · `POST /roadside/turn/{id}/flag`.
**Fleet (org-scoped, bands-only path):** `GET /fleet/readiness` · `POST /fleet/readiness/invite` · `POST /fleet/readiness/reassess/{driver}`. (No collision with M14's `/fleet/recovery/*` namespace.)
**Admin (F14):** entitlement grant/revoke · calibration review queue · content publish (draft → reviewed → released) · gate dashboard.
**Public:** `GET /verify/{token}` (record verification, rate-limited, reveals record validity + issue date only). **A new public path is an edge change in the same commit** — Caddy `handle /verify/*` alongside `/pack/*`, verified by container grep and a live fetch, never by reading the Caddyfile in the repo (entry 148; TRAPS §3).

### E3.1.6 Driver UI (design-prd §22.3 DoD applies in full)

- **Entry:** a plain **row** on More — §10.5 keeps More a plain 64 dp row list with **no cards, no promos, no badges**, so the entry is a row ("Roadside Ready" + one-line caption), not a card — plus org-invite deep links. **No new bottom-nav tab** — tab changes remain the standing A8/D7 owner decision (D16 folds into it).
- **Session surface:** full-screen, S1 shape; oversized officer-line text mirror (optional), 56 dp mic, live "listening" state, hard pause on DRIVING. New-surface composition logged as decision-log proposals (§E3.1.7); if any new token proves necessary, **STOP** per §22.
- **Result surface:** strengths / needs-practice per phrase family; claim prompt for guests; "Start my plan" primary CTA.
- **Drill player:** S2 dock-task shape; progress strip; shadowing playback; works offline per FR6.
- **Record viewer:** reuses DocumentViewer; the record sits in the M5 wallet grid (not inspection mode).
- **Every new surface registers in the layout harness in the same commit that creates it** (v2.0 acceptance #3), and every fetching surface declares all four states — loading / data / empty / failed — per the §22.3 rule entry 131 added; a fixture is never one of them.
- All strings × **seven** locales (after §E3.3) + pseudo-locale; CI completeness enforced as always; doc-type and trucking acronyms stay English (§12.3).
- **DRIVE.md gains the Readiness journey** (guest check → claim → drill day → offline drill → reassessment → verify URL) in the same commit as the surfaces it walks (v2.0 acceptance #3).

### E3.1.7 Notifications and surface proposals — decision-log entries (owner approval before build)

The log lives in `docs/decisions/117-current.md` (entries 157–158 moved it); the implementing session logs these as **numbered entries against the live file** (159+ at time of writing). Per entry 121's precedent, a **new notification class is a §22.2 never-improvise category** — entry 118's delegation does not cover it, so P-1 and P-2 below go to the owner as forks with their full spec, exactly as the packet-push fork did:

- **P-1:** new notification class `readiness_reminder` (drill due · plan expiring · reassessment scheduled). Proposed spec, entry-121 shape (and now with `arrival_reminder` — entry 169 — as the built precedent for a P1 clock-anchored class): **tier P1** (useful today), `opt_out`, defaults ON **only for enrolled program participants** (a driver who bought or was granted a 30-day program has opted into its mechanism, which is daily practice); `max_per_day` **1**; **NOT budget-exempt** (counts against §13.1's two-a-day); quiet hours respected; `route_relevant_only` false; deep-links to `/roadside/plan/today` per §13.5; never promotional.
- **P-2:** new notification class `readiness_invite` (org-initiated seat invitation via F8 SMS/email/Telegram; **one per driver per org per 7 days**; fired only by an org admin's action, never by platform initiative; quiet hours respected; deep-links to the invite claim).
- **P-3:** the session surface + progress strip, composed from existing tokens/components — logged as composition; no new visual class expected.
- **P-4:** Readiness section added to the Fleet Workspace (§18 family — composition inside the existing portal, not a sixth portal).

### E3.1.8 Flags & gates (F13)

- **`m15_roadside`** — master; registered with **no `default_on`** (a capability that has never shipped declares nothing and lets the operator's decision govern — HANDOFF-121 §13.14 / the F-02 discipline). Turning it ON opens the free Roadside Check platform-wide; sponsored features (Readiness section, seats, reassessment triggers) additionally require **entitlements**, which is what scopes the 45-day gate window to pilot orgs without a per-org flag.
- **`m15_billing`** — does not exist. Created only on gate pass + **D15**.
- **`m15_assessment`** — does not exist. Created only when all three **D19** criteria are met; no build proceeds toward it meanwhile.

### E3.1.9 Definition of Done (Phase A, PRD §7.16 style)

All FRs behind flag **`m15_roadside` (default OFF)** · tests alongside every FR (unit + API + vitest; e2e extends the full-platform day: owner invites → guest check → claim → diagnostic → a week of drills incl. one offline → holdout reassessment → record PDF verifies at the public URL **from outside the box**) · seven locales + pseudo-locale pass · offline behaviors verified · DRIVING policy verified · consent flow verified in all locales · a11y pass · import-linter green with the m15 contract (32/32) · **zero payment code paths reachable** · every §E3.1.10 quality law covered by an automated test · calibration harness live (review queue + rolling agreement metric) · **Uzbek coaching content: ≥40 intents released through the review pipeline** (scenarios 1–2 + signs) · latency budget met on the dev stack · F9 budget alerting live for audio minutes · every new surface in the layout harness same-commit · DRIVE.md journey added same-commit · **`m15` in `MODEL_MODULES`** (`api/db_registry.py`) in the first schema commit (TRAPS §1.4 — omitting it fails remotely across unrelated suites) · seed: DEV_SEED demo scenario + one real pilot-carrier org (is_dev pattern for the demo).

**Live-fire law, restated for this module because invites make it hot:** Gmail is the SMTP target in every environment by owner decision (2026-08-15, HANDOFF-127 §2) — **every environment is live-fire for email, and the same posture applies to SMS/Telegram the day those transports carry invites.** During build and demo, invites are addressed only to inboxes and numbers the owner controls. No session restores Mailpit or adds an environment guard as a tidy-up.

### E3.1.10 Quality laws — binding, same force as design-prd laws; each ships with a test

- **Q-1 Accent is never scored.** Intelligibility only. No feature, score, weight, or tag may encode accent or nativeness. "I go Chicago" must outscore "Yes." on a destination question — a rubric fixture asserts it.
- **Q-2 Uncertain ASR never penalizes.** Below-threshold confidence → `REVIEW_NEEDED`, excluded from bands; the one-tap transcript flag is always rendered.
- **Q-3 Practice is private, structurally.** The org-facing query path is a separate function that cannot return turn-level data; a test asserts org context reaches bands and aggregates only, and that `mode=practice` sessions are invisible to it entirely.
- **Q-4 Nothing interactive in motion.** Sessions refuse to start and hard-pause on DRIVING; a test flips the state mid-session.
- **Q-5 Holdout integrity.** `holdout=true` variants never appear in drills or coaching; reassessment draws holdout-first. Property test on the generators.
- **Q-6 Content ships reviewed or not at all.** `released` requires human review + version bump; F9-drafted text has no path to a driver. Publish-path test.
- **Q-7 The record never overclaims.** Record templates come from a fixed catalogue carrying the v3 Appendix A disclaimer; *assessment / certificate / FMCSA approved / pass* are forbidden strings — the test greps template **and rendered PDF text**.
- **Q-8 Bands are provisional until calibrated.** Until rolling human agreement ≥85% over the sample window, every org-facing band renders the provisional label. The gate metric is the test's fixture.
- **Q-9 No silent English in coaching.** Missing coaching content in the driver's locale renders the honest empty state — F15 criterion 5 applied to module data. Per-locale test.
- **Q-10 Guest work is never lost silently.** Claim merges completely; expiry is warned on the result screen. Claim round-trip test.

### E3.1.11 Metrics

**Gate (Track A, commercial — recorded in handoffs, not code):** ≥10 owner conversations → **≥3 paid pilots ($499) live by day 45**, ≥2 presold on deposit before the flag turns on; ≥1 converts to monthly by day 60–75. Kill: <2 paid pilots despite ≥8 genuine conversations → the flag stays OFF and the platform keeps the technology (Telegram auth, Tajik, server speech, guest sessions); that is the fold-in, by construction.
**Gate (Track B, in-product — the FR10 dashboard):** baseline completion ≥60% of invited · voluntary second session ≤7 days ≥35% · remediation start after a flagged weakness ≥50% · **holdout-variant improvement on remediated intents for ≥50% of drill completers** · scorer agreement ≥85%. Secondary (Phase B only): free-check → program conversion ≥5% among non-sponsored drivers.
**North stars:** business — retained sponsored seats; learning — previously-failed intents passed on holdout variants per week.
**DDD note (M13 precedent, restated by E2 for M14):** Driver Dollars Delivered is **not** credited from readiness — an avoided OOS is not honestly measurable. M15 carries its own counter (*"readiness improvements demonstrated"*) until a defensible dollar mapping exists.

---

## E3.2 F1 extension — Telegram auth method + guest sessions

1. **`telegram` auth method** joins the pluggable registry exactly as F1's law anticipated ("must slot in without reworking the account schema or session model"): Login Widget hash validation on the browser PWA; Mini App `initData` validation when opened inside Telegram. One account, multiple linked methods — a driver who starts in Telegram adds email/password later (or the reverse) and nothing merges because nothing was ever separate. Migration adds the method rows only.
2. **Guest sessions:** F1 issues a short-lived unauthenticated principal usable only by modules that opt in (m15 first). Claim = attach the guest principal's rows to an account, atomically. Guest principals expire in 7 days.
3. Rationale: Telegram is not a nice-to-have — it is the acquisition channel of the exact community M13's founding vendor already serves. Foundation change is additive; no rework of existing auth.

## E3.3 F15 extension — seventh locale: Tajik (`tg`)

- `tg` (Cyrillic) enters as a **first-class locale** — no completeness exemption; criterion 5 ("no English fallback reaches a driver") is not negotiable, so the entire existing catalogue is drafted (LLM) then **native-reviewed before merge** (budget a paid reviewer; the audit's warning stands: machine-translated strings shipped unreviewed are worse than the gap they hide). CI completeness enforces `tg` from the merge onward; every module's future strings ship ×7 + pseudo-locale.
- BCP-47 mapping `tg → tg-TJ` for `core/speech.js`; Web Speech coverage will be thin — decision 205's graceful degradation already handles it.
- Glossary law holds: trucking jargon stays English inside Tajik text.
- **Voice note:** no major vendor ships neural Tajik (or Somali) TTS. Tajik coaching launches **text-first**; because coaching lines are fixed and cacheable, recorded human audio is the later path to voice — a weekend of studio time, not an engineering project.
- Benefit is platform-wide: Haulmeter gains its seventh driver language whether or not M15's gate passes.

## E3.4 F9 + F6 extension — server-side speech seam activation

Decision 204 preserved the F9 `transcribe`/`synthesize` stubs "for later — e.g. higher-quality/consistent TTS, processing audio." M15 is that later.

1. **Streaming STT adapter** behind the F9 provider registry (Deepgram first candidate; provider-abstracted). The accented-English benchmark set is **built from pilot sessions** via F9 call recording — not as a separate pre-project; the provider decision (vs. Whisper-large) is made on that data.
2. **Batch TTS adapter** for officer/coach line synthesis: one-time benchmark (ElevenLabs / Azure / OpenAI) for the two English officer voices; Azure `uz-UZ-SardorNeural` / `MadinaNeural` for the Uzbek coach after a native spot-check. Synthesis runs as worker jobs at content release (the established flag-gated worker pattern); runtime TTS is limited to dynamic slot fragments.
3. **F6 audio support:** audio MIME types, range serving, and a **retention TTL class** (30-day, driver-deletable) distinct from permanent content audio. Serving follows the entry-145 discipline: signed URLs terminated at the API, object store private, and any `src` the browser fetches is proven against the **serving origin**, never asserted as a string. MinIO locally; the bucket seam stands.
4. **F9 budgets** extend to per-minute audio accounting with an anomaly alert (the v3 §9 cost-control requirement), on the existing per-module budget rows (no uncapped state exists — the F-17 invariant covers m15 from its first row).
5. New settings: STT/TTS keys empty in `infra/.env.example`, real values in `infra/.env` only (rule 9). An unset speech key **refuses loudly** rather than degrading to on-device — a silent fallback is how a scoring control becomes decorative (the M14 crypto precedent, audit F-02's shape). LOCKED ports untouched (5438/8008/9008). M11 is unaffected — on-device stays; upgrading the copilot to server STT is a noted follow-on, not built.

## E3.5 PRD §9 amendment — monetization law (drafted for approval as D15; amends "Driver price: $0, permanently")

**§9.0 The three-tier law.**
1. **Tier 1 — Core utility: $0, forever.** Never paywalled, enumerated: the map and all crowd data (reading and contributing) · The Meter and every detention/accessorial claim function · the docs wallet and inspection mode · load tools · community · the voice copilot · **the free Roadside Check**. Nothing may ever move from tier 1 to tier 3.
2. **Tier 2 — Money in motion: unchanged.** Parking take rate, detention/accessorial contingency, fuel spread, fleet per-seat SaaS, data product.
3. **Tier 3 — Programs & premium services: purchasable.** Defined as offerings with a beginning, an end, and a deliverable, that **create capability rather than gate existing utility**. First instances: *Roadside Ready 30* ($49 one-time; $29 launch price, first 100) and carrier readiness seats ($12/driver/mo, $99/mo minimum, $120/driver annual; $499 pilot). Adding a tier-3 offering requires a decision-log entry demonstrating conformance to this definition.

**Rationale:** tier 1 is the trust wedge and the crowd-density engine the data product depends on; tier 2 already out-earns any subscription on paper; tier 3 opens episodic-program revenue without touching either. The anti-erosion clause is the law's teeth. (PWA distribution keeps tier-3 purchases store-tax-free; protect this if Capacitor is revisited.)

## E3.6 What approving this reverses, and what it does not

**D14 names one reversal**, logged as such per the A8/D8 precedent: **v2.0 §4 "no new modules until the Phase DoD is met" is superseded for M15 only** — the second named use of the D8 carve-out. The argument is different from D8's and is stated on its own terms rather than borrowed: **(a)** the window is external and closing (NPRM comments close 9 Oct 2026; enforcement has been live since June 2025 — the market exists now and is being served badly by assess-and-abandon incumbents); **(b)** the extension is **self-terminating by construction** — the 45-day kill clause caps scope exposure, and a failed gate leaves the flag OFF while the platform keeps four durable assets (Telegram auth, the `tg` locale, server-side speech, guest sessions); **(c)** M15 neither depends on nor defers the Phase DoD's two named unknowns — it runs foreground and parked, so the unproven background sensor (#8) is untouched, and the wedge's paid-claim validation (#3) proceeds in parallel on M14's track; **(d)** revenue, if the gate passes, funds the validation work the Phase DoD demands. Every other module remains bound by §4.

**D15 names the second change to standing law:** v1.0 §9's opening line — *"Driver price: $0, permanently"* — is **amended, not repealed**, into the three-tier law of §E3.5. Tier 1's enumerated free-forever list plus the anti-erosion clause is the protection; a driver never pays for anything that exists today, and the free Roadside Check joins that list on day one.

**Unchanged, explicitly:** all nine working rules; the design constitution in full (LAW 0, NAV-1's five tabs, the §22.2 never-improvise categories, §22.3 + the four-state rule); every architectural boundary (`core < foundation < modules`, `.public` only, no lateral imports; M14 untouched and unimported); seven locales for every driver-facing string once `tg` merges; §13's interruption budget (both new classes count against it); the §13.4 motion policy, applied more strictly here than anywhere; F15's glossary law; the M13 Phase A zero-payment discipline; the privacy posture — org contexts see bands and aggregates only, and no voiceprint column exists or can be added without a new D-question.

**Non-goals for M15 v0:** formal assessment mode (`m15_assessment` does not exist); in-app payments (`m15_billing` does not exist); generative free-form officer; Capacitor wrapping; a bottom-nav tab (A8/D7 territory); coaching languages beyond the stated order without D20; any horizontal expansion beyond commercial trucking.

## E3.7 Owner decisions — D14–D20 (continuing the v2.0 §6 registry)

**Signature states as of 16 August 2026:** D14 **SIGNED, scope (b) — Session A only** · D16 **CONFIRMED** (default) · D17 **CONFIRMED** (default) · D20 **CONFIRMED** (ru + tg next, then by demand) · D15, D18, D19 **OPEN**.

Registry text for **D14**, signed and to be written into `trucker-platform-prd-v2-amendment.md` §6 at fold-in, with scope (b) recorded as the chosen option:

> **D14** | **Approve PRD Extension E3 — M15 Roadside Readiness.** One reversal, named per the A8/D8 precedent: v2.0 §4 ("no new modules until the Phase DoD is met") is **superseded FOR M15 ONLY**, on the arguments recorded in E3 §E3.6 — a closing external window (NPRM comments close 9 Oct 2026), a self-terminating 45-day gate with a kill clause, no dependency on the unproven sensor, and durable platform assets (Telegram auth, Tajik, server speech, guest sessions) regardless of gate outcome. **Every other module remains bound by §4.** · **Scope options at approval:** (a) full program — Sessions A–C + gate window as sequenced in E3 §E3.8, or (b) **Session A only**, per the slice discipline of D8, with B and C authorized against this entry by their own kickoffs. Phase A carries zero payment code paths; `m15_billing` and `m15_assessment` do not exist. D15–D20 remain open where marked; nothing bills a customer until D15 has an answer on record. | Blocks: everything

| # | State | Decision | Blocks |
|---|---|---|---|
| **D14** | **SIGNED — scope (b)** | Approve this extension; Session A authorized, B and C by their own kickoffs against this entry | Nothing further for Session A |
| **D15** | **OPEN** | Approve the §9 three-tier amendment (§E3.5) — the second named change to standing law | Phase B billing only; Phase A has zero payment code and proceeds regardless |
| **D16** | **CONFIRMED** | Entry point: More **row** + fleet-portal Readiness section at Phase A; whether Readiness ever earns a bottom-nav tab folds into the standing A8/D7 tab decision | — |
| **D17** | **CONFIRMED** | Training record as a wallet document type, **excluded from inspection mode** — whether to show a training record to an officer is the driver's choice, not a designed flow | — |
| **D18** | **OPEN (deferred)** | Neutral-brand surface (reserved): if consultant/CDL-school channels later require a non-Haulmeter face, the options are a skinned §18 portal or module extraction (cheap by construction — schema-per-module + public-interface-only imports). Deferred until a channel demands it | Nothing today |
| **D19** | **OPEN** | **`m15_assessment` trigger criteria** (M13 Q13 style): transportation counsel engaged · scorer calibration ≥90% agreement · consent + retention architecture reviewed. The flag does not exist until all three; no build proceeds toward it meanwhile. **Note:** the counsel criterion can share the D13 engagement — one transportation-counsel touch can scope carrier-name invoicing (M14) and assessment-mode exposure (M15) together | `m15_assessment` creation |
| **D20** | **CONFIRMED** | Coaching-language order after uz: **ru + tg text next**, then es/pa/so strictly by carrier demand | — |

No session may resolve the OPEN ones; a session that needs one **parks the item and records the question for the owner** (v2.0 §6 law, unchanged — the counsel subagent advises but carries no owner authority).

## E3.8 Build-order amendment, sequencing & build notes

PRD §8's module list extends to **M15** (after M14, its own flag, its own DoD, tests alongside every change — the *how* of the retired §6 build law survives in the nine working rules and is unchanged). Proposed sequencing — three build sessions plus a gate window; **content authoring is an owner-track workstream running in parallel from day one** (officer phrase variants, Uzbek explanations, 2–3 paid driver-reviewers), because no session writes 300 field-real officer lines for you:

- **Session A — Foundations** *(authorized by D14)*: §E3.2 (telegram + guest) · §E3.4 (STT/TTS adapters, F6 audio + TTL class, budget alerting) · §E3.3 dispatched (tg catalogue drafted, native review commissioned — a named schedule risk: the seven-locale gate blocks flag-ON if review lags) · `m15` schema + migrations · scenario engine core · content pipeline (draft → reviewed → released) · scenario 1 authored end-to-end with cached audio. **Key-tolerant start:** Session A may begin before the Telegram bot / Azure Speech / Deepgram accounts exist — adapters refuse loudly when unset (§E3.4.5), fixture suites carry the tests, and live synthesis/auth smoke is a named remainder, never a silent gap. **Content:** the owner-track scenario-1 pack (intents, variants, signs, uz explanations) enters the pipeline as `draft`; where it lags, the engine builds against a DEV_SEED draft scenario — Q-6 means draft content has no path to a driver, so nothing waits on it.
- **Session B — The loop:** WS session loop to latency budget · consent flow · diagnostic engine + failure tags · result surface · the FR5 teaching loop · guest claim · Uzbek content to ≥40 released intents (owner track converging).
- **Session C — The program:** SRS + drill plan + offline packs · reassessment + F4 record PDF + `/verify/{token}` **including the edge route, proven from outside the box** · fleet Readiness section + Q-3 boundary · entitlements + F14 admin surfaces · gate dashboard · e2e + full quality-law test sweep · seed pilot org.
- **Gate window (45 days from Session A start):** `m15_roadside` ON; pilot orgs scoped by entitlements. Business track in parallel: the carrier list from FMCSA registration data (**the same SAFER community list as M14's pilot pipeline — one call serves fleet seats, recovery, and readiness**) · ≥2 pilots presold on deposit before Session C ends · the **NPRM comment filed before 9 Oct 2026** (free credibility; the enforcement story is the acquisition hook) · weekly owner reports concierge (no dashboard dependency).
- **Phase B (`m15_billing`)** is scheduled only on gate pass + **D15**. **`m15_assessment` is explicitly NOT scheduled and its flag does not exist.**

**Build notes — TRAPS sections the implementing sessions read before touching the named thing** (read the relevant section, not cover to cover):

- **TRAPS §1 (migrations):** `m15` into `MODEL_MODULES` in the first schema commit — omitting it fails remotely across unrelated suites and hides when m15's own tests run (§1.4). Enums created explicitly, referenced with `create_type=False` — the 0057/0079 lesson, where alembic printed "Running upgrade" for both migrations and the database had neither (§1.2). Load-bearing constraints on the model as well as the migration (§1.3). Revision ids short (§1.1). Verify by querying the schema, never the exit line (§1.6).
- **TRAPS §3 (the edge):** `/verify/{token}` is the one URL in this module a stranger reads. Route it at the edge in the same change, force-recreate caddy on deploy, prove it by fetching from the public internet — a 200 serving index.html is this codebase's most-repeated defect class (entries 145/148: *a URL correct in the process that mints it and wrong in the process that fetches it*).
- **TRAPS §2 (the harness lies):** the latency probe and every Q-law test get the break-the-thing treatment — sabotage each and watch it go red before trusting green. A check that looks like the strongest available and isn't is the 127 pattern, found only by running things.
- **TRAPS §10 (live-fire):** invites and reminders ride transports that reach the outside world in every environment. Owner-controlled inboxes and numbers only, in dev and in demos, always.
- **Make targets** namespace as `m15-*` — `m14-*` belongs to the recovery overlay and is on production.

---

*End of Extension E3. On approval (D14), the implementing session logs the P-1..P-4 proposals as numbered entries in `docs/decisions/117-current.md`, writes D14–D20 into the v2.0 §6 registry (D14 per the text in §E3.7), amends PRD §8 (module list → M15) and §9 (per §E3.5, once D15 lands), adds the m15 import-linter contract (32nd), updates the module worklist, and proceeds plan-first as always. ClearRoad PRD v3.0 remains the commercial authority for the gate, pricing, market strategy, and content plan; this extension governs the engineering.*
