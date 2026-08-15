# PRD Extension E2 — M14 Fleet Recovery Overlay

**Status:** **APPROVED 2026-08-15 (owner, D8) — BUILD AUTHORIZED FOR SLICE 1 ONLY.** Slice 1 is `KICKOFF-m14-slice1-eld-claim.md`: evidence classes (FR3), one Motive connector with a pasted key and polling (FR2), and ELD-dwell drafting the **existing** M3 claim **held** for fleet-admin approval (FR4). **FR1, FR5 beyond hold-all, and FR6–FR9 remain PROPOSED** and are not build-authorized; further slices get their own kickoff against this entry rather than a new D-number. **D9–D13 remain OPEN, and nothing sends to a counterparty until D13 has an answer on record.** Approving this document was owner decision **D8** and is a **logged reversal of two standing rules** (see §E2.10) — per the A8 precedent, a reversal must be named as one. The full entry is in the v2.0 §6 registry.
**Amends:** `docs/trucker-platform-prd.md` v1.0 (§8 module list, §16 exclusions) and `docs/trucker-platform-prd-v2-amendment.md` (§4 non-goals) · **Date:** 15 August 2026 · **Owner:** Turaboy
**Origin:** owner strategy document "RecoveryOS" (2026-08-15) + gap analysis against the deployed platform at HANDOFF-121 / migration `0066`.
**Naming note:** E1 was the M13 extension document (its internal §E2/§E3 were platform additions *within* it). This is the second extension document; its module is **M14**. New owner decisions continue the v2.0 D-series (D8–D13) so one registry holds them all.

Both governing laws hold: the v2.0 validation law (work ordered by distance to a validated driver — here, *fleet* — outcome; done = a paying party used it and the outcome is in the database) and the design law (design-prd §1; §18 for the portal surfaces this touches). All nine working rules unchanged.

---

## E2.0 Gap analysis — RecoveryOS capability vs. the platform as of HANDOFF-121

Statuses follow audit discipline: **OBSERVED** = read in the dump and cross-checked against tests/handoffs; **INFERRED** = needs a command on the box before a session plans against it.

| # | RecoveryOS capability | Status | Where / what's missing |
|---|---|---|---|
| 1 | Parse rate con, extract accessorial terms | **BUILT** (OBSERVED) | F5 + F9 parse path; M4-FR4 term extraction with driver-confirm and missing-terms warning |
| 2 | Watch the trip; detect arrival/departure/dwell | **BUILT, phone-based** (OBSERVED) | F3 geofence ENTER/EXIT/DWELL_TICK over device traces. **Missing:** any second trace source. ELD is excluded by v1.0 §16 → M14-FR2 |
| 3 | Assemble evidence packet | **BUILT, stronger than spec'd** (OBSERVED) | F4 hash-chained log + Pack Composer. **Missing:** declared evidence basis when the source is not the phone → M14-FR3 |
| 4 | Live detention computation at contract rate | **BUILT** (OBSERVED) | M3-FR2 clock; correct trigger per rate-con terms |
| 5 | Draft/send claim + invoice per approval rules | **BUILT, driver-approves** (OBSERVED) | M3-FR5/FR6; notify-only mode exists. **Missing:** org-level rules → M14-FR5 |
| 6 | Layover / TONU / lumper | **BUILT** (OBSERVED) | M4-FR1/2/3 through the shared pipeline |
| 7 | Dunning + escalation | **BUILT** (OBSERVED) | M3-FR6 day-3/10/21 cadence; M3-FR7 partner seam. Partner contract itself is a §13 activation gate, unsatisfied |
| 8 | Track requested→invoiced→paid | **BUILT** (OBSERVED) | F7 `ReceivableState` (invoiced/acknowledged/disputed/escalated/recovered/written_off); M4-FR5 Money Owed view |
| 9 | Ask driver for missing evidence | **BUILT** (OBSERVED) | M3-FR8 guided capture; M5-FR5 gap nudges. **Missing:** fleet-triggered request → folded into M14-FR4 |
| 10 | Broker intelligence ("Broker A pays 83% after follow-up") | **SCHEMA BUILT, data thin** (OBSERVED) | F5 `Counterparty` registry with observed payment behavior + M2 dwell + M12-FR3 analytics. Fills only as claims flow — M14 is the volume engine |
| 11 | Mailbox ingest (rate cons, broker replies, remittances) | **SEAM ONLY** (OBSERVED) | F8 has `record_inbound_reply` + `MessageDirection.inbound` on threads; **nothing receives mail or classifies it** → M14-FR1, FR6 |
| 12 | Autonomous negotiation (fetch requested doc, answer, accept/challenge $120-vs-$158) | **NOT BUILT** (OBSERVED) | Deliberate: driver-approves-before-send is legal posture. Graduated autonomy → M14-FR6 |
| 13 | Linehaul AR: short-pays, stale invoices, deduction audits, missed fuel surcharge | **NOT BUILT** (OBSERVED) | Platform only ever invoices accessorials. M9's auditor is the pattern, pointed the other way → M14-FR7 |
| 14 | Accounting connector (QuickBooks) | **NOT BUILT** (OBSERVED) | No occurrence in the codebase → M14-FR8 |
| 15 | ELD connector (Motive/Samsara) | **NOT BUILT** (OBSERVED) | v1.0 §16 exclusion covers *building* an ELD; read-only API consumption was never specified either way → §E2.10, M14-FR2 |
| 16 | "$14,730 recovered" fleet dashboard | **PARTIAL** (OBSERVED) | The Meter + DDD exist per-driver; M12-FR4 reporting exists. **Missing:** fleet recovery view with per-broker and per-evidence-class cuts → M14-FR9 |
| 17 | TMS load push | **BUILT as surface** (OBSERVED) | M12-FR6 webhook: load push into F5, claim status out. M14 consumes it, adds nothing |

