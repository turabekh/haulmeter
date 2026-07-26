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
- 2026-07-20 · Tokens (§6/§8 Buttons) · New tokens `--on-accent` (white) + `--accent-fill` (= shield-600) for filled interactive-accent buttons, which §6/§8 did not specify. **Resolved (owner deferred to best judgment):** filled primary buttons fill with the shield-600 step and carry a white label, meeting contrast in both themes (dark white-on-#2C5FC4 → 5.93:1 AA; light white-on-#22509E → 7.75:1 AAA). shield-500 remains the accent for links/active/focus. · §16 contrast for primary actions outranks the exact shade; verified in `ui/test/contrast.test.js`. · approved
- 2026-07-20 · Tokens (§6.1/C-3) · Derived the **light theme** surface/text ramps (dark stays primary; §6.1 gave only qualitative "invert the ramps around the same accents, accents darken one step"). Locked light values — surfaces `--ink-0 #EDF1F5 / --ink-1 #F7F9FB / --ink-2 #FFFFFF`, hairline `--line-1 #CFD8E1`; text `--text-1 #10161C / --text-2 #47535F / --text-3 #5C6B77`; accents one step darker `--shield-500 #2C5FC4 / --shield-600 #22509E / --ledger-500 #2E8A4B / --marker-500 #A85D00 / --flare-500 #C5343A`. Only the 12 color tokens change; type/space/radius/motion/touch are theme-invariant. Toggled by system setting + manual override (`prefers-color-scheme` + `[data-theme]`). · Blue-cast near-white bg mirrors the dark "never pure #000" anchor (never pure #FFF); every ratio verified against §16 (text-1 ≥7:1 AAA, text-2 ≥4.5:1, text-3 ≥3:1, shield ≥3:1) in both themes by `ui/test/contrast.test.js` in CI. Owner-approved to derive. · approved
- 2026-07-22 · Brand (§23 / PRD §17.6) · **Product brand name = "Haulmeter"** (was placeholder "LONGHAUL"). Owner decision. Trucking-native ("haul") + the product's sole signature element ("meter" / The Meter). Rendered **mixed-case** as a wordmark (never ALL-CAPS, T-3). Single source of truth `ui/src/core/brand.js` (`BRAND`); user-facing surfaces (login wordmark, dev title) read it. Internal identifiers stay unchanged — Docker/DB/MinIO creds `longhaul`, `app_name "longhaul-api"`, and the F4 evidence hash namespace `longhaul-evidence:` (changing the salt would invalidate existing evidence chains). · Locked by a UI test asserting `.auth__brand` === "Haulmeter" with no "LONGHAUL". Trademark + domain clearance remain the owner's real-world step. · approved

- 2026-07-25 · Notifications (§13 / E-D1) · **New notification class `vendor_alert`** — the first OPT-IN class. Off until the driver turns it on (absence of a preference row reads as NOT opted in — silence is never consent), P1 tier, its own cap of **1 per driver per day** on top of the §13.1 budget, route/favorite-relevant facilities only, quiet hours respected, one-tap mute per vendor. The M13-FR6 anti-spam laws ARE the class definition. Classes are code-defined (like the tier table) so the laws are reviewable in one place; only the per-driver choice is data. Session A wires exactly one event: appearance-cancelled. · A promotions channel is precisely where a driver's background-permission goodwill gets spent; making the caps part of the class definition means no future event can quietly opt out of them. Enforced by `api/tests/foundation/f08_notifications/test_notification_class.py`. · approved
- 2026-07-25 · Map (§11.1/§11.2 / E-D2) · **Food badge + "Food" preset chip**, composed from existing tokens — no new visual class. The badge is the **first use of the §11.2 badge slot**: it rides the existing pin's puck (Lucide icon + `--marker-500`, `--r-pill`, `--s-1`) and leaves the 44 dp target unchanged. "Food" becomes a fifth chip in the §11.3 preset row, reusing `.chip`; the row already scrolled horizontally, so it costs nothing at 360 dp. NAV-1 is untouched — this is a filter row, not navigation. · §11.1 decided the badge-vs-pin question: additional signals render as badges on existing pins, never as more pins. Locked by `ui/test/vendor-ui.test.js`. · approved
- 2026-07-25 · Portals (§18 / E-D3) · **Vendor portal joins the portal family** as the fourth web-first surface (alongside Property-Owner, Fleet Workspace, Public Scorecard): desktop-first, comfortable tables, 1200 dp cap, same tokens, never importing driver-app screens. **Not built in Session A** — vendor management is API + the F14 console only until Session B. · The vendor sits at a desk to manage a schedule; nothing in §18 justifies desktop-first thinking in the driver app (LAW 0). · approved
- 2026-07-25 · Honesty (§11.7) · **A vendor's own claim is never rendered as a driver count.** Presence beliefs carry a `source`: `"crowd"` renders "3 drivers · 20m", `"vendor"` renders "vendor says here". The rule is enforced by the SHAPE of `presenceLabel` (it cannot emit a count for a vendor-sourced belief), not by reviewer discipline. The same split runs server-side: a vendor's self-report is an authoritative F10 submission attributed to the vendor, and it cannot credit the vendor's own show-up rate. Reliability displays as a raw pair ("shows up 19 of 20"), never a percentage — a fraction carries its own sample size, and "95%" over two appearances would overstate what we know. · Same discipline as the fuel-label pass: the platform states who said what and when, and never borrows the crowd's authority for a party with an interest. · approved
- 2026-07-25 · Tiers (§16 C-1) · **`documents_on_file` renders NEUTRAL, not positive.** Only `verified` earns `--ledger-500`; the middle rung of the vendor ladder uses `--text-2`. · "License on file" is a statement about paperwork, not an endorsement — colouring it as success would imply an inspection that never happened. · approved

- 2026-07-26 · Promotions (§21.3 / PRD §17 Q10) · **Promoted vendor content renders in a LABELLED SLOT, never blended into organic results.** Its own container, below the ranked rows, always carrying a "Promoted" label, composed from existing tokens (`--marker-500` on the label chip, existing `.chip`/caption type — no new visual class). §21.3 forbids ads and upsell cards; this is permitted because it is vendor-supplied text whose provenance a driver can see, it reads quieter than the organic content above it, it is never interstitial, and it can never buy position. · Q-3 is protected by SHAPE, not vigilance: the ranking function takes no promotion argument and promoted content arrives from a different function and a separate API endpoint, so the two cannot be concatenated by habit. Locked by `ui/test/vendor-ui.test.js` (no promotion text inside a `.vendor` row) and by the ranking grep-test that still passes unmodified. · approved
- 2026-07-26 · Reviews (§11.7) · **A rating average never renders without its reviewer count**, and no reviews renders as "No reviews yet" rather than 0.0. Distinct-REVIEWER counting: past the cadence window a driver's new verdict replaces their old one, so "12 drivers" always means twelve people. · Same discipline as the show-up pair and the fuel labels — a figure without its denominator invites overreading a handful of opinions, and a 0.0 average reads as "rated badly" when it means "nobody has said". · approved
- 2026-07-26 · Moderation (§E1.9 Q-8) · **Report severity is asymmetric by blast radius.** A reported REVIEW hides on the first report (low impact, trivially restored). A reported VENDOR LISTING stays visible until reports from N DISTINCT drivers accumulate (default 3, F13-tunable), because hiding a whole vendor takes away a livelihood and a single anonymous report would hand a competitor a kill switch. Repeat-offender suspension counts reports a moderator UPHELD, never reports received. The report affordance is a tertiary text button at the bottom of the sheet — available without being suggestive. · Owner-approved 2026-07-26 over the strict literal reading of Q-8. · approved
- 2026-07-26 · Portals (§18) · **Vendor portal shipped at `/vendor-portal`** as the fourth §18 surface (E-D3 realised). Desktop-first, 1200 dp cap, shares `ui/core` tokens, imports no driver-app screen. Two rules it may never soften: the show-up pair a vendor sees is the SAME string drivers see (no vanity variant, no percentage rounded in their favour), and a publishing suspension is stated plainly at the top rather than discovered when a publish fails. Promotion delivery reports what actually went out, since the `vendor_alert` caps suppress some sends. · A portal that flatters its user produces vendors who are surprised by their own reputation. · approved

- 2026-07-26 · Portals (§18 / E-D4) · **Admin console navigation: a persistent section rail**, seven sections as ROUTER CHILDREN at `/admin/*`. §18 was silent on portal navigation and §22.2 makes navigation structure a never-improvise category, hence this entry. Left rail ≥900 dp; below that a horizontal scrolling strip reusing the driver app's preset-chip shape rather than inventing a narrow-viewport pattern. Rail badges only where work is genuinely pending — a "0" on every item is decoration (§21.3). **NAV-1 (five tabs, no drawers) governs the DRIVER app; a portal rail is not a driver-app drawer**, so the two do not conflict. Children rather than internal tabs because a moderation queue must be bookmarkable and shareable, browser back must behave, and each section should fetch only its own data. · Composed from existing tokens; no new token was needed. · approved
- 2026-07-26 · Controls (§8 / E-D4) · **A state pill and an action button are different jobs and must not be one control.** The old flag row rendered a single button whose label was the action, so an operator read "Disable" and had to infer the flag was on. Colour now communicates STATE (On / Off / **Gates unmet** — three facts, not two), the button communicates only what pressing it does. Disabling a flag that gates a whole module requires a confirm step that NAMES what it gates; enabling requires none, because turning something on is recoverable by turning it off. · Applies to any future toggle in a portal, not only flags. Locked by `ui/test/admin-console.test.js`. · approved
- 2026-07-26 · Ops honesty (§11.7 extended to the operator) · **"Never ran", "switched off" and "failing" are three different facts and no surface may collapse them.** A naive health panel shows one blank cell for all three. A job that never ran reports null, not zero; a job whose flag is off is not a failing job; a failing job carries its error and its streak. Operator timestamps are ISO-trimmed and **never localized** — an operator correlating with container logs needs one stable string, not one per reader's browser. · The §11.7 discipline the driver app applies to crowd data applies equally to the operator: state what is known, and say plainly when nothing is. · approved
- 2026-07-26 · Registries (§22.2 heuristic "remove rather than add") · **A registered capability whose destination does not exist is LABELLED, never linked.** Thirteen modules register an admin view and none of their destinations are built; rendering them as links would create thirteen controls that 404. The registry's value is knowing what exists — a link to nothing is worse than an honest label, and the entry becomes a link automatically once its route resolves. · Same rule that removed the dead "suggest a cook" control from the driver app. · approved

- 2026-07-26 · Accounts (§18 / E-D6) · **Admin account management, and the four limits that define it.** An operator may create, edit, reset a credential and deactivate. They may **never read a password** (support that can read one can be social-engineered into surrendering it — only a TEMPORARY credential is ever issued, shown once, forcing replacement at next login), **never delete** (accounts reference money, claims and evidence; erasure would tear holes in records a third party may need to verify — hard delete is a retention workflow, PRD §17 Q16), and **never grant `platform_admin` without an explicit confirm** naming the consequence, which also gets its own audit action so it can be alerted on. Deactivation blocks login, kills live sessions, and preserves every row the account points at — a locked door, not an erasure. · Every limit is asserted by test rather than assumed; each is a place where a well-meaning future change would quietly make the product less trustworthy. · approved
- 2026-07-26 · Settability (§22 / decision 8) · **Some things are constitutionally not settable, and their absence is enforced, not merely observed.** No route may mutate F4 evidence or its hash chain, F7 ledger postings, F10 crowd submissions/beliefs, the detention clock's geofence events, or the audit log itself; no moderation verb accepts replacement text, because the author's words survive the verdict either way. Enforced by NEGATIVE tests against the live OpenAPI schema — "we didn't build an endpoint for that" is a weaker guarantee than "no endpoint for that can exist". The positive half is asserted too: anything classified admin-settable must actually be reachable, or the classification is a fiction. · An evidence record an admin could edit is worth nothing in a dispute; a belief an operator can set is an opinion wearing crowd data's clothes (§11.7). · approved
- 2026-07-26 · Gates (§22 / manual-settability) · **An activation gate can be WITHDRAWN as well as met.** A precondition that could only ever be ticked is a one-way ratchet; if a legal review lapses or an insurance policy expires the gate must be able to go back, and enabling then refuses until it is met again. · Withdrawal is audited like any other operator mutation. · approved

- 2026-07-26 · Impersonation (§18 / E-D5) · **Scoped "view as vendor", and why its safety is structural rather than procedural.** The session belongs to the ADMIN and merely NAMES the vendor, never the reverse — so every write attributes to the admin because of who owns the session, not because a caller remembered to pass an actor. An impersonation token is REFUSED by ordinary authentication, so it cannot reach a driver endpoint or the admin console however it is passed around; that is how "vendors only" is enforced rather than merely intended. Reads scope to the subject so the screen is byte-identical to the vendor's own — debugging "my screen looks wrong" is the entire point. Time-boxed at **30 minutes**, endable immediately, both ends audited. **No bypass:** the Q-4 publish floor applies to an admin publishing on a vendor's behalf exactly as it applies to the vendor. · A banner that names the vendor and states "anything you change is recorded as you, not them" is persistent and full-width, because an operator must not forget whose screen they are on. Driver impersonation is not approved and the domain refuses it at the source. · approved
- 2026-07-26 · Assisted edits (§18 / E-D5) · **The vendor is told when support edited their things.** "Edited by Haulmeter support" is derived from the audit log via `target_ref` rather than from flags on vendor/appearance/promotion — one source of truth, and the log is already the record of who did what. A vendor's OWN edits record nothing assisted: an audit entry for every ordinary edit would bury the ones that matter. · A support action a user cannot see is indistinguishable, to them, from a bug. · approved
- 2026-07-26 · Facilities (§18 / decision 7) · **An admin edit is another SOURCE, not an overwrite.** Console facility writes go through the same F2 pipeline every ingest uses, so what NTAD/OSM/TPIMS recorded keeps its provenance and the existing priority and union rules arbitrate. The alternative is quietly corrosive: an operator fixes a typo, a feed's claim is destroyed, the next ingest restores it, and nobody understands why the correction keeps reverting. The rule is stated in the UI where the operator is about to act, sources are shown per row, and there is no delete — merging is the answer to a duplicate, and the copy says so. · One honest exception, commented in place: the canonical NAME has no pipeline arbitration rule (it is set once at creation and never revisited), so a rename is applied directly — safe precisely because no ingest path renames an existing facility. · approved


- 2026-07-26 · Status semantics (§16 C-1 / §11 / E3.1) · **A weigh station's colours are INVERTED against every other status in the system, deliberately.** `closed` takes `--ledger-500` (the good-news token) and `open` takes `--marker-500` (attention). Everywhere else in the product, more-of-the-thing is worse; here the thing itself is the obstacle, and a closed scale is what a driver hopes for. Colour follows the MEANING to the driver, not the word: rendering "open" green because open is usually good would tell a tired driver the opposite of the truth at highway speed. **No new token is introduced** — the existing ledger/marker pair is reused. C-1 is unaffected and load-bearing here: the pill always carries its translated label, so a driver who cannot separate the two hues still reads "Closed", and an unreported scale says "no recent report" rather than rendering as though someone had said it was shut (§11.7). The report sheet's question, its two options and the F10 signal all come from one function (`statusReportFor`), so the vocabulary shown and the reading filed can never drift apart. Owner-approved 2026-07-26 ("approved, inverted colors and the flag"). · Locked by `ui/test/weigh-station-ui.test.js`. · approved
- 2026-07-26 · Map layers (§11.1 / E3.1) · **Scales ride the Drive preset only, behind their own flag `m01_weigh_stations`.** Drive is the preset for moving forward, which is exactly when a weigh station is a decision; Tonight and Work would only gain noise. The layer flag gates what a DRIVER sees and is separate from the ingest flag, so the data can be pulled and inspected before anyone is shown it — and while it is off the server returns an empty list rather than relying on the client to filter, so a driver never downloads a layer they have not been given. In corridor mode scales lead the stack (they are the only line with a deadline attached) and are read-only, like every other corridor line (§13.4 / Forbidden #11). · approved

- 2026-07-26 · Portals (§18 / §22.2 navigation) · **The vendor portal reuses the admin console's section rail (E-D4) rather than inventing a structure.** Six sections — Overview · My week · Menu & prices · Promotions · Verification · Reputation — as router CHILDREN under `/vendor-portal/*`, with the same ≥900 dp left rail / narrow horizontal strip. §22.2 makes navigation structure a never-improvise category; the resolution order's step 7 ("nearest analogous rule") points at a structure already approved for the same portal family, so this composes rather than invents. Children rather than internal tabs for the console's own reason: each section fetches only its own data — the single-page portal `Promise.all`'d four endpoints on mount and would have loaded six. **Two things live in the SHELL, not a section**: the impersonation banner and a publish suspension, because a cook must not have to be on the right page to learn either. Owner-approved 2026-07-26. · approved
- 2026-07-26 · Vendor signup (§18 / PRD §17) · **Self-serve registration is OPEN — no admin approval queue.** A cook signs up, lands on the UNVERIFIED rung, and their pin says so. The gate is the machinery that already exists: the Q-4 publish floor (which refuses with the exact missing fields), the verification ladder rendered honestly, and Q-8 moderation with its distinct-reporter threshold. An approval queue would add a second gate that says less than the tier label already says, and would make the operator a bottleneck on every cook. The portal gets its **own public door** at `/vendor-portal/join`: the driver login is mobile-first, asks for an authority number and lands on the trucking map, all three wrong for a vendor. The signup form asks for exactly what the floor will require, so "you cannot publish yet" is never discovered after the fact. Owner-approved 2026-07-26. · approved
- 2026-07-26 · Prices (§11.7 / PRD extension §E1.1) · **A vendor's standing MENU and a published OFFERING are different objects, and that separation is a truthfulness guarantee, not a schema convenience.** The menu is what a cook sells today; publishing SNAPSHOTS it into per-appearance offerings. Editing a price therefore changes what will be advertised next and never what a driver was shown last Tuesday — the reliability record and the reviews both refer to past windows, and a menu that rewrote history would make them unauditable. The portal states this in one sentence above the price table, because without it a cook assumes one of the two wrong things: that old listings silently update, or that they must re-publish to correct a price going forward. **Phase A is untouched**: `price_cents` is information, there is no order, basket, total or billing column, and `menu_item` was added to the Phase-A allowlist as a deliberate decision rather than slipping in. · approved

- 2026-07-26 · Filters (§11.3) · **The "More filters" sheet §11.3 has specified since v1.0 is now built, for the Food preset only.** Presets remain the interface; this is the ONE sheet, reached from a chip that appears only on Food, because the other presets have nothing to narrow yet. Composed entirely from the existing pill/chip shape and BottomSheet (NAV-3) — no new token, component pattern or navigation structure. Three narrowings, all of them facts the Q-4 publish floor **already forces a cook to provide**: a dish/name search, the languages they speak, and their halal answer. A filter **narrows and can never widen**: it is applied server-side to the output of the §E1.9 quality laws and the Q-3 ranking, so no combination of them can surface a lapsed appearance or reorder anything — the worst a filter can do is show a driver less. Search is bounded by the viewport exactly as the unfiltered query is, and the sheet says so, because an empty result must read as "none in this view" and not "none anywhere". **DRIVING:** the sheet never opens at speed (Forbidden #11 — no keyboard while moving); filters already set keep narrowing the corridor, which is precisely why they persist. · approved
- 2026-07-26 · Halal (§11.7 / §23 honesty) · **The platform still makes no halal claim — so the cook answers a CLOSED question as well as an open one.** `halal_disclosure` is free text and a filter over it would have meant the platform parsing a cook's sentence to decide who counts as halal, which is the platform claiming. Instead `halal_claim` has three rungs meaning exactly what they say: **not claimed · vendor says halal · halal certificate on file**. The driver-facing label always names **who is speaking** — the chip and the sheet read "Vendor says halal", never a bare "Halal" — and the free-text sentence is still shown verbatim beneath it. `certified` is **not self-awardable**: it requires an approved `halal_cert` document, and an unsupported claim is silently **downgraded to self_declared** rather than refused, because "vendor says halal" is still true and refusing would leave an honest cook unable to say anything. The portal offers only the rungs the server will honour, so the control never promises something taken back on save. The filter sheet states plainly that we do not check the claim ourselves. · Same discipline as the verification ladder: a rung a vendor could simply select would mean nothing to the driver reading it. · approved
- 2026-07-26 · Locales (§12.5) · **A language chip is labelled in its own language in every catalogue** — "ਪੰਜਾਬੀ", not "Punjabi" — because the person scanning for a cook who speaks their language is looking for their own script, whatever language the app happens to be in. These six keys are deliberately identical across all six catalogues; translating them would make the chip harder to find for exactly the person it exists for. · approved

- 2026-07-26 · Portals (§18 / §22.2 navigation) · **A seventh vendor-portal rail item, "My site", shown to SERVICE CENTRES only.** §22.2 makes navigation structure a never-improvise category, hence this entry; the item composes into the rail already approved for this portal family (E-D4) and invents nothing. It is type-conditional because a mobile cook has no site to claim, and a rail item that leads to "this is not for you" is decoration — the same reasoning that made the module registry label an unbuilt destination rather than link it. The ROUTE stays open regardless: a vendor who switches type in Profile, or arrives from a link, gets the section rather than a dead URL, and a food vendor who lands there is told plainly instead of being shown a search the server would refuse. **Known and deliberately not fixed here:** a service centre still sees "My week" and "Menu & prices", which are food-shaped. Making the whole rail type-aware is a larger change than this slice, and half-doing it would be worse than the honest gap. · approved
- 2026-07-26 · Claims (§11.7 / §12 copy) · **What the claim flow says at each of the four places it can disappoint someone.** (1) A **name mismatch** names the site we hold — "the name we have for this site is: …" — and never prints the similarity score, because "0.42" tells a business owner nothing about what to type next; the field is prefilled from the VENDOR's own business name and never from the facility, since prefilling from the facility would score 1.00 every time and make the check theatre. (2) A **rival claim is a dispute an operator settles**, disclosed on the search row BEFORE the form is filled rather than learned from the outcome, and worded so it never reads as a rejection — the domain deliberately refuses to let a second claimant silently lose, and the screen must not undo that. (3) **Curation ADDS**: services ingestion already knows render ticked and locked, each saying whose fact it is ("from our records" / "added by you"), because a claim edit cannot erase an ingested fact (E3.2) — the union is the screen, not a footnote. (4) **Proof is optional and the form says what that costs**: an operator with no document has only the name to go on, so a claim can take longer or be refused. Owner-approved 2026-07-26. · One thing the portal is never offered: **`scale`**. A weigh scale feeds the M1 weigh-station layer, and a service a claimant could simply tick would put an unverified scale in front of a driver deciding whether to pull in — the same discipline as the verification ladder and the halal rungs, where a rung a vendor could self-award would mean nothing to the driver reading it. Locked by `ui/test/vendor-site.test.js` and `api/tests/api/test_facility_claim_api.py`. · approved

---

*End of design.prd v1.0 — when in doubt: phone first, remove rather than add, and let the Meter be the only loud thing on the screen.*
