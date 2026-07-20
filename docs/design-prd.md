# DESIGN.PRD — Design Constitution for the Consolidated Trucker Platform

**Codename:** LONGHAUL · **Companion to:** trucker-platform-prd.md · **Status:** Authoritative v1.0 · **Date:** 20 July 2026

---

## 0. Authority — how Claude Code must use this document

This document is the **single source of truth for every design decision** in this codebase: visual, layout, interaction, copy, and component choices. It exists so that no design decision is ever improvised.

**Binding rules for Claude Code (and any agent or human touching UI):**

1. Before writing or changing ANY user-facing code (screens, components, styles, copy, notifications, PDFs, emails), consult this document. If it answers the question, follow it exactly — no reinterpretation, no "improvements."
2. If it does not answer the question, apply the Decision Protocol (Section 22). Never invent new colors, type sizes, spacings, component patterns, or copy conventions outside the token and rule system. Compose from what exists.
3. If composing from existing tokens/rules is genuinely impossible, STOP. Do not ship a guess. Write a proposal entry in the Decision Log (Section 23) describing the gap, the proposed rule, and the rationale — then ask, or proceed only with the smallest reversible choice clearly logged.
4. Precedence within this document: **LAW 0 (Section 1) → Forbidden List (21) → Tokens (6) → Component Rules (8) → Surface Specs (10–11) → everything else.** Higher always wins on conflict.
5. Every UI change must pass the Definition of Done checklist (Section 22.3) before it is considered complete. No exceptions, including "quick fixes."
6. This document may only be changed by an explicit human decision recorded in the Decision Log. Agents propose; the owner disposes.

---

## 1. LAW 0 — MOBILE FIRST. NON-NEGOTIABLE.

**THIS PRODUCT IS DESIGNED, BUILT, AND TESTED MOBILE FIRST. ALWAYS. NO EXCEPTIONS IN THE DRIVER APP.**

The user is a truck driver holding a mid-range Android phone in one gloved hand, in a bouncing cab, in glare or darkness. That person is the design target. Not a desktop browser. Not a simulator window stretched wide. Not the developer's monitor.

**Operational meaning — all of the following are mandatory:**

- **MF-1. Baseline canvas:** every screen is designed and implemented at **360 × 800 dp portrait** first (mid-range Android class; iPhone 375 dp verified second). A screen that is not complete, beautiful, and one-hand usable at 360 dp **does not exist yet**, regardless of how it looks wider.
- **MF-2. CSS direction:** styles are written for the 360 dp baseline with **`min-width` media queries only** to enhance upward. Any `max-width`-driven, desktop-first layout in the driver app is a defect and must be rejected/reverted on sight.
- **MF-3. Wider ≠ more:** tablet/landscape layouts (Section 7) may only **re-arrange and add breathing room**. They may never add features, actions, or information that the 360 dp layout lacks. If it matters, it fits on the phone; if it doesn't fit on the phone, it doesn't matter.
- **MF-4. One-hand rule:** every primary action on every screen sits in the thumb zone (Section 7.3) and meets touch-target tokens (Section 6.5). If a flow needs two hands, redesign the flow.
- **MF-5. Test order:** manual and automated UI verification runs at 360 dp **first**; wider viewports are verified only after 360 dp passes. Screenshots in reviews are 360 dp by default.
- **MF-6. Performance is part of mobile first:** budgets in Section 20 are measured on the baseline *device class*, not on a dev machine (Section 20.1).
- **MF-7. The only exception:** the three web-first surfaces — Property-Owner Portal, Fleet Workspace, Public Scorecard site — follow Section 18. Everything else in this document assumes the driver's phone. When in doubt, you are building for the phone.

Every checklist in this document repeats mobile-first checks deliberately. That is not redundancy; that is enforcement.

---

## 2. Design principles — ranked (use as tie-breakers, top wins)

1. **Glanceable over complete.** The right three things now beat all forty things always. Design for a 10-second look.
2. **Calm over engaging.** No noise, no nags, no gamified dopamine. The app is a professional instrument. Attention is borrowed from a person operating an 80,000 lb vehicle — spend it like it's dangerous, because it is.
3. **Numbers over prose.** "2h 14m · $87 accruing" beats a sentence. Every key fact has a numeric form.
4. **One primary action per screen.** At most one secondary. Everything else is reachable, not visible.
5. **State decides the screen.** The app reshapes itself to the driver's moment (Section 5); the driver never hunts for what the moment obviously requires.
6. **Trustworthy by appearance.** Restraint, precision, and consistency read as "this evidence will hold up." Every pixel supports the claim that this company gets drivers paid.
7. **Never blame, never beg.** Copy and design never scold the driver, never plead for engagement, never dark-pattern.

