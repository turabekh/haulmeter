# Product Requirements Document — Consolidated Trucker Platform

**Internal codename:** LONGHAUL (working name only — final brand TBD)
**Document status:** Draft v1.0 for build
**Date:** 20 July 2026
**Owner:** Turaboy
**Scope:** Full product. All modules specified in this document are in scope and will be built in one continuous program.

---

## 1. Executive summary

LONGHAUL is a single mobile-first platform that consolidates the three biggest daily money leaks for US truck drivers — time lost finding parking, dollars lost on fuel, and hours given away unpaid at shipper/receiver docks — into one app built around a truck-aware live map and an evidence engine.

It combines the information layer of Trucker Path (live road intelligence, POIs, crowdsourced statuses), the transaction layer of Truck Parking Club (instantly bookable private parking), and a category neither owns: automated, GPS-verified detention and accessorial pay recovery on a contingency basis. The driver pays $0, permanently. Revenue comes from money already in motion: a take rate on parking bookings, a contingency share of recovered claims, fuel-spread margin, and fleet/B2B layers.

The strategic engine is a data flywheel: every detention event logged is also a facility wait-time data point; facility intelligence plus live parking makes the map the daily-open app; daily opens keep the geofence armed so evidence capture is automatic; and the map surfaces bookable parking at the exact moment of need. Each module solves another module's cold-start problem.

## 2. Problem and market context

- Parking is the top structural problem: drivers spend on average 58 minutes per day searching for parking, worth roughly $5,500/year per driver in lost compensation, against a national shortage estimated at ~1 space per 11 drivers and a crisis costed at over $100B/year to the industry.
- Detention is the top unmonetized problem: carriers report detention on roughly 1 in 6 loads at market rates of $35–120/hr after a standard 2-hour grace period — and are rarely paid, primarily because arrival/departure times are disputed and evidence is assembled too late.
- Fuel is the largest variable expense (~$1,000+/week for OTR), with proven appetite for app-mediated discounts of 15–50¢/gallon.
- The incumbent landscape is fragmented: drivers stack 5–10 single-purpose apps. Trucker Path aggregates information but monetizes the driver via subscriptions and has a weak, criticized routing engine; Truck Parking Club owns the parking transaction but has no daily-engagement surface; detention tools (DMRG, Detention Source) are single-purpose, thin, and either stop at notification or charge the driver a subscription to chase money they are owed.

**Market thesis:** the winning product is the driver's daily co-pilot that is free forever, useful alone from install #1 (no network required), and monetizes only when it makes or saves the driver money.

## 3. Vision and positioning

**One-liner:** *The trucker's daily co-pilot that finds you parking, saves you fuel, and gets you paid for every minute you wait.*

**Positioning against incumbents:**
- vs. Trucker Path: they inform; we transact and recover — and we never charge the driver.
- vs. Truck Parking Club: they are open only when booking; we are open all day, present at the moment of need.
- vs. DMRG / Detention Source: they are single-purpose tools with no audience and no collection muscle; our tracker is armed automatically because the app is already running.

**Product promise to the driver:** every feature either saves you time, saves you money, gets you paid, or protects you. Nothing else ships.

## 4. Target users and personas

- **P1 — Owner-operator (OTR).** One truck, own authority or leased on. Feels every unpaid detention hour and every cent of diesel directly. Primary monetizable persona for claims, parking, and fuel.
- **P2 — Company driver.** Cannot invoice brokers; paid per mile/load by a carrier. Uses the map, parking, protection features, and the settlement auditor (disputing pay with their own carrier). Roughly two-thirds of the driver population — the reach persona.
- **P3 — Small fleet owner / dispatcher.** 3–20 trucks. Wants detention analytics across drivers, parking benefits administration, and facility scorecards for lane pricing. Primary B2B persona.
- **P4 — Property owner.** Repair yard, storage lot, CDL school, warehouse operator with spare truck-adequate space. Supply side of the parking marketplace; wants passive income with zero admin.
- **P5 — Counterparties (brokers, shippers, receivers).** Not users, but every outbound artifact (notices, invoices, evidence packs) is designed for them: professional, contract-citing, dispute-resistant.

## 5. Product principles

1. **Driver pays $0, forever.** No driver subscription, ever. Monetize money in motion only.
2. **Single-player useful on day one.** Every module must deliver value to one driver with zero network. Network effects are an accelerant, never a prerequisite.
3. **Evidence-grade or nothing.** Timestamps, locations, and documents are captured to a standard a broker's accounting department (or a collection attorney) cannot credibly dispute.
4. **Data as byproduct, never as chore.** Drivers are never asked to do unpaid data entry; intelligence is derived from actions they take for their own benefit, and contributions that require effort are paid (points).
5. **Shield and sword.** Every adversarial capability (claims) is paired with a protective one (on-time proof, cargo photos), and all counterparty communication defaults to relationship-preserving tone.
6. **Don't build what liability owns.** No proprietary turn-by-turn navigation, no ELD, no load board. Integrate or deep-link instead.
7. **Offline is the default network condition.** All capture works with zero connectivity and syncs later.

## 6. Build strategy — Common Ground first, then module by module

**Governing rule of this PRD:** we build the **Common Ground first** — the shared foundation (Section 7, components F1–F15) that every module stands on — and only then **build module by module, in order M1 → M12, to the end** (Section 8). This is a single continuous build program executed in one go:

- The build order is a **dependency sequence, not a release-versioning plan.** There is no v1/v2/v3 split anywhere in this document; the product is one complete platform and every module in Section 8 is committed scope.
- **No module UI work begins until the Common Ground is production-quality.** The foundation is treated as an internal product with its own definition of done (Section 7.16).
- **Each module is built end-to-end behind its own feature flag** in the platform's flag registry, to its stated Definition of Done, with tests shipped alongside every change, before the next module begins. Flags exist for operational safety and controlled activation — not for withholding scope.
- **Module boundaries are enforced mechanically** (import-linter, core/UI split): a module may depend on Common Ground services and on the public interfaces of earlier modules only. No lateral imports, no reach-ins.
- **Sequencing rationale:** M1–M2 create the daily surface and the facility keystone; M3–M5 are the differentiating recovery/protection engine that runs on that surface; M6–M7 add the transaction layers (parking, fuel) that require external supply/partners and therefore benefit from an existing audience; M8–M9 are intelligence layers that consume data accumulated by M2/M3 (and bootstrap on heuristics until then); M10–M12 are network, AI-UX, and B2B layers that multiply everything before them.

The remainder of this document specifies the Common Ground (Section 7) and each module (Section 8) separately and completely.

---

## 7. The Common Ground (Foundation Layer)

The Common Ground is the set of shared services, data models, and client infrastructure that all twelve modules consume. It is built first, in full, and treated as an internal product. Nothing in this layer is module-specific; anything module-specific belongs in Section 8.