Net-new work = **M14** (connectors, evidence classes, org approval rules, negotiation assist, linehaul AR, fleet recovery dashboard) + two additive foundation columns (F4 evidence class, F5 remittance linkage) + six owner decisions (D8–D13).

---

## E2.1 Concept

**The same recovery engine, a second sensor, a second buyer, zero driver behavior change.** Haulmeter's claims pipeline currently rides entirely on the driver's phone: app adoption, background permission, an unproven sensor (Phase DoD #4/#8). M14 attaches the identical pipeline to data the fleet's back office already has — the ELD feed, the email inbox, the accounting file — so a 25-truck carrier gets claims drafted with **no driver doing anything**, and the phone becomes the *upgrade* rather than the prerequisite.

**One pipeline, two evidence classes.** M14 does not fork M3/M4. It feeds them. An ELD-derived claim moves through the same states, templates, dunning, and ledger as a phone-verified one; the pack simply declares its basis (M14-FR3). The bet the module exists to measure: recovery rate by evidence class. If brokers pay ELD-grade claims nearly as often, the fleet tier scales without the sensor; where they dispute, phone-verified capture is the documented answer — and the F5 registry learns which broker accepts which, which is the moat the RecoveryOS document names.

**Overlay, not operating system.** Connectors read; they never write into the fleet's systems (single flag-gated exception: FR8 invoice push). M14 is not a TMS, not an ELD, not accounting, and never presents itself as any of them. v1.0 §13's "not an ELD" posture extends verbatim: M14 consumes provider APIs and gives no HOS advice.

**Invoicing party.** P1 claims stay in the driver's name (v1.0 §13 billing-agent posture, unchanged). Fleet-originated claims invoice **in the carrier's name** — the carrier is the contracting party on its own loads, which is the legally *simpler* posture, subject to counsel confirmation (D13).

## E2.2 Actors & roles

- **Fleet admin** (existing F1 role) — primary user: connects systems, sets approval rules, works the queues. A `back_office` member role (F1 org membership) covers dispatchers/clerks without admin rights.
- **Driver** — passive beneficiary. M12-FR1's explicit member consent extends to ELD-derived claim generation, named in the consent screen (D13 wording). Driver-identifiable data still never reaches their counterparty beyond the claim itself (§13 hard policy).
- **Platform admin** (F14) — connector health, classification review queue, autonomy-graduation review.

## E2.3 Functional requirements

Per v2.0 law, every FR names its **validation** — an observation about the world, not the suite.

**M14-FR1 — Mailbox ingest.**
Per-fleet forwarding address first (no OAuth); Gmail OAuth connector second. Every inbound item lands in F6 typed storage, then F9 classifies: `rate_con` → existing F5 parse path (a fleet forwarding its rate cons gets loads created with terms extracted — capability #1 above, no new parse code); `broker_reply` → matched to its F8 `OutboundThread` via `record_inbound_reply`, then FR6; `remittance` → FR7; `unknown` → review queue (F14). **Nothing auto-sends from ingest.**
*Validation:* a fleet that is not the owner's forwards one week of real rate cons and ≥90% create correct loads without manual entry.

**M14-FR2 — ELD/telematics connector (read-only).**
Motive and Samsara first (public APIs; order and terms are D11 — the D6 discipline applies: official APIs only, never scrape). Pulls vehicle stop/location history, normalized into F3 as a second trace source with `source=eld_provider` attribution; geofence evaluation runs over ELD traces against F2 facilities exactly as over device traces. Provider webhooks where offered; polling fallback in the worker (flag-gated job, F13, per the established worker pattern).
*Validation:* an arrival/departure pair derived from a real fleet's ELD feed matches the facility's gate reality within the F3 ±3-minute target on ≥10 stops.

**M14-FR3 — Evidence classes (F4 additive extension).**
Every pack declares its basis: `phone_verified` (hash-chained, EXIF, server timestamps — today's class), `eld_derived` (provider timestamps, provider named), `mixed`. §11.7's honesty discipline aimed at counterparties: the pack never implies chain-of-custody it does not have; the verification block states exactly what anchors what. F5 counterparty records accumulate accept/dispute outcomes *per class* — the FR that turns claims volume into broker intelligence (capability #10).
*Validation:* one broker pays an `eld_derived` pack; one broker's documented dispute of one is answered by a `phone_verified` upgrade on the next load at the same facility.

**M14-FR4 — Fleet claim generation without driver action.**
For connected fleets: dwell beyond free time at a `shipper_receiver` stop auto-drafts the M3 claim (same pipeline, same templates), queued per FR5 rules. When phone evidence exists for the same stop, the pack upgrades to `mixed`/`phone_verified` automatically. Missing-evidence requests (POD photo, signed in/out) go to the driver over F8 SMS/push as a fleet-triggered variant of M5-FR5's nudge — worded as a request, never a demand (v1.0 §5.5 tone law).
*Validation:* a claim drafted purely from ELD data, approved by a fleet admin who is not the owner, is paid by a real broker. **This is the module's headline validation.**

**M14-FR5 — Approval rules engine.**
Per-fleet runtime config (F13 config registry pattern, like `a01.capture_checklist`): auto-send threshold (e.g., complete-evidence claims under $X send on a timer unless held), per-broker overrides, notify-only mode, and hold-all default. Extends M3-FR6's approval posture from a person to an organization's standing rules; the legal posture is unchanged — a human (or their recorded standing rule) authorizes every send.
*Validation:* a fleet sets a rule, and a claim sends under it with the rule's id recorded on the F4 event log.

**M14-FR6 — Inbound negotiation assist (graduated autonomy).**
F9 classifies broker replies on the thread: `doc_request` → fetch the named document from F6 (POD, BOL, signed times) and draft the response with it attached; `partial_offer` → compare against rate-con terms and the fleet's accept-floor (FR5 config): at/above floor drafts an acceptance, below drafts a documented counter; `denial` → drafts the contract-citing follow-up (the "42% deny, 83% pay after documented follow-up" move); `payment_promise` → sets receivable expectation. **Draft-first, always:** everything queues for human approval until the fleet graduates a category per D12 criteria (≥N drafts approved with ≥X% sent unedited); ambiguity or below-floor offers always queue to the M12 claims desk regardless of graduation. Every autonomous action is on the F4 event log.
*Validation:* one real broker doc-request is answered by an approved draft carrying the correct document, and the claim subsequently pays.

**M14-FR7 — Linehaul AR watch.**
Reconcile remittances (FR1 ingest and/or FR8 accounting reads) against F5 load rates and terms. Findings: `short_pay`, `unauthorized_deduction`, `missed_fuel_surcharge`, `stale_invoice` (past terms, no payment). Each opens an F7 receivable of a new class routed through the existing dunning cadence with linehaul-appropriate templates (firmer baseline than accessorial tone — this is the fleet's own billed revenue). This is M9's settlement-auditor pattern pointed at the carrier's AR instead of a company driver's settlement; M9 code is not imported laterally — the pattern is replicated in m14, per the M13/M2 review-pattern precedent.
*Validation:* one real short-pay is flagged, pursued through the pipeline, and the difference is collected.

**M14-FR8 — Accounting connector (QuickBooks Online first).**
Read: invoice/payment status, so FR7 knows what is actually paid rather than inferring from mail. Optional write (separate flag): recovered-accessorial invoices pushed to QBO so the fleet's books match the pipeline. F7's custody posture unchanged — recoveries remit direct to the carrier; the platform's fee is invoiced/ledgered as today, never netted from client funds.
*Validation:* a fleet's QBO shows one pipeline-recovered invoice without manual re-entry.

**M14-FR9 — Fleet recovery dashboard.**
The RecoveryOS homepage number, scoped honestly: **Recovered** (F7 `recovered`, fee-net shown) and **Pending** (open receivables by state/age), with per-broker and per-evidence-class cuts and per-truck normalization. Lives in the Fleet Workspace (web-first, design-prd §18); extends M12-FR4 reporting rather than duplicating it. Numbers-first per §2.3; every figure traceable to ledger rows — this dashboard is a sales artifact and must never say more than the ledger does.
*Validation:* a fleet owner who is not the owner quotes their number unprompted in a pilot check-in.

## E2.4 Data model (schema `m14`; additive foundation columns noted)

- `connector` (fleet_id, kind: `mailbox`|`eld`|`accounting`, provider, auth ref → secrets outside the repo per rule 9, status, last_sync, health)
- `ingest_item` (connector_id, F6 doc ref, classification, confidence, disposition, review_state)
- `trace_import` (connector_id, provider vehicle ref → F1 driver/truck mapping, normalized events) — feeds F3; F3 traces gain `source` attribution (**foundation additive column**)
- F4 pack: `evidence_class` (**foundation additive column**; backfill = `phone_verified`, behavior-preserving per the 0066 discipline)
- `approval_rule` (fleet_id, scope, thresholds, per-counterparty overrides, versioned — the rule id lands on the event log)
- `negotiation_action` (thread ref, classification, draft ref, approval state, graduation category)
- `ar_finding` (load ref, type, expected/received cents, F7 receivable ref, state)
- F5 `Counterparty`: per-evidence-class outcome tallies (**foundation additive**), remittance linkage

Boundaries: `m14` imports `foundation.*.public` + earlier modules' `.public` only (m03/m04/m09-pattern/m12) — legal since M14 is last. import-linter contract added in the first commit (31st contract). Foundation columns are migrations with the §9.3 care: backfilled, no box changes behavior.

## E2.5 API

Fleet-scoped: `/fleet/recovery/connectors` (CRUD + OAuth callbacks + provider webhooks in), `/fleet/recovery/findings`, `/fleet/recovery/approvals`, `/fleet/recovery/negotiation`, `/fleet/recovery/dashboard`, `/fleet/recovery/rules`. Admin (F14): connector health, classification review, graduation review. Driver app: **zero new endpoints.**

## E2.6 UI

Fleet Workspace additions only (design-prd §18 portal rules; registered in the layout harness **in the same commit** per v2.0 acceptance #3 — portals are exempt from LAW 0's order, not §6's floors, per HANDOFF-121 §13.13). Surfaces: Connectors, Approvals queue, Negotiation queue, AR findings, Dashboard. **Zero driver-app changes: no NAV impact, no new notification class, no §22.2 category touched.** Fleet-facing surfaces are English (operators); F15's six-locale law continues to govern anything driver-facing (the FR4 evidence nudge reuses existing translated M5 strings or ships ×6).

## E2.7 Flags & gates (F13)

- `m14_overlay` — master; registered with **no `default_on`** (a capability that has never shipped declares nothing and lets its gates govern — HANDOFF-121 §13.14). Gates: `legal_signoff` (**inherited from M3 and currently unsatisfied — M14 does not launder the claims pipeline past its own precondition**), `provider_terms_accepted` (D11), `carrier_invoicing_counsel` (D13).
- `m14_negotiation_autonomy` — per-category graduation (D12); default OFF, draft-only.
- `m14_linehaul_ar` — FR7; gate: `linehaul_fee_decision` (D10).
- `m14_accounting_write` — FR8 push half only.

## E2.8 Monetization, KPIs, COGS

Accessorial contingency unchanged (~15% automated / 25–30% escalated). Fleet packaging: **$499 / 45-day / up-to-25-truck concierge pilot** (the ClearRoad structure, credited on conversion), converting to D9's model — pure contingency vs. hybrid ($/truck/mo + reduced %). Linehaul-AR fee is D10 (the M4 lumper debate again: recovering the fleet's own billed revenue may price lower than found money, or free as retention). The SAFER 150-carrier community list is this module's pilot pipeline — one call already serves ClearRoad, fleet seats, and M14.

KPIs: connected fleets; % of forwarded rate cons parsed complete; claims auto-drafted per 100 connected stops; **recovery rate by evidence class** (the module's central experiment); $ recovered per truck per month; time-to-first-dollar per fleet (target <14 days from connect); negotiation drafts sent unedited %; F9 cost per claim (per-call tracking exists; expected cents against a fee measured in tens of dollars).

## E2.9 Definition of Done

All of: (a) M14-FR4's headline validation — an ELD-only claim, fleet-approved, broker-paid, fee collected, observed in the ledger; (b) one FR6 doc-request answered and the claim paid; (c) one FR7 short-pay collected; (d) ≥2 fleets that are not the owner's connected and active; (e) evidence-class recovery rates reportable with sample sizes displayed (§8.8 no-false-precision law); (f) tests with every change, 31/31 import-linter, every new portal surface in the harness same-commit.

## E2.10 What approving this reverses, and what it does not

**D8 names two reversals**, logged as such: (1) **v2.0 §4 "no new modules until Phase DoD is met"** — superseded *for M14 only*, on the argument that M14 attacks the Phase DoD's own blockers (a paid claim, revenue without the unproven sensor) rather than adding scope beside them; (2) **v1.0 §16's ELD exclusion, narrowed** — building or registering an ELD stays excluded forever; *read-only consumption of a fleet's existing provider API* is now permitted. §16's other exclusions (turn-by-turn, load board, factoring) stand untouched.

**Unchanged, explicitly:** driver pays $0 forever (M14 is entirely fleet-side); one claims pipeline (M14 feeds M3/M4, never forks them); driver-approves posture for driver-originated claims; §13 privacy hard policy; all nine working rules; the design constitution in full; six locales for anything driver-facing.

**Non-goals for M14 v0:** building ELD/TMS/accounting software; auto-send before graduation; factoring/advances; any vertical beyond trucking (RecoveryOS's horizontal expansion is explicitly out — the wedge is the product); driver-app changes of any kind; scraping or unofficial APIs.

## E2.11 Sequencing & preconditions

Ordered by distance to a validated outcome, per the standing law:

- **Precondition 0 — F-01.** Outbound email must actually leave the box. An owner `.env` action; no M14 work is honest before it.
- **Precondition 1 — `legal_signoff`.** The M3 gate is unsatisfied while the flag is live (every boot says so). D13's counsel touch can resolve both in one engagement.
- **Group 1 (no external dependency):** FR1 forwarding-address ingest, FR3 evidence classes, FR5 rules, FR9 dashboard skeleton. A fleet forwarding rate cons gets value before any OAuth exists.
- **Group 2 (external party):** FR2 ELD (D11 provider accounts), FR8 QBO, Gmail OAuth.
- **Group 3 (graduated):** FR6 autonomy, FR7 linehaul AR (D10).
- **Parallel legwork (owner):** SAFER carrier list; presell 2 pilots on deposit before Group 2 lands — the ClearRoad gate discipline applied here: if community fleet owners won't pay $499 against this pitch, that is a gate input, not a footnote.

## E2.12 Open owner decisions (continuing the v2.0 registry)

| # | Decision | Blocks |
|---|---|---|
| **D8** | Approve this extension — accepting the two named reversals in §E2.10 | Everything |
| **D9** | Fleet pricing: pure contingency vs. hybrid ($/truck/mo + reduced %) | Pilot conversion |
| **D10** | Linehaul-AR fee: contingency, reduced, or free-as-retention | FR7 activation |
| **D11** | ELD provider order and terms path (Motive vs. Samsara first; official APIs only) | FR2 |
| **D12** | Autonomy graduation criteria (N approved drafts, ≥X% unedited, per category) | FR6 beyond draft-only |
| **D13** | Counsel touch: carrier-name invoicing posture + ELD-consent wording + evidence-class disclosure language | FR2/FR4 activation; overlaps the standing M3 `legal_signoff` |

---

## E2.13 The standing warning, aimed here

Carried forward because M14 is unusually exposed to it: *a suite proves the code does what it was written to do; it cannot see the thing nobody built, and the owner cannot see what nobody asked for.* Every connector added is a new place where a green suite can pass over a dead integration — a mailbox that classifies fixtures, an ELD poller that never fires, a webhook nothing calls. The F-01 lesson is the module's founding lesson: **a deferral that cannot fail is indistinguishable from a finished feature.** Every connector ships with an end-to-end proof against the real provider, observed from outside the box, before its flag is eligible — and the validation column above, not the test count, is what "done" means.

*End of Extension E2. Build begins, if approved, with Group 1 behind `m14_overlay` OFF.*