---

## 3. Context of use — design for exactly three sessions

Every screen must declare (in its spec/PR) which session type it serves:

- **S1 — Glance (driving, 5–15 s).** Phone mounted, sunlight or night, vibration. Needs: oversized figures, corridor-relevant info, voice for anything interactive. Zero typing. Zero reading paragraphs.
- **S2 — Dock task (stopped, 30 s–3 min).** Gloves possibly on, impatient, task-focused: confirm arrival, snap BOL, check clock, send notice, book spot. Needs: big targets, linear flows, camera-first capture, one decision per step.
- **S3 — Plan (evening/rest, 2–10 min).** Relaxed but tired. Review money, plan tomorrow, audit a settlement, browse facility intel. Needs: comfortable density, clear totals, no urgency theatrics.

Environment constants for all three: bright sun glare AND night dark (dark-first, Section 6.1), engine vibration (target sizes, Section 6.5), gloves (ditto), older-skewing eyes (type floor, Section 6.2), six languages (Section 12), connectivity unreliable (Section 15).

---

## 4. Information architecture & navigation

**The driver never sees "modules."** Twelve engineering modules collapse into five surfaces on a persistent bottom tab bar:

| Tab | Label (EN) | Serves | Backing modules |
|---|---|---|---|
| 1 | **Map** | Where am I going; what's around | M1, M2, M6, M7 (layers) |
| 2 | **Load** | Current work: stop, clock, evidence, protection | M3, M4, M5, F5 |
| 3 | **Money** | Owed, recovered, saved; claims pipeline | M3, M4, M9, M7 savings |
| 4 | **Docs** | Wallet, inspection mode, uploads | M5, F6, M9 exports |
| 5 | **More** | Profile, fleet, points, settings, help | M10, M12, F1 |

**Navigation laws:**

- **NAV-1.** Bottom tab bar, always visible on tab roots, icons **with labels** (never icon-only), 5 tabs exactly. No hamburger menu. No navigation drawer. Anywhere. Ever.
- **NAV-2. Two-tap depth:** every feature is reachable in ≤2 taps from its tab root. If a design needs depth 3, restructure it (usually into a bottom sheet).
- **NAV-3. Sheets over screens:** secondary tasks (detail views, filters, quick actions, confirmations with context) open as bottom sheets over the current screen. Full-screen pushes are reserved for linear flows (claim review, booking checkout, onboarding).
- **NAV-4.** Android hardware/gesture **back always works** and always does the obvious thing (close sheet → previous screen → tab root). iOS swipe-back equivalently. Back never loses entered data (drafts persist).
- **NAV-5. Cross-links are verbs, not menus:** contextual jumps ("Book this spot," "View facility," "Open claim") deep-link between tabs; discovery happens through use, not through browsing menus.
- **NAV-6.** The tab bar hides only in: active camera capture, full-screen map interaction (returns on any gesture end), and inspection mode.

---

## 5. App state machine — the screen follows the moment

The app derives a **driver state** from F3 motion/geofence signals and time. State changes what the Map and Load tabs foreground — it never blocks access to anything.

| State | Trigger (from F3/F5) | What changes |
|---|---|---|
| **IDLE** | default; stationary, no armed stop | Standard layouts (S3 density). Map tab = last preset. |
| **DRIVING** | sustained motion above walking speed | Glance mode ON app-wide: type scale bumps one step (Section 6.2), Map enters Corridor mode (11.4), all text inputs disabled in favor of voice (Section 14), notifications become audio-first (13), tap targets on primary cards grow to 64 dp. |
| **ON_SITE** | inside an armed stop's geofence | Load tab auto-foregrounds **The Meter** (Section 9) as home card; Map pins the facility card; capture actions (BOL photo, condition photos) are one tap from anywhere via a persistent action chip. |
| **RESTING** | stationary >20 min at a parking-type facility, evening window | Map tab defaults to "Tonight" preset (11.3); Money tab surfaces today's summary; notifications muted to P0 only (13.2). |

**State laws:** SM-1: state transitions animate calmly (Section 6.4) — never jarring, never modal. SM-2: the driver can always override the foregrounded card with one swipe; override persists until next state change. SM-3: every screen spec must define its DRIVING behavior explicitly (even if "unchanged"). SM-4: state logic lives in one place (foundation UI core), never re-implemented per screen.