### 7.1 F1 — Identity, Access & Organizations
One account model, many roles. A single user may simultaneously be a driver, a fleet admin, and a property owner.
- Launch authentication: regular **email/password with no activation/verification step** — drivers onboard in under 60 seconds. Auth is built as a **pluggable method registry** from day one: social sign-in (OAuth) and email/SMS OTP are committed later additions and must slot in without reworking the account schema or session model (one account, multiple linked auth methods).
- Role attachments: `driver`, `fleet_admin`, `property_owner`, `platform_admin`. Organization entities (`fleet`, `property_business`) own memberships and permissions.
- Driver profile: truck/trailer dimensions and equipment type (consumed by map filtering and load context), operating authority type (own MC / leased / company driver — this gates claim-invoicing behavior platform-wide), home time zone.
- Consumed by: every module.

### 7.2 F2 — Canonical Facility Registry (the keystone)
Every module keys off `facility_id`. One physical location = one canonical record, forever.
- Facility types: `truck_stop`, `rest_area`, `shipper_receiver`, `parking_property`, `scale`, `weigh_station`, `fuel_station`, `repair`, plus composites.
- Ingestion pipeline with deduplication: geocoding, geohash/H3 blocking, fuzzy name/address matching, admin merge tools. Sources: OpenStreetMap extract, FHWA/Jason's Law truck-parking datasets, state TPIMS feeds, chain location lists, and user check-ins (which create *candidate* facilities pending confirmation by a second signal).
- Each facility carries: geometry (point + optional lot polygon for geofencing), attributes/amenities, operating hours, and per-module extensions (dwell stats, parking inventory, fuel prices) stored in module-owned tables referencing `facility_id`.
- Consumed by: every module.

### 7.3 F3 — Location & Geofence Engine
The platform's sensory system: background location on the client, geofence evaluation and trace storage on the server.
- Client: background geolocation via Capacitor plugin; adaptive sampling — significant-change mode by default, high-accuracy mode automatically when within an "armed" radius of a destination facility or during an active stop. Battery budget: ≤5%/day in default mode.
- Server: geofence evaluation service emitting `ENTER`, `EXIT`, `DWELL_TICK` events against facility geometries; PostGIS storage of traces (timestamped linestrings) with configurable retention.
- Per-facility geofence tuning (radius/polygon) with feedback loop from confirmed arrivals; target: arrival detection within ±3 minutes of ground truth.
- Time integrity: server time is authoritative; client clock skew is measured per event and recorded; GPS time cross-checks flagged on divergence.
- Consumed by: M1, M2, M3, M4, M5, M8, M9, M10.

### 7.4 F4 — Evidence Engine
Turns raw events into artifacts that survive a dispute.
- Append-only event log per `stop`: every event (geofence, photo, user action, notification sent) is hash-chained (each record's hash includes the previous record's hash) to make tampering evident; chain heads periodically anchored to an external timestamping service.
- Artifact capture: photos with EXIF preserved, GPS coordinates, and server-received timestamps; guided capture flows (framing prompts) supplied per use case by modules.
- Evidence Pack Composer: templated PDF generation (cover summary, event timeline, map snapshot of the trace, artifact appendix, hash-chain verification block). One composer, many templates (detention claim, TONU, on-time proof, cargo condition).
- Consumed by: M3, M4, M5, M9, M12.

### 7.5 F5 — Load & Stop Context
Claims are worthless without contractual context. This service maintains the driver's current work state.
- `Load` object: broker/carrier counterparty, rate, appointment times per stop, accessorial terms (detention rate, free time, TONU terms), reference numbers. Created three ways: rate-confirmation upload parsed by the AI Gateway (primary), manual quick-entry, or fleet/TMS push (M12).
- `Stop` object: links a `load` to a `facility` with an appointment window; the unit around which geofencing arms, evidence accrues, and claims are computed.
- Counterparty registry: brokers/shippers with contact channels, observed payment behavior, and claim history (feeds M8 and M12 analytics).
- Consumed by: M3, M4, M5, M8, M9, M11, M12.

### 7.6 F6 — Documents Service
- Object storage (S3-compatible) with typed documents: `rate_con`, `bol`, `pod`, `lumper_receipt`, `cdl`, `med_card`, `insurance`, `permit`, `settlement`, `other`.
- OCR/vision extraction via AI Gateway on upload; extraction results stored as structured metadata alongside the file.
- Expiry engine: documents with validity dates emit reminders (30/14/3 days) through F8.
- Consumed by: M3, M4, M5, M6, M9, M12.

### 7.7 F7 — Ledger & Payments
One double-entry ledger for all value flows: booking payments, owner payouts, recovered claims, contingency fees, fuel transactions, and points.
- Stripe for card processing; Stripe Connect for property-owner and (where applicable) driver payouts — deliberately structured so the platform never takes custody in a way that triggers money-transmitter licensing.
- Claim receivables tracked as ledger objects with states (`invoiced`, `acknowledged`, `disputed`, `escalated`, `recovered`, `written_off`).
- Points are a ledger currency with a defined redemption rate against parking bookings only (no cash-out), earned per F10 trust-weighted contributions.
- Consumed by: M3, M4, M6, M7, M10, M12.

### 7.8 F8 — Notifications & Outbound Communications
- Inbound-to-driver: push (FCM/APNs), SMS (Twilio), email. Quiet-hours aware; safety-aware (no interaction prompts while vehicle in motion — voice summaries via M11 instead).
- Outbound-to-counterparty: transactional email service with per-thread tracking (sent/opened), templated professional documents, reply-to routing into the platform. All counterparty templates are contract-citing and relationship-preserving by default.
- Template registry versioned alongside the prompt registry (F9).
- Consumed by: every module.

### 7.9 F9 — AI Gateway
Single service wrapping all model calls; no module calls a model API directly.
- Capabilities: document parsing (rate cons, settlements, receipts), drafting (counterparty communications), speech-to-text and text-to-speech (for M11), embeddings (pgvector) for facility/review search, and structured-output enforcement.
- Prompt/version registry with evaluation fixtures per task; per-call cost tracking and budgets per module.
- Consumed by: M2, M3, M4, M5, M8, M9, M11, M12.