---

## 6. Design tokens — the only source of visual truth

Tokens live in one file (`ui/tokens.scss`, mirrored to CSS custom properties). **No hardcoded visual values anywhere else — no raw hex, px sizes, durations, or shadows in components.** Quasar brand variables are mapped FROM these tokens (Section 19), never the reverse.

### 6.1 Color — dark-first, "instrument panel at night"

The aesthetic anchor is the subject's own world: asphalt, instrument-cluster glow, DOT-amber marker lights, retroreflective signage. Dark is the **primary theme** (night driving); light is derived, not the default. Deliberately avoided: pure-black + neon-accent clichés and consumer-app gradients.

**Surfaces (dark):**
- `--ink-0` #0E1319 — app background (asphalt, blue-cast near-black; never pure #000)
- `--ink-1` #151C24 — raised cards
- `--ink-2` #1C2530 — sheets, overlays
- `--line-1` #2A3644 — hairline borders (borders convey elevation; shadows do not — Section 6.3)

**Text (dark):**
- `--text-1` #EEF3F7 — primary (reflective white)
- `--text-2` #A3B0BC — secondary
- `--text-3` #66737F — muted/disabled

**Semantic accents (identical roles in both themes):**
- `--shield-500` #3D74E0 / pressed `--shield-600` #2C5FC4 — brand + the ONLY interactive color (buttons, links, active tab, focus)
- `--ledger-500` #3BA55D — positive: money recovered/saved, parking EMPTY, success (deliberately a calm banking green, never neon)
- `--marker-500` #F0A72E — caution: parking SOME, free time <30 min, expiring docs (DOT amber)
- `--flare-500` #E5484D — critical: parking FULL, detention accruing past threshold, overdue, destructive actions

**Color laws:** C-1: color never carries meaning alone — every status pairs with an icon or label (colorblind drivers are a core audience). C-2: accents are used at ≤10% of any screen's area; surfaces and text do the work. C-3: light theme derives by inverting the surface/text ramps around the same accents (accents darken one step for contrast); it exists for bright-sun preference and is toggled by system setting + manual override. C-4: no gradients, no glassmorphism, no decorative color. C-5: map night/day styles use these same tokens (Section 11.6).

### 6.2 Typography — the type IS the professionalism

- **UI face:** `IBM Plex Sans` — all interface text. Covers Latin (EN/ES/SO/UZ-Latin) and Cyrillic (RU) with a consistent technical character.
- **Figures face:** `IBM Plex Mono` — **numbers with meaning only**: timers, money, dwell figures, gallons, miles. Always with tabular behavior; this is the visual signature (Section 9). Never used for prose.
- **Punjabi:** `Noto Sans Gurmukhi` mapped as the family for `pa` locale; metrics-compatible line-height tokens verified.
- Loaded as self-hosted variable fonts; system-stack fallback defined; no other families, ever.

**Type scale (mobile baseline, dp / line-height):**
- `--type-meter` 44/48 Mono SemiBold — The Meter (timers/money heroes)
- `--type-display` 28/34 Sans SemiBold — screen titles, big states
- `--type-title` 20/26 Sans SemiBold — card titles
- `--type-body` 16/24 Sans Regular — default; **absolute floor for interactive text**
- `--type-label` 14/20 Sans Medium — buttons, tabs, field labels
- `--type-caption` 13/18 Sans Regular — timestamps, sample sizes, legal. **Nothing smaller exists.**

**Type laws:** T-1: DRIVING state bumps `body→18`, `title→22`, `meter→52` via a single scale variable — never per-screen overrides. T-2: money and time are ALWAYS Mono + tabular in fixed-width containers (zero layout shift while counting). T-3: no ALL-CAPS anywhere (Gurmukhi has no case; caps read as shouting) — emphasis via weight/size only. T-4: sentence case for every label, title, and button. T-5: user font-scaling honored to 200% — layouts must reflow, never clip (Section 16). T-6: truncation of money, time, or status is forbidden — scale down within token steps or wrap.

### 6.3 Space, shape, elevation

- **Grid:** 8 dp base. Spacing tokens: `--s-1` 4, `--s-2` 8, `--s-3` 12, `--s-4` 16, `--s-5` 24, `--s-6` 32, `--s-7` 48. Screen gutter: 16 dp (`--s-4`).
- **Radius:** `--r-card` 12, `--r-control` 10, `--r-sheet` 16 (top corners), `--r-pill` 999. Nothing else.
- **Elevation:** expressed by **surface step + hairline border** (`ink-0→1→2` + `line-1`). Drop shadows exist only on the floating action chip and map cards: one token `--shadow-float: 0 4px 16px rgba(0,0,0,0.35)`. Material multi-level shadows are forbidden.

### 6.4 Motion — calm, physical, skippable

- Durations: `--t-fast` 120 ms (state feedback), `--t-base` 200 ms (sheets, transitions), `--t-slow` 320 ms (state-machine reflows). Easing: standard `cubic-bezier(0.2, 0, 0, 1)`.
- Motion communicates state change only; zero decorative animation, zero looping ambient motion. The Meter's counting is the one living element per screen.
- `prefers-reduced-motion` honored globally: transitions become fades ≤120 ms; The Meter updates discretely (per second) instead of smoothly.

### 6.5 Touch & ergonomics — the glove spec

- Minimum target **48 × 48 dp**; primary buttons **56 dp** tall; DRIVING-state primary cards **64 dp**.
- ≥8 dp between adjacent targets; list rows ≥64 dp; bottom-sheet grab handle ≥32 dp tall hit area.
- Primary actions bottom-anchored within the thumb zone (Section 7.3). Destructive actions never sit adjacent to frequent actions.
- Gestures always have a visible-button equivalent (gloves defeat subtle gestures; swipes are enhancement, not requirement).

### 6.6 Iconography

- One set: **Lucide**, outline style, 2 dp stroke, at 20/24/28 dp only. No filled/duotone mixing, no emoji as UI, no custom one-off icons without a Decision Log entry.
- Icons always accompany status colors (C-1) and always pair with labels in navigation and buttons (icon-only allowed solely for universally learned actions: back, close, camera — each with accessible labels).

---

## 7. Layout system — mobile-first mechanics

### 7.1 Baseline & breakpoints
- **Baseline (design + build + test first): 360 × 800 dp portrait.** (MF-1.)
- `bp-wide` ≥600 dp — tablets & cab-mounted landscape: two-pane where it genuinely helps (Map | detail sheet docked right; Load | Meter docked). Re-arrangement only (MF-3).
- `bp-desktop` ≥1024 dp — **driver app: not designed for.** It must not break (fluid max-width 480 dp column, centered), but no desktop layouts are built. Desktop is Section 18's portals only.
- All media queries `min-width` (MF-2).

### 7.2 Screen anatomy (portrait baseline)
Top→bottom: status/context strip (state + connectivity, 32 dp) → screen title zone → content (scroll region) → bottom-anchored primary action (when present, 56 dp + 16 gutter) → tab bar (64 dp + safe-area). Content never hides under the tab bar; scroll regions get 16 dp end-padding above it.

### 7.3 Thumb zone
Bottom 60% of the viewport is the interaction zone. Primary/frequent actions live in the bottom third. The top strip is read-only context. Nothing interactive in the top 15% except back/close.

### 7.4 Density
S3 surfaces (Money, Docs, facility profiles) use comfortable density: max ~7 data rows per viewport. S1/S2 surfaces use card density: max 3 cards per viewport. Cramming is a defect, scrolling is not.

---

## 8. Component rules

Every component below is built once in `ui/core/` on tokens, then reused. New component ≠ new pattern: if a need doesn't match these, apply Section 22.

- **Buttons:** Primary (filled `shield`), Secondary (hairline outline), Tertiary (text). One Primary per screen (Principle 4). Loading state = inline spinner replacing label, width locked. Destructive = `flare` filled, requires its own confirm sheet.
- **Cards:** `ink-1`, `--r-card`, hairline border, 16 dp padding, title (`type-title`) + figure/status + one action max. Cards are glanceable units — no card ever scrolls internally.
- **Bottom sheets:** the workhorse (NAV-3). `ink-2`, top radius, grab handle, snap points 40%/90%, dim scrim 40%. Sheets stack max 1 deep.
- **Status pill:** label + icon + semantic color at 14 dp text; the ONLY colored-background chip in the system (parking status, claim state, doc expiry).
- **List rows:** 64 dp min, leading icon (24) + primary/secondary text + trailing figure (Mono) or chevron. Virtual scrolling mandatory >30 rows.
- **Forms:** one question per screen in critical flows (claims, booking checkout); inputs 56 dp; labels above fields (never placeholder-as-label); segmented controls/chips over dropdowns when ≤5 options; native pickers for date/time; numeric keypad for numeric fields; every error inline, specific, and next to its field (Section 12.4).
- **Empty/loading:** skeletons mirror the real layout (no spinners for content); empty states = one line of what this is + one action to start (Section 15.3).
- **Toasts/banners:** toast = confirmation only, 3 s, bottom, above tab bar, never interactive-critical. Persistent conditions (offline, sync pending, permission missing) = status strip banner, not toasts.
- **Camera capture:** full-screen, guided overlay frames per artifact type (BOL, seal, trailer corner), shutter 72 dp, review-retake-confirm in one screen. Capture works with zero connectivity, always (Section 15.1).