### 7.10 F10 — Crowd Data Pipeline
- Submission API for statuses (parking fullness, weigh station open/closed, fuel price confirmations, facility attribute corrections) with source, location proof (submitter's geofence presence), and timestamp.
- Trust scoring per contributor; time-decay functions per data type (parking status decays in hours; amenities decay in months); aggregation jobs producing the "current best belief" per facility per signal.
- Points issuance hooks into F7.
- Consumed by: M1, M2, M7, M10.

### 7.11 F11 — Map & POI Serving
- Tile provider: Mapbox (or equivalent); truck-relevant styling and night mode as first-class.
- POI overlay API: clustered facility pins with per-module badge layers (live status, bookable, fuel price, dwell rating) composed server-side from module tables.
- Corridor query primitive: "facilities of type X within Y minutes of my route/heading" — shared by M1, M7, M8.
- Consumed by: M1, M2, M6, M7, M8, M10.

### 7.12 F12 — Offline Sync & Outbox (client infrastructure)
Trucking's default network condition is "none."
- Client-side event outbox: every capture (geofence event acknowledgment, photo, status report, claim action) is written locally first (SQLite/IndexedDB), queued, and synced with idempotency keys when connectivity returns. Server timestamps record both `occurred_at` (client, skew-corrected) and `received_at`.
- Read-side caching: last-known map region, active load context, and document wallet available fully offline.
- Consumed by: every module.

### 7.13 F13 — Feature Flags, Validation Gates & Config Registry
- Central flag registry: every module and every risky sub-feature ships behind a flag with kill-switch semantics; flags are configuration, not code branches left to rot.
- Validation-gate hooks: per-module activation checklists (legal sign-off items, partner agreements in place, insurance bound) enforced as flag preconditions in the registry — operational gates within the single build, not release phases.
- Runtime config: rate tables (detention defaults by equipment type), geofence tuning parameters, points economy rates, fee percentages.
- Consumed by: every module; owned by platform.

### 7.14 F14 — Admin Console & Analytics
- Ops console: facility merge/edit, claim pipeline management, booking/refund handling, contributor trust management, counterparty registry curation, content moderation queue (reviews), template/prompt editing.
- Product analytics: event instrumentation standard, per-module KPI dashboards (Section 14), cohort retention, funnel views.
- Consumed by: platform operations; every module registers its admin views here.

### 7.15 F15 — Localization & Language Services
Incumbent trucker apps are English-only; Punjabi-, Russian-, Uzbek-, Somali-, and Spanish-speaking drivers are large, underserved segments of the US fleet — full multilingual operation is an acquisition wedge, not a compliance checkbox.
- Launch languages (all shipped, none deferred): **English, Spanish, Punjabi, Russian, Uzbek (Latin script), and Somali**; Amharic is the designated next candidate. Per-user locale lives on the F1 profile and is chosen at onboarding (and switchable anytime).
- Coverage rule: every driver-facing surface — UI, notifications (F8), voice (M11 via F9 STT/TTS), and help content — renders in the user's language. Counterparty-facing artifacts (invoices, notices, evidence packs, the public scorecard) are **always English**: they are US legal/commercial documents.
- Translation pipeline: full string externalization with ICU message formatting; AI-assisted translation through F9 with native-speaker driver review before release; a maintained trucking-term glossary keeps recognized English jargon (detention, lumper, rate con, BOL) untranslated where drivers use the English terms regardless of language.
- Units remain imperial (miles, gallons, feet/inches) in every language — this is US trucking.
- Voice: per-language STT/TTS via the F9 gateway, including mixed-language utterances with embedded English trucking terms.
- Consumed by: every module; hard dependency for F8 templates, F9 prompts, and M11.

### 7.16 Foundation Definition of Done
The Common Ground is complete when: (a) all fifteen components pass their test suites in Docker-composed CI; (b) a synthetic end-to-end scenario runs green — a test driver with a parsed rate con is geofence-armed at a seeded facility, generates a hash-chain-valid evidence pack PDF offline, syncs it, and triggers a templated counterparty email with a ledger receivable — exercising F1–F9 and F12 in one flow; (c) the flag registry, admin console, and analytics pipeline are operational; (d) module scaffolds (empty bounded contexts with enforced import boundaries) exist for M1–M12; and (e) every driver-facing string in the app shell is externalized, with all six launch-language packs loading and rendering correctly (F15).

---

## 8. Modules

Each module below is committed scope, specified separately, and built in the stated order after the Common Ground. Format per module: Purpose · Primary users · User stories · Functional requirements (FR) · Foundation dependencies · Monetization · KPIs · Definition of Done (DoD) · Notes.

---

### 8.1 M1 — Road Intelligence Map
**Purpose:** the daily-open surface. A truck-aware live map of everything a driver needs on the road, replacing Trucker Path's core informational value without its subscription creep.
**Primary users:** P1, P2, P3.
**User stories:** As a driver, I open one map and see truck stops, rest areas, scales, weigh stations, and fuel prices along my corridor, filtered by my rig and my needs, with live statuses I can trust.
- M1-FR1: Truck-aware map with POI layers per F2 facility types; filterable by amenities, and by rig dimensions from the F1 profile.
- M1-FR2: Live parking status per facility (Empty / Some / Full) computed by F10 from crowd reports, TPIMS public feeds where available, and passive signals (anonymized dwell density from F3 opt-in traces).
- M1-FR3: Parking status prediction per facility per hour (historical model, heuristic until M8 upgrades it), displayed as "usually fills by 6pm".
- M1-FR4: Weigh station status layer (open/closed) from crowd reports with recency indicators.
- M1-FR5: Fuel price display layer per station (crowd-confirmed and/or feed-based; becomes transactional in M7).
- M1-FR6: Corridor mode: ordered list of upcoming facilities along current heading/route with ETAs (F11 corridor primitive).
- M1-FR7: One-tap status contribution ("lot is full") gated by geofence presence proof; issues points (F7/F10).
- M1-FR8: Deep-link handoff to external navigation (Google Maps / Hammer / CoPilot) for turn-by-turn — explicitly no in-house routing.
- M1-FR9: Full offline behavior: last-synced region browsable; contributions queue via F12.
**Foundation dependencies:** F1, F2, F3, F10, F11, F12.
**Monetization:** none directly; engagement engine for all transactional modules.
**KPIs:** DAU/MAU ≥ 40%; median sessions/day ≥ 3 for active OTR drivers; % of tracked corridors with fresh (<4h) parking status.
**DoD:** map performant to 50k POIs; status pipeline live end-to-end (report → aggregate → pin badge) under 60 seconds; offline region cache verified; contribution-with-proof flow shipped.
**Notes:** honesty in the UI about data freshness ("reported 40 min ago by 3 drivers") is a trust feature, not a weakness.

---

### 8.2 M2 — Facility Intelligence & Scorecard
**Purpose:** the layer no incumbent owns properly — canonical profiles of shippers/receivers with objective dwell statistics and structured driver reviews; the public output is a facility scorecard that gives drivers leverage and the platform free press.
**Primary users:** P1, P2, P3; P5 as subjects.
**User stories:** As a driver, before I accept or arrive at a stop, I see what to expect: average dock time by time of day, check-in procedure, overnight parking, backing situation, hazards, and what other drivers say. As a fleet owner, I price lanes with facility dwell data.
- M2-FR1: Facility profile page per F2 `shipper_receiver`: attributes (check-in procedure, PPE rules, restrooms, overnight parking allowed, backing type, hazards), structured 10-aspect driver ratings, and free-text reviews (moderated via F14).
- M2-FR2: Objective dwell statistics computed from F3/F4 stop events: median/percentile dock time overall and by arrival-hour bucket; sample sizes always displayed.
- M2-FR3: Detention-risk indicator per facility derived from M3 claim events (rate of stops exceeding free time).
- M2-FR4: Post-stop micro-review prompt (30 seconds, optional, points-earning) auto-triggered by geofence EXIT — data as byproduct, never a chore.
- M2-FR5: Public scorecard: web-published, aggregated, anonymized facility rankings (best/worst dwell by region/industry), refreshed monthly; individual driver data never identifiable.
- M2-FR6: Facility search with semantic review search (F9 embeddings): "receivers near Dallas that unload overnight".
- M2-FR7: Facility self-service claim page for P5 counterparties to correct factual attributes (hours, procedures) — never to edit ratings or statistics.
**Foundation dependencies:** F2, F3, F4, F9, F10, F14.
**Monetization:** none directly; feeds M8 pricing intelligence and the M12 data product; scorecard is the marketing engine.
**KPIs:** % of driver stops occurring at facilities with a populated profile; reviews per 100 stops; scorecard press pickups/backlinks.
**DoD:** dwell statistics pipeline validated against manually verified stops; moderation queue operational; public scorecard live with legal-reviewed methodology page.
**Notes:** publish only aggregated factual measurements plus clearly-attributed user opinions; the methodology page and moderation policy are the defamation shield (Section 13).

---

### 8.3 M3 — Detention Tracker & Recovery
**Purpose:** the differentiator and acquisition wedge. Zero-effort, GPS-verified detention evidence; a live detention clock; professional automated claims; and contingency recovery so the driver never pays to chase money they're owed. (This is the AirHelp pattern applied to dock time: legally owed money, counterparty friction, and automation making small claims economical at scale.)
**Primary users:** P1, P3 (P2 receives evidence-only mode for use with their carrier).
**User stories:** As an owner-operator, I upload my rate con, drive to the stop, and do nothing else: the app proves when I arrived, warns the broker before detention starts, invoices them the moment it accrues, and if they ignore it, someone collects for me — and I only ever pay a cut of what's recovered.
- M3-FR1: Stop arming: active `stop` (from F5) arms the geofence; ENTER/EXIT and dwell events accrue to the F4 evidence log automatically, offline-safe (F12).
- M3-FR2: Live detention clock in-app: free time countdown from the contractually correct trigger (appointment vs. arrival per rate-con terms), then accrual at the load's detention rate; on-screen and via M11 voice.
- M3-FR3: Pre-detention counterparty notice: at configurable threshold (default 30 min before free time expires), templated notice to broker/shipper contact (F8) — "real-time notice" is the claims-stickiness requirement.
- M3-FR4: Detention-start and detention-accruing notices with live evidence links.
- M3-FR5: One-tap claim pack on EXIT: Evidence Pack PDF (F4 composer) + invoice generated **in the driver's name** (billing-agent model) at the load's rate, sent via tracked email thread (F8), receivable opened in F7.
- M3-FR6: Claim pipeline states with automated dunning cadence (day 3 nudge, day 10 firm, day 21 escalation offer), all templates relationship-preserving and contract-citing (F9 drafting, driver approves before send — "notify-only" mode available).
- M3-FR7: Escalation: driver one-tap consents to hand the claim to the integrated licensed transportation collection partner; partner fee tier applies; status syncs back into the pipeline.
- M3-FR8: BOL/paperwork photo prompts at check-in and release (guided capture, F4), attached to the pack automatically.
- M3-FR9: Company-driver mode (P2): identical evidence capture and pack generation, no invoicing; pack export formatted for submission to their carrier (feeds M9 settlement auditing).
- M3-FR10: Every completed stop writes dwell data to M2 regardless of whether detention occurred.
**Foundation dependencies:** F1–F9, F12, F13 (activation gated on collection-partner agreement + legal sign-off flags).
**Monetization:** contingency fee on recovered amounts — ~15% for claims paid via automated invoice/dunning; ~25–30% on partner-escalated collections (benchmarked to commercial transportation collections at 10–25%, higher for aged/complex accounts; our same-day GPS-verified claims are the freshest and most collectible class).
**KPIs:** % of stops with complete evidence capture (target >95% of armed stops); claims submitted per 100 detention-eligible stops; recovery rate; median days-to-payment; contingency revenue per active P1/month.
**DoD:** end-to-end flow (rate con → armed stop → clock → notices → pack → invoice → receivable → recovery-marked) shipped and exercised against ≥3 real claim templates; escalation partner integration contract-signed and technically live; company-driver mode shipped.
**Notes:** the single most important unknown in this PRD is the automated-stage recovery rate; instrument it from the first claim (Section 17).

---

### 8.4 M4 — Accessorial Recovery Suite
**Purpose:** the same evidence-and-invoice rail, extended to the other accessorials nobody bundles: layover, TONU (Truck Ordered Not Used), and lumper reimbursement.
**Primary users:** P1, P3.
**User stories:** As an owner-operator, when a load falls through after I've committed, or I'm held overnight, or I pay a lumper out of pocket, the money comes back without me building a paper trail by hand.
- M4-FR1: TONU claims: geofence-proven arrival (or dispatch-time proof for pre-arrival cancellation) + rate-con terms → TONU invoice via the M3 pipeline; typical values $150–500.
- M4-FR2: Layover claims: overnight dwell detection at a stop facility + terms → layover invoice via the M3 pipeline.
- M4-FR3: Lumper capture: receipt photo at the dock → OCR (F6/F9) → reimbursement invoice to broker auto-drafted with load reference attached; ledger tracks reimbursement separately from earnings.
- M4-FR4: Accessorial terms extraction from rate cons (F5/F9) with a driver-confirm step; missing terms trigger a pre-acceptance warning ("this rate con is silent on detention/TONU").
- M4-FR5: Unified "Money Owed" view: all receivables (M3+M4) with states, aging, and one-tap actions.
**Foundation dependencies:** F4–F9; M3 pipeline (public interface).
**Monetization:** same contingency structure as M3; lumper reimbursements at a reduced fee (they are pass-through costs, not earnings) or free as a retention feature — decision flag in F13.
**KPIs:** accessorial claims per active P1/month; recovery rate by claim type; % of rate cons parsed with complete accessorial terms.
**DoD:** all three claim types generate valid packs and invoices through the shared pipeline; "Money Owed" view live.
**Notes:** M4 exists as a separate module (not M3 scope-creep) so the claim-type registry, templates, and analytics stay independently testable.

---

### 8.5 M5 — Protection & Document Wallet
**Purpose:** the shield to M3/M4's sword. The same evidence engine pointed at protecting the driver from chargebacks, false cargo claims, and roadside friction.
**Primary users:** P1, P2, P3.
**User stories:** As a driver, my on-time arrival is provable before anyone accuses me of being late; my trailer's condition is documented before and after every load; and every credential I need at an inspection is one tap away and never silently expired.
- M5-FR1: On-time arrival proof: geofence ENTER inside the appointment window auto-fires a timestamped "checked in at 07:58" notification to the counterparty (opt-in per load) and files the proof artifact — near-zero cost, runs on M3's arming.
- M5-FR2: Cargo-condition protocol: guided photo sequences (trailer exterior, seals, load blocking, reefer setpoint) at pickup and delivery; geotagged, timestamped, hash-chained (F4); one-tap condition report export.
- M5-FR3: Document wallet: CDL, med card, insurance, permits, IFTA license, rate cons — typed storage (F6), expiry alerts, offline access, one-screen "inspection mode" presentation.
- M5-FR4: Incident capture: generic evidence flow (photos + notes + location) for accidents, damage discoveries, or disputes, producing a shareable pack.
- M5-FR5: Protection summary per load: what's documented, what's missing, nudges before gaps become risks.
**Foundation dependencies:** F3, F4, F5, F6, F8, F12.
**Monetization:** none; retention, habit-formation (keeps background location justified and armed), and P2 reach.
**KPIs:** % of loads with pickup+delivery photo sets; document wallet adoption; expiry-alert saves (documents renewed before lapse).
**DoD:** all five FRs shipped; inspection mode usable offline in <2 taps from app open.
**Notes:** M5 is the App Store narrative for background location: continuous, user-visible benefit.

---

### 8.6 M6 — Parking Marketplace
**Purpose:** the transaction layer — instantly bookable private truck parking fused into the same map, with a property-owner portal that makes supply effortless. TPC's validated model, minus the separate app.
**Primary users:** P1, P2 (demand); P4 (supply); P3 (fleet-paid parking, completed in M12).
**User stories:** As a driver at 6pm watching every public lot read Full, the map shows me a guaranteed spot four miles ahead, priced, bookable in two taps against my HOS clock. As a property owner, I list spare spots once and money shows up.
- M6-FR1: Listings: property onboarding (vetting checklist, no residential), spot inventory, pricing (hourly/daily/weekly/monthly), amenities, photos, rules; owner sets rates.
- M6-FR2: Real-time availability and instant booking; payment captured on booking (F7 Stripe), platform take deducted, owner payout via Connect.
- M6-FR3: The closing loop: when M1 shows public lots Full/likely-full on the driver's corridor, bookable inventory is surfaced in the same view, framed against remaining HOS time.
- M6-FR4: Check-in/out via the existing geofence (F3): arrival confirmation, overstay detection, and dispute evidence for free.
- M6-FR5: Owner portal (web, Quasar): calendar, bookings, payouts, blackout dates, simple analytics; designed for zero-admin operation.
- M6-FR6: Reviews both ways (driver↔property) via the F10/F14 pipelines.
- M6-FR7: Cancellation/refund policy engine with automated enforcement; 24/7 support escalation path staffed via ops (F14).
- M6-FR8: Fleet booking hooks (shared payment method) stubbed for M12 completion.
**Foundation dependencies:** F1, F2, F3, F7, F8, F11, F13 (activation gated on refund policy + damage/liability posture flags), F14.
**Monetization:** take rate on every booking, designed at 15–20% all-in, baked into the owner side so the driver sees one transparent price (drivers are already ambivalent about pay-to-park; no checkout surprises).
**KPIs:** listed spots per target corridor; booking conversion from "Full nearby" moments; GMV; take-rate revenue; repeat-booking rate; owner churn.
**DoD:** full booking→payout loop live with real money in test-mode parity; owner portal shipped; corridor supply playbook document (Section 12) executed for the first corridor.
**Notes:** damage coverage (TPC offers up to $25K/booking) is a competitive checkbox — resolve the insurance open question (Section 17) before flag activation, not before build.

---

### 8.7 M7 — Fuel Savings Network
**Purpose:** the sleeper economics: negotiated discounts at fuel merchants, paid through the app, platform keeps a per-gallon spread. Mudflap's model, fused into the corridor view.
**Primary users:** P1, P3.
**User stories:** As an owner-operator, the map shows my net price after discount along my corridor; I tap, get a payment code at the pump, and save 15–50¢/gallon with no card, no fees, no minimums.
- M7-FR1: Merchant network management: discount agreements, per-station net pricing, settlement terms (F14 admin).
- M7-FR2: Discounted price display integrated into M1's fuel layer: gross vs. your-net price, corridor-ranked by true cost including deviation miles.
- M7-FR3: In-app fuel payment: code/QR at pump via payment partner integration; transaction recorded to F7 ledger with spread accounting.
- M7-FR4: Fuel spend analytics per driver: gallons, savings-to-date, IFTA-ready export hook (M9).
- M7-FR5: Crowd price confirmation (F10) keeps non-network station prices honest on the same layer.
**Foundation dependencies:** F2, F7, F10, F11; M1 (fuel layer).
**Monetization:** retained spread per gallon (single largest per-driver revenue potential at OTR volumes of ~1,500–2,000 gal/month); no driver fees ever.
**KPIs:** network stations live; attach rate (% of active P1s transacting monthly); gallons/month; spread revenue per transacting driver.
**DoD:** end-to-end discounted purchase at ≥1 live merchant partner; settlement reconciliation in ledger verified.
**Notes:** build the module fully; merchant acquisition is a business-development track that runs in parallel and gates *activation* (F13), not build. Payment-partner selection is an open question (Section 17).

---

### 8.8 M8 — Decision Intelligence
**Purpose:** turn the platform's proprietary data into the decisions drivers make ten times a week. This is where the ML background becomes the moat.
**Primary users:** P1, P3.
**User stories:** As an owner-operator, before I accept a load I see its *true* profit — rate minus route fuel, tolls, and the expected detention cost at that specific receiver. Before I book an appointment I see which hour gets me unloaded fastest. At day's end, one answer to "where do I sleep tonight."
- M8-FR1: True-profit load calculator: input rate con or manual load → net = revenue − route fuel (M7 net prices) − tolls − expected accessorial time cost from M2/M3 facility distributions; output rate-per-mile *after* this receiver's dwell history.
- M8-FR2: Appointment-time optimizer: per-facility dwell-by-hour model with recommendations ("06:00 averages 40 min; 14:00 averages 3.5 h") and confidence based on sample size.
- M8-FR3: "Where do I sleep tonight" solver: remaining HOS input (manual entry; no ELD integration in scope) + corridor + live/predicted parking (M1) + bookable inventory (M6) + fuel plan (M7) → ranked stop recommendations.
- M8-FR4: Parking-fill prediction service upgrading M1-FR3 from heuristic to learned model.
- M8-FR5: All models bootstrap on heuristics + public data and improve as M2/M3 data accumulates; every prediction displays its basis (sample size / heuristic) — no false precision.
- M8-FR6: Detention-risk pre-acceptance flag: "this facility exceeds free time on 43% of tracked stops."
**Foundation dependencies:** F2, F5, F9, F11; consumes M1, M2, M3, M6, M7 data via public interfaces.
**Monetization:** none directly; drives claim volume (M3), bookings (M6), and fuel attach (M7); core of the M12 data product.
**KPIs:** calculator uses per active P1/week; prediction calibration (Brier score on parking-fill); % of accepted loads pre-checked.
**DoD:** all three headline tools shipped with basis-transparency; prediction pipeline retraining on schedule; calculator validated against hand-computed loads.
**Notes:** deliberately sequenced late in the build so real data exists; heuristic fallbacks mean it ships complete regardless.

---

### 8.9 M9 — Driver Money & Tax Tools
**Purpose:** the quiet compounders that make the app the driver's financial system of record — and the wedge into the company-driver majority.
**Primary users:** P2 (auditor), P1 (tax tools).
**User stories:** As a company driver, I upload my weekly settlement and the app flags the detention and layover pay my carrier missed, with my own GPS evidence attached. As an owner-operator, my state-by-state miles and per-diem days compile themselves.
- M9-FR1: Settlement auditor: settlement upload → AI parse (F9) → reconciliation against the driver's own F4/F5 stop and load history → discrepancy report (missed detention/layover/bonus) with attached evidence packs formatted for carrier submission.
- M9-FR2: IFTA mileage: state-by-state miles computed from F3 traces (jurisdiction boundary crossing), monthly/quarterly export (CSV/PDF).
- M9-FR3: Per-diem day counter: nights-away detection from traces + home base; tax-year export.
- M9-FR4: Earnings dashboard: settlements + recovered claims (M3/M4) + fuel savings (M7) in one view; feeds the North Star metric.
- M9-FR5: Expense capture-lite: receipt photos (F6 OCR) categorized for tax export — explicitly not full accounting software.
**Foundation dependencies:** F3, F4, F5, F6, F9; M3 (packs), M7 (fuel data).
**Monetization:** none directly; P2 acquisition and platform stickiness (justifies always-on background location alongside M5).
**KPIs:** settlements audited/month; discrepancy find rate and $ flagged; IFTA export users; P2 share of MAU.
**DoD:** auditor validated against ≥20 real anonymized settlements across ≥3 carrier formats; IFTA output cross-checked against a commercial calculator.
**Notes:** position auditor output as "review with your carrier," not legal advice; template tone matters as much as with brokers.

---

### 8.10 M10 — Community & Points Economy
**Purpose:** pay drivers for the data everyone else extracts for free, and create peer-to-peer liquidity incumbents structurally can't copy.
**Primary users:** P1, P2.
**User stories:** As a driver, my parking reports, reviews, and price confirmations earn points I redeem against paid parking. When I'm pulling out of a full lot, I tap "leaving in 15" and another driver gets my spot instead of circling.
- M10-FR1: Points economy: earn rules per contribution type (trust-weighted via F10), redemption solely against M6 bookings at a fixed rate (F7 ledger currency); anti-gaming controls (geofence presence proof, rate limits, trust decay).
- M10-FR2: Spot handoff relay: "leaving in X min" broadcast from a geofence-confirmed present driver at a public facility; claimable by one nearby driver; both earn points on confirmed handoff (claimer's subsequent ENTER). Free-lot only — never cannibalizes M6 inventory (the structural move TPC cannot make).
- M10-FR3: Contributor reputation: levels, streaks, corridor leaderboards — light, dignified, no cringe.
- M10-FR4: Moderated facility Q&A ("is the north entrance still closed?") pinned to facility pages (M2), answerable by geofence-present drivers.
**Foundation dependencies:** F3, F7, F10, F14; M1, M2, M6.
**KPIs:** contributions per DAU; handoff success rate; points-funded share of M6 bookings; contributor retention vs. non-contributors.
**Monetization:** indirect — points redemption is partially circular against the M6 take rate; data quality lifts every module.
**DoD:** full earn→redeem loop live; handoff relay shipped with abuse controls; economy parameters tunable via F13 config.
**Notes:** the relay is the highest-novelty bet in this PRD; ship it with conservative geofence proof requirements and iterate parameters via config, not code.

---

### 8.11 M11 — Voice Copilot & AI Communications
**Purpose:** the AI-native UX layer: hands-free access to everything (hands are on the wheel 11 hours a day), and a ghostwriter that removes the tone problem suppressing claims.
**Primary users:** P1, P2, P3.
**User stories:** As a driver in motion, I ask "any parking near exit 42 around seven?" or say "start my detention clock" and it happens. When I need to push a broker, the message that goes out is firm, professional, and cites the contract — because the app wrote it and I approved it.
- M11-FR1: Voice interface (F9 STT/TTS) over platform intents: parking/fuel/facility queries (M1/M2/M8), detention clock status and actions (M3), load context questions (F5), booking initiation (M6, confirm-on-screen when stopped).
- M11-FR2: Motion-aware interaction policy: voice-first with audio responses while in motion; visual confirmations deferred (F8 safety rules).
- M11-FR3: Comms ghostwriter: counterparty message drafting (detention notices, rate-con clarifications, polite escalations, carrier disputes) with tone presets from relationship-preserving to firm; driver always approves; templates/prompts versioned (F8/F9).
- M11-FR4: Conversational claim assistant: "what am I still owed and what's the next action on each?" over the M3/M4 receivable state.
- M11-FR5: Wake interaction via on-screen button and headset controls (no always-on hotword in scope).
- M11-FR6: Full multilingual voice operation in all six launch languages (F15/F9), handling mixed-language utterances with embedded English trucking terms; ghostwriter accepts driver input in any launch language and always outputs counterparty messages in English.
**Foundation dependencies:** F5, F8, F9, F15; consumes M1–M6, M8 interfaces.
**Monetization:** none directly; differentiated UX incumbents' tap-based apps can't match; lifts claim submission volume (revenue-adjacent).
**KPIs:** voice sessions per driving-hour DAU; ghostwriter adoption per claim; claim-submission lift for ghostwriter users.
**DoD:** ≥15 intents live with ≥95% intent-routing accuracy on the eval fixture set (F9 registry) in each launch language; ghostwriter shipped across all counterparty templates (English outbound per F15); motion policy verified.
**Notes:** voice quality over an app's *own structured data* is a tractable, high-payoff problem — this is not open-domain assistant scope.

---

### 8.12 M12 — Fleet & B2B Layer
**Purpose:** the multiplier: fleet accounts that buy per-seat, and the aggregated data product the industry argues about today.
**Primary users:** P3; data buyers (brokers/shippers/3PLs).
**User stories:** As a small fleet owner, I onboard my drivers, give them a parking benefit on a shared payment method, see detention exposure across my fleet by facility, and recover it centrally. As a lane analyst, I buy facility dwell benchmarks nobody else can produce.
- M12-FR1: Fleet workspace: driver invitations, roles, consolidated views over member drivers' loads, stops, claims, and protection status (member consent explicit at join).
- M12-FR2: Parking benefits: shared payment methods, monthly allowances, booking policies (completes M6-FR8).
- M12-FR3: Fleet claims desk: centralized M3/M4 pipeline across drivers; fleet-level counterparty analytics (which brokers pay detention, which facilities burn hours).
- M12-FR4: Fleet reporting: dwell exposure, recovered $, fuel savings, IFTA rollups (M9) per driver and fleet-wide.
- M12-FR5: Data product: subscription access to aggregated, anonymized facility dwell benchmarks and lane friction indices; aggregate-only, minimum-sample thresholds, never identifiable driver data, and never sold in a form usable against an individual contributor (hard policy, Section 13).
- M12-FR6: TMS/webhook API: load push into F5, claim status out — integration surface, not a TMS.
**Foundation dependencies:** F1, F5, F7, F14; consumes M2, M3, M4, M6, M7, M9 interfaces.
**Monetization:** per-seat fleet subscription; data-product subscriptions; fleets also amplify M3/M6/M7 transactional volume.
**KPIs:** fleets onboarded; seats; fleet-originated claim volume and GMV; data-product ARR.
**DoD:** fleet workspace end-to-end with ≥1 design-partner fleet exercising benefits + claims desk; data product live with published methodology and privacy policy.
**Notes:** M12 last because it multiplies everything before it and needs the data the earlier modules generate.

---

## 9. Monetization model (consolidated)

Driver price: **$0, permanently.** All revenue is a share of money already in motion.

| Stream | Module | Mechanism | Design parameters | Illustrative unit economics |
|---|---|---|---|---|
| Parking take rate | M6 | % of each booking, baked into owner side | 15–20% all-in; owner joins free, no contracts | 3–4 paid nights/mo × ~$25 → $13–18/driver/mo |
| Detention & accessorial contingency | M3, M4 | % of recovered claims only | ~15% automated-stage; 25–30% partner-escalated (commercial collections benchmark: 10–25%, fresh claims collect best) | ~1.5 events/mo × $150 avg × 50% recovery × 20% → ~$20–25/driver/mo |
| Fuel spread | M7 | Retained ¢/gal on network purchases | Driver saves 15–50¢/gal; platform retains low single-digit ¢/gal | 1,500–2,000 gal/mo × 3–5¢ → $50–100/driver/mo |
| Fleet subscriptions | M12 | Per-seat SaaS | Benefits admin + claims desk + analytics | Priced at pilot |
| Data product | M12 | Aggregated facility/lane benchmarks subscription | Aggregate-only, minimum-sample, hard privacy policy | Priced at pilot |

Blended potential at maturity is ~$85+/month per fully monetized driver; model conservatively at 15–25% of MAU monetizing in any month. Revenue activation order follows the build order's dependency logic: contingency first (needs only a collections partner), parking corridor-by-corridor as supply signs, fuel once volume gives negotiating leverage, fleet/data once there is something to aggregate. Activation is controlled by F13 flags — it is not a build-phasing mechanism.

## 10. Technical architecture and stack

Consistent with the platform engineering standards used across ventures: fixed stack, Docker-only environments, maximum modularity with mechanically enforced boundaries, tests with every change, plan-first execution.

- **Backend:** FastAPI modular monolith. One deployable; one Python package per module (`m01_map` … `m12_fleet`) plus `foundation/*` packages for F1–F15. import-linter contracts enforce: modules → foundation allowed; modules → earlier-module *public interfaces* allowed; lateral/reach-in imports forbidden; core/UI split enforced.
- **Data:** PostgreSQL 16 with PostGIS (geometry, traces, geofences, jurisdiction boundaries for IFTA) and pgvector (F9 embeddings). Single database, schema-per-module ownership; cross-module reads via views/interfaces only. Redis for cache/queues; background workers for geofence evaluation, aggregation jobs, dunning cadences, and ML batch jobs.
- **Clients:** Quasar/Vue 3 single codebase → Capacitor builds for iOS/Android + PWA/web (owner portal and fleet workspace are web-first). Swappable-UI discipline: all business logic in the core layer, UI framework replaceable. Background geolocation via Capacitor community plugin with the F3 adaptive-sampling policy.
- **Storage & services:** S3-compatible object store (F6); Stripe + Stripe Connect (F7); Twilio + FCM/APNs + transactional email (F8); Mapbox (F11); LLM/STT/TTS behind the F9 gateway exclusively.
- **Environments:** Docker Compose for dev and CI parity; single-region deploy initially; infrastructure sized to a 100k-MAU design point with horizontal worker scaling.
- **Testing:** every FR maps to at least one automated test; the F7.15-style synthetic end-to-end scenario runs in CI permanently; module DoD includes green suite in composed CI.

## 11. Non-functional requirements

- **Offline-first:** all capture paths (evidence, statuses, photos, claims actions) function with zero connectivity and sync idempotently (F12). Target: no data loss at 24h offline.
- **Battery:** ≤5%/day in default tracking mode; high-accuracy only when armed (F3).
- **Time & evidence integrity:** server-authoritative time, client-skew recording, hash-chained event logs with external anchoring (F4); evidence packs verifiable by a third party.
- **Geofence accuracy:** arrival detection within ±3 minutes at tuned facilities; tuning feedback loop mandatory.
- **Reliability:** 99.5% availability target; claims and bookings pipelines idempotent end-to-end.
- **Usability:** glove-friendly touch targets, high-contrast night mode, voice access to all core actions while in motion (M11), and full multilingual operation in all six launch languages per F15 — English, Spanish, Punjabi, Russian, Uzbek, and Somali — across UI, notifications, and voice.
- **Privacy & security:** location data encrypted at rest; role-scoped access; fleet visibility only with explicit member consent; B2B data aggregate-only with minimum-sample thresholds; drivers can export and delete their data. App Store background-location justification anchored on continuously visible user benefit (detention clock, on-time proof, IFTA).
- **Safety:** no interactive prompts while in motion; voice/audio pathways instead (F8 policy).

## 12. Data acquisition and cold-start strategy

- **POI seed (M1):** OpenStreetMap extract + FHWA/Jason's Law truck-parking datasets + state TPIMS real-time availability feeds where published + chain location lists → F2 ingestion with dedup. Goal: credible national map on day one of module activation.
- **Facility registry growth (M2):** every geofenced stop creates/validates facilities automatically; candidate facilities from check-ins confirmed by a second independent signal.
- **Dwell statistics (M2/M8):** generated as a byproduct of M3/M5 usage; publish only with sample-size transparency.
- **Parking supply (M6):** corridor-first playbook — pick 2–3 dense freight corridors, target repair yards/storage lots/CDL schools (the proven TPC supply profile), onboard with the zero-admin promise; do not spread nationally before corridor density proves conversion.
- **Fuel prices (M1/M7):** crowd-confirmed prices + merchant-network feeds; commercial price-feed licensing (e.g., OPIS) evaluated as a cost/benefit open question (Section 17).
- **Live statuses (M1):** TPIMS public feeds + geofence-proven crowd reports + passive dwell density; freshness always displayed.

## 13. Legal, regulatory and trust

- **Claims structure:** invoices issue **in the driver's name** with the platform acting as billing agent and automation layer — this is the primary posture. Escalated collection runs through a **licensed transportation collection partner** under a referral/revenue-share agreement. Direct collection-agency licensing (state-by-state for commercial debt) is explicitly *not* assumed; revisit only with counsel if partner economics demand it. FDCPA governs consumer debt and is largely inapplicable to these B2B claims, but state commercial-collection rules vary — legal review is an F13 activation precondition for M3/M4.
- **Facility scorecard (M2):** publish (a) aggregated factual measurements with disclosed methodology and sample sizes, and (b) clearly attributed user opinions under a moderation policy — the platform curates but does not author reviews. Defamation review of the methodology page is an activation precondition.
- **Not an ELD:** the platform never presents itself as, or substitutes for, an FMCSA-registered ELD; HOS inputs in M8 are driver-entered planning aids.
- **Payments:** Stripe/Stripe Connect structure avoids money-transmitter licensing; points are closed-loop, non-cashable, redeemable only against platform bookings.
- **Marketplace liability (M6):** terms allocate risk between driver and property owner; damage-coverage insurance (competitive parity with TPC's up-to-$25K) is an activation precondition decision, not a build blocker.
- **Privacy:** CCPA/state-law compliant data rights; the hard policy — driver-identifiable data is never sold and never provided to a driver's own counterparty; B2B products are aggregate-only with minimum-sample suppression.

## 14. Metrics framework

**North Star: Driver Dollars Delivered (DDD)** — dollars recovered for drivers (M3/M4/M9-flagged) + dollars saved (M7 fuel discounts) per month. Every module either grows DDD or grows the audience/data that grows DDD.

Supporting platform metrics: DAU/MAU ≥ 40%; W8 driver retention; % of stops with complete evidence capture; armed-stop coverage (share of active drivers' loads tracked); blended ARPU vs. the Section 9 model. Per-module KPIs are stated in each module spec and instrumented through F14 from each module's first commit.

## 15. Risks and mitigations

- **Recovery rate unknown (the load-bearing assumption).** If automated-stage recovery is materially below model, contingency economics thin out. → Instrument from claim #1; dunning cadence and escalation split are F13-tunable; partner escalation captures the tail; the evidence pack itself remains a retention feature even at low recovery.
- **Driver fear of broker blacklisting suppresses claims.** → Relationship-preserving default templates, notify-only mode, ghostwriter tone control (M11), and on-time-proof framing (M5) that makes the platform read as professionalism, not aggression.
- **Background location friction (OS policies, battery, permission grants).** → M5/M9 continuous-benefit narrative, adaptive sampling, graceful degraded mode (manual check-in/out preserves most claim value).
- **Parking supply cold start.** → Corridor-first density strategy; points economy routes demand-side engagement into supply-side liquidity; M6 is fully built regardless and activates per corridor.
- **Fuel network dependency on partners.** → Module built to completion; merchant/payment-partner acquisition is a parallel BD track gating activation only.
- **Crowdsourced data gaming.** → Geofence presence proof on all contributions, trust scoring, decay, anomaly detection (F10).
- **Scorecard legal exposure.** → Section 13 posture; counsel review as activation precondition; facility factual-correction channel (M2-FR7).
- **Scope weight for a solo-led build.** → This PRD's entire structure is the mitigation: one foundation, strict module boundaries, one module at a time to DoD, orchestrated agentic development against per-FR tests.

## 16. Explicitly out of scope

- Proprietary turn-by-turn navigation engine (deep-link handoff only).
- ELD hardware/software or FMCSA ELD registration.
- Load board (integrate/import loads; never build the marketplace).
- Factoring / instant claim advances (deliberate future option once recovery-rate data exists; ledger designed not to preclude it).
- Gate-control or any other hardware.
- Social feed/forum beyond facility-pinned Q&A; driver jobs/recruiting.
- Non-US markets at launch (architecture must not preclude them).

## 17. Open questions and assumptions

1. Automated-stage claim recovery rate (assumed 50% blended in Section 9) — measure from first live claims.
2. Collection partner selection and revenue-share terms (transportation-specialist agencies with contingency law-firm networks are the target profile).
3. Fuel payment-partner and merchant-network route (direct merchant deals vs. white-label network).
4. Commercial fuel-price feed licensing (OPIS et al.) vs. crowd+network-only pricing.
5. Marketplace damage-coverage insurance: carrier, cost, and coverage cap for M6 activation.
6. Final brand name and trademark clearance (LONGHAUL is internal only).
7. Points redemption rate and earn-table calibration (F13 config; tune with live data).
8. TPIMS feed coverage/format survey per state (engineering spike during F2 build).

---

## Appendix A — Competitive reference (summary)

| Player | What they own | Structural gap this PRD exploits |
|---|---|---|
| Trucker Path | Daily engagement, crowdsourced statuses, huge POI/community base | Monetizes the driver (subscriptions); weak routing rep; no transactions on parking; no recovery |
| Truck Parking Club | Parking transactions, supply network, owner tooling | No daily-open surface; single-purpose; can't do free-lot peer liquidity without cannibalizing itself |
| DMRG / Detention Source | Detention tracking concept validation | Notification-only or driver-pays subscription; no audience; no collection muscle; no data flywheel |
| Dock411 | Facility-info category definition | Weak execution/UX; no objective dwell measurement; no economic engine |
| Mudflap / fuel cards | Fuel discount economics | Single-purpose; no evidence/claims/parking context |
| Drivewyze / PrePass / CAT Scale / weather apps | Adjacent single-purpose utilities | Fragmentation itself — the consolidation opportunity |

## Appendix B — Glossary

**Accessorial** — charges beyond linehaul (detention, layover, TONU, lumper). **BOL** — bill of lading. **Detention** — compensable time held at a facility beyond free time (typically 2h) at $35–120/hr. **Dwell** — total time at a facility. **HOS** — FMCSA hours-of-service limits (11h driving / 14h on-duty windows). **IFTA** — interstate fuel tax agreement requiring per-state mileage. **Lumper** — third-party unloading labor the driver often pays and reclaims. **Rate con** — rate confirmation; the load's contract. **TONU** — Truck Ordered Not Used; cancellation compensation. **TPIMS** — state Truck Parking Information Management Systems publishing real-time availability. **POD** — proof of delivery.

---

*End of PRD v1.0 — build begins with the Common Ground.*