---

## 9. Signature element — **The Meter**

The product's one memorable visual: the counting figure that means *"your time is being measured, and it's worth money."* Executed identically everywhere it appears:

- Composition: `type-meter` IBM Plex Mono figure (time `H:MM:SS` or money `$0,000.00`) + 14 dp label above + status pill below. Counts live (smoothly; discretely under reduced motion). Fixed-width digits — the layout never breathes.
- Color logic: free-time countdown `text-1` → last 30 min `marker` → accruing money `ledger` → disputed/overdue `flare`.
- Appears in: the ON_SITE home card, Money tab totals, detention push notification (big-text style), the PDF evidence-pack header strip, and the DRIVING voice summary ("meter check") — same numbers, same order, same wording, every surface.
- The Meter is the ONLY animated, ONLY mono-set, hero element. Nothing else on a screen competes with it. Boldness is spent here and nowhere else.

---

## 10. Surface specs (the five tabs)

Each spec: purpose · anatomy at 360 dp · primary action · session type · DRIVING behavior. Anything not stated inherits Sections 4–8.

### 10.1 Map (root)
- Purpose: what's around and ahead; the daily-open surface.
- Anatomy: full-bleed map → preset chips row (top, scrollable: Drive / Tonight / Work / Fuel) → floating "report status" chip (bottom-right, above tab bar) → facility card as bottom sheet on pin tap.
- Primary action: contextual — the facility sheet's single CTA (Book / Navigate / Arm stop).
- Sessions: S1 + S3. DRIVING: Corridor mode (11.4) replaces free-pan.

### 10.2 Load
- Purpose: the current stop and its money/evidence state.
- Anatomy: The Meter card (state-dependent) → stop context row (facility name, appointment, counterparty) → evidence checklist card (BOL ✓, photos 2/4, notice sent ✓) → next-stop preview.
- Primary action: state-dependent single CTA (Arm stop → Snap BOL → Send notice → Generate claim).
- Sessions: S2. DRIVING: collapses to Meter-only glance card + voice hint. Empty state (no active load): "Add a load" (rate-con photo import) as the one action.

### 10.3 Money
- Purpose: everything owed, recovered, saved — the driver's P&L with the platform.
- Anatomy: month summary (Meter treatment: recovered + saved totals) → receivables list (status pills: invoiced / disputed / escalated / paid, aging in Mono) → savings row (fuel) → export row.
- Primary action: per-receivable "Next action" (nudge / escalate / mark paid).
- Sessions: S3. DRIVING: read-only; actions deferred with "tonight" queue.

### 10.4 Docs
- Purpose: wallet + capture inbox.
- Anatomy: Inspection mode button (top, 56 dp, works offline in ≤2 taps from cold start) → expiring-soon strip (marker pills) → document grid by type → capture FAB-chip.
- Primary action: Inspection mode. Sessions: S2. DRIVING: inspection mode reachable but confirms vehicle stopped.

### 10.5 More
- Purpose: identity, fleet, points, settings, help. Deliberately boring; a plain 64 dp row list. No cards, no promos, no badges. Sessions: S3.

## 11. Map design spec

- **11.1 Layer law:** max **2 data layers** active simultaneously; additional signals render as badges on existing pins, never as more pins.
- **11.2 Pin taxonomy:** shape = facility type (circle: truck stop/rest; square: bookable property; diamond: shipper/receiver; small square: scale/weigh). Fill = semantic status color. Badge slots: price (fuel), $ (bookable), clock (dwell risk). Pins have 44 dp hit areas regardless of visual size.
- **11.3 Presets over filters:** Drive (parking status + fuel ahead), Tonight (parking only, availability-sorted), Work (armed stop + its facility intel), Fuel (net prices). One "More filters" sheet exists; presets are the interface. Preset choice persists per state (RESTING→Tonight).
- **11.4 Corridor mode (DRIVING):** map locks to heading-up follow; a vertical "next 3 exits/facilities" card stack (64 dp cards, Mono figures: miles, price, status) replaces free exploration; all taps deferred-safe (queue "save for stop" instead of opening flows).
- **11.5 Clustering:** server-side; cluster chip shows count + dominant status color; declutter rule: labels appear only ≥ zoom threshold; overlapping labels never allowed.
- **11.6 Map styles:** custom day + night styles from Section 6.1 tokens; night style is the default pairing with dark theme; roads/labels desaturated so semantic pins are the only saturated elements.
- **11.7 Freshness honesty:** every crowd-fed status shows relative age subtly ("40m · 3 drivers") in `text-3`; stale (>4 h) statuses hollow their fill. Never fake confidence.

## 12. Content & microcopy — copy is design material

- **12.1 Voice:** calm professional peer. Plain verbs, sentence case, no exclamation marks, no hype, no apology theater. The app states facts and next steps.
- **12.2 Numbers first:** lead with the figure, follow with the noun ("$87 accruing · 1h 12m past free time"). Buttons say exactly what happens ("Send notice", "Book spot — $24"), and the same verb persists through the flow and its confirmation ("Notice sent").
- **12.3 Terminology:** trucking jargon stays in English in every locale (detention, lumper, rate con, BOL, TONU) — defined once in contextual help, never translated. Counterparty-facing text is always English (F15).
- **12.4 Errors & empties:** every error = what happened + what to do, specific, unblaming ("No signal — saved on your phone. Syncs automatically."). Empty states invite the first action; they never scold or emote.
- **12.5 Multilingual writing laws:** design copy in EN, but layout at +40% length (pseudo-locale `xx-XL` in CI); no text in images; no concatenated sentence fragments (full ICU messages with placeholders); no idioms/wordplay; dates localized, units NEVER (miles/gallons/ft-in everywhere, Section F15); the six locales ship together — a string without all six translations fails CI.
- **12.6 Notifications copy:** ≤2 lines: figure-first fact + single action ("Detention started · $75/h — Notice ready to send"). Never cute, never urgent-scammy.

## 13. Notifications & interruption budget

- **13.1 Budget:** max **2 unprompted notifications per driver per day** (rolling), excluding P0. Exceeding the budget is a defect: background-permission survival is a platform-critical asset.
- **13.2 Tiers:** **P0** money/safety-critical, time-sensitive (detention started; booking failed; claim paid) — allowed always, audio-first while DRIVING. **P1** useful today (free time 30-min warning; doc expires this week) — respects quiet hours + budget. **P2** everything else — digest only, in-app, never pushed.
- **13.3 Quiet hours:** default 22:00–06:00 local (driver-adjustable); RESTING state mutes to P0.
- **13.4 In-motion policy:** while DRIVING, notifications render as one-line audio summaries (Section 14) + silent tray entries; no interactive prompts, no full-screen intents except active-navigation-critical (none exist today).
- **13.5** Every notification deep-links to the exact screen and state it describes. No landing on tab roots.

## 14. Voice UX rules (M11 surface behavior)

- **14.1** Voice is the DRIVING-state input; every S1-relevant intent (meter check, parking ahead, fuel ahead, arm stop, send notice confirm) must be completable by voice alone.
- **14.2** Invocation: persistent mic button in the status strip (48 dp) + headset controls. No hotword.
- **14.3** Audio responses ≤2 sentences, figure-first, same wording as the visual Meter/cards (one vocabulary everywhere). Confirmations that move money or send documents require explicit verbal confirm + are queued to a visual review card at next stop.
- **14.4** While stopped, voice results always land in the visible UI (the sheet opens); voice never becomes an invisible parallel app.
- **14.5** Locale follows the user's language including mixed English trucking terms; unrecognized → one graceful re-ask, then visual fallback queued. Never pretend to understand.

---

## 15. System states — offline, loading, empty, error

- **15.1 Offline is a mode, not an error.** Every capture path (photos, geofence acks, status reports, claim actions) works fully offline and queues (F12). UI: persistent thin status-strip banner "Offline — everything saves to your phone" in `text-2` (calm, not red); queued items show a subtle pending glyph; sync completion is silent (no toast parade).
- **15.2 Loading:** skeletons mirror final layout; content appears progressively; The Meter never skeletons (it renders from local state instantly). No full-screen spinners, ever.
- **15.3 Empty:** one sentence of purpose + one starting action. Empty Money: "Recovered and saved money shows up here. Add your first load to start the meter."
- **15.4 Errors:** inline, specific, actionable (12.4). Retries are automatic where safe; the user is asked to act only when only they can. Failed money-moving actions are always explicit and persistent until resolved.
- **15.5 Degraded location:** if background permission is lost, the app shows a single persistent Load-tab card explaining exactly what stops working (the meter arms manually) with a one-tap fix — never nags beyond that card.

## 16. Accessibility spec — the road IS the accessibility case

- Contrast: critical data (Meter, statuses, primary actions) ≥7:1 (AAA); all other text ≥4.5:1; verified in BOTH themes in CI.
- OS font scaling honored to 200%: layouts reflow, rows grow, nothing clips or truncates (T-5/T-6).
- Color never sole signal (C-1); status = color + icon + label. Test all screens through a deuteranopia filter before done.
- All interactive elements labeled for screen readers; The Meter announces as a live region at sane intervals (once/min while accruing).
- Reduced motion honored (6.4). Focus states visible (2 dp `shield` ring) — keyboard/switch access works even though touch-first.
- Glare test: every screen reviewed at max brightness against the light theme and min brightness dark theme.

## 17. Outbound artifacts — the PDF is a screen

Evidence packs, invoices, and counterparty emails are the highest-stakes "UI" in the product: they are what gets the driver paid.

- Same tokens: Plex Sans text, Plex Mono figures, `shield` single accent on white; generous margins; zero decoration.
- Evidence pack anatomy: header strip with The Meter figure (total detention · total $) → parties & load refs → event timeline (Mono timestamps, hairline rules) → map trace snapshot → artifact thumbnails → hash-verification block (monospace, quiet). Reads in 30 seconds by a broker's accounts payable clerk; that clerk is the persona.
- Invoices: standard AP-friendly layout (bill-to, terms, line items, remit info) — deliberately conventional; novelty here costs money.
- Emails: plain, short, professional; one link; no marketing footer, no images. Always English (F15).

## 18. The web-portal exception (the ONLY non-mobile-first surfaces)

Property-Owner Portal, Fleet Workspace, Public Scorecard: desktop-web-first (their users sit at desks), responsive down to tablet/phone, same tokens/type/copy voice on light theme default. Density: comfortable tables, 1200 dp max content width. They share `ui/core` tokens and components where sensible but never import driver-app screens. **Nothing in Section 18 ever justifies desktop-first thinking in the driver app (LAW 0).**

## 19. Quasar implementation rules — component engine, not design language

- **Q-1 Token supremacy:** Quasar SCSS brand variables are assigned FROM `tokens.scss`. No Quasar default color, shadow, or size reaches the screen.
- **Q-2 Material OFF:** ripple disabled globally; Material shadows replaced by Section 6.3 elevation; default Quasar toolbar/FAB/chip looks are not used.
- **Q-3 Use Quasar for behavior:** QLayout/QPage scaffolding, QForm/QInput internals, QVirtualScroll, QDialog (rare), pull-to-refresh, i18n plumbing — restyled entirely by tokens.
- **Q-4 Custom-build the signature surfaces:** tab bar, cards, sheets, status pills, The Meter, map overlays, corridor cards, camera overlays. These live in `ui/core/` and contain zero Quasar visual defaults.
- **Q-5** No inline styles; no per-component hex/px; no `!important` wars — token classes and CSS vars only. Icons via Lucide, not Material icon font.
- **Q-6** All breakpoint logic uses the Section 7.1 tokens; Quasar's `$breakpoint-*` mapped to them; `min-width` only in the driver app (MF-2).

## 20. Performance budgets (measured, not vibes)

- **20.1 Baseline device class:** a ≤$180 mid-range Android (A-series/Moto G class), throttled 4G. All budgets measured there. Dev-machine performance proves nothing (MF-6).
- Cold start → interactive Map: ≤4 s; warm ≤2 s. Tab switch ≤300 ms. Map pan/zoom ≥45 fps sustained with full pin load (target 60).
- The Meter and Load tab render from local state in ≤500 ms with zero network.
- JS bundle (initial, driver app) ≤350 KB gz; images: no decorative imagery — photos only where they ARE the content (facility, docs), lazy + sized.
- Battery: default tracking ≤5%/day (F3); UI never blocks on sync.
- CI enforces budgets on the baseline profile; a red budget blocks merge like a red test.

## 21. Forbidden list — never, regardless of who asks

1. Desktop-first CSS or layouts in the driver app (LAW 0 / MF-2).
2. Hamburger menus, nav drawers, >5 tabs, icon-only navigation.
3. Ads, promos, upsell cards, engagement streak-nags, confetti (points UI stays dignified — M10).
4. New colors, fonts, sizes, shadows, or radii outside tokens.
5. ALL-CAPS text; truncated money/time; non-tabular figures.
6. Blocking modals for non-destructive actions; toast-critical information; spinner-only loading.
7. Text baked into images; concatenated translation fragments; shipping any string without all six locales.
8. Dark-pattern anything: guilt copy, hidden fees at checkout (M6 shows one final price), pre-checked options, fake urgency.
9. Notification-budget violations; marketing pushes to drivers.
10. Decorative animation, parallax, gradients, glassmorphism, emoji-as-UI.
11. Interactive prompts while DRIVING; keyboard input while DRIVING.
12. Material-default look leaking through (ripple, elevation shadows, default chips) — reads "generic app," kills Requirement 3 (professional).

## 22. Decision protocol — what Claude Code does when this document is silent

**22.1 Resolution order:** (1) LAW 0 → (2) Forbidden List → (3) Tokens → (4) Component Rules → (5) Surface/Map specs → (6) Ranked Principles (Section 2, top wins) → (7) nearest analogous rule in this doc.

**22.2 If still unresolved, apply the four heuristics in order:** remove rather than add · sheet rather than screen · number rather than sentence · one action rather than two. Then log the choice (Section 23) as a PROPOSED convention. If the choice would create a new token, component pattern, navigation structure, or notification class — STOP and ask; those four categories are never improvised.

**22.3 Definition of Done — every UI change, no exceptions:**
- [ ] Complete and excellent at **360 × 800 dp** BEFORE any wider viewport touched (LAW 0)
- [ ] `min-width` queries only; primary action in thumb zone; targets ≥48 dp
- [ ] Dark theme first, light verified; contrast passes (16)
- [ ] DRIVING-state behavior explicitly defined for the screen (SM-3)
- [ ] Offline behavior defined; capture paths work with zero network
- [ ] All six locales present; renders under `xx-XL` +40% pseudo-locale without clipping
- [ ] Figures in Mono/tabular, fixed-width; no truncated money/time
- [ ] Zero hardcoded visual values; tokens only; no new colors/sizes
- [ ] Font-scaling 200% reflow verified; status = color + icon + label
- [ ] Android back behavior verified; deep-link target correct
- [ ] Performance budgets green on baseline profile (20)
- [ ] Nothing from the Forbidden List (21)

## 23. Decision Log (append-only)

Format: `DATE · AREA · DECISION · RATIONALE · STATUS(proposed/approved)`

- 2026-07-20 · Foundation · Adopted this document v1.0 as the binding design constitution; The Meter designated the sole signature element; IBM Plex Sans/Mono + Noto Sans Gurmukhi locked as the only type families; five-tab IA locked. · Baseline decisions of record. · approved
- 2026-07-20 · Tokens (§6.1/C-3) · Derived the **light theme** surface/text ramps (dark stays primary; §6.1 gave only qualitative "invert the ramps around the same accents, accents darken one step"). Locked light values — surfaces `--ink-0 #EDF1F5 / --ink-1 #F7F9FB / --ink-2 #FFFFFF`, hairline `--line-1 #CFD8E1`; text `--text-1 #10161C / --text-2 #47535F / --text-3 #5C6B77`; accents one step darker `--shield-500 #2C5FC4 / --shield-600 #22509E / --ledger-500 #2E8A4B / --marker-500 #A85D00 / --flare-500 #C5343A`. Only the 12 color tokens change; type/space/radius/motion/touch are theme-invariant. Toggled by system setting + manual override (`prefers-color-scheme` + `[data-theme]`). · Blue-cast near-white bg mirrors the dark "never pure #000" anchor (never pure #FFF); every ratio verified against §16 (text-1 ≥7:1 AAA, text-2 ≥4.5:1, text-3 ≥3:1, shield ≥3:1) in both themes by `ui/test/contrast.test.js` in CI. Owner-approved to derive. · approved

---

*End of design.prd v1.0 — when in doubt: phone first, remove rather than add, and let the Meter be the only loud thing on the screen.*
