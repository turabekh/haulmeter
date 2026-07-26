# HANDOFF-085 — the driver surface (M5 session 4 of 5)

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** there is now a button for the server work sessions 1–2 built, the evidence
checklist tells the truth, and two claims the constitution made about itself are true for the first time.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0048_m05_on_time_consent** (none added) |
| Tests | **pytest 923 · vitest 345 · layout 144/144 · ruff clean · import-linter 30/30** |
| §23 decision log | 42 entries (see §6 — two are owed) |
| Handoffs | 000 → 085 |
| Git | **31 commits local on `main`, no remote configured** |

## 2. What was built

**A prompt is attributed, never asserted.** `Photo  seals` reads to a clerk as *this photograph shows
the seals* — the platform asserting image content in its own voice. If the driver shot a mud flap at
step two, the document states something false and we said it. It now reads **`prompted: seals`**. Same
discipline as "Vendor says halal" never being a bare "Halal", `documents_on_file` rendering neutral, and
a vendor's presence claim never appearing as a driver count.

**The checklist stopped lying twice.** §10.2 specifies "photos **2/4**" and the code rendered
`photos · 2` — a bare count cannot tell a driver whether they are finished, and FR5 exists to make a gap
visible while they are still standing where it can be closed. The **BOL row asserted a ✓
unconditionally**; it now answers honestly, which for most stops today means *not yet*. F6 gained the
by-subject query its `subject_kind`/`subject_ref` columns always implied.

**Export and share reached the driver.** Export regenerates from the chain (the driver's own copy,
always current); share pins what is sent and hands over **one link** per §17. The copy says which is
which rather than offering two buttons that look alike. A queued share follows §15.1 exactly — stated
once, quietly, **silent on completion**. Neither renders while DRIVING: the record stays readable at
speed, nothing there acts (SM-3, Forbidden #11).

**§6.2's Gurmukhi sentence is true in all three parts** — see §3.

## 3. What the browser caught that no test could

**§6.2 claimed "metrics-compatible line-height tokens verified" for Punjabi.** All three parts of that
sentence were false: the font was never vendored, `--font-gurmukhi` was applied to **nothing**, and no
verification was ever performed. `pa` rendered in IBM Plex Sans, **which has no Gurmukhi coverage at
all** — one of six launch locales fell through to whatever the device happened to have.

The fix is ordinary. **The verification is the part that could not have existed before this program:**
"metrics-compatible" is a *layout* claim, and Gurmukhi carries matras above *and* below the baseline, so
a line height tuned for Latin is exactly what clips silently. `pa` now runs the full matrix beside `en`
and `xx-XL`, with a new assertion for **text clipped by its own line box**. 144 checks green — so the
tokens really are metrics-compatible, and we know it rather than assert it.

The harness built last session is what made a constitutional claim checkable within a day of it being
questioned. That is the return on it.

## 4. Inspection mode — the measured number

```
INSPECTION MODE: 2 taps from cold start, offline · 3 credentials shown
```

Counted in a real browser, cold start, **every request outside the app aborted** — the dead zone a scale
house actually is. The wallet renders from F12 read-side cache, which is the whole point: an inspector
is not waiting for a dead zone to end. `ui/layout/inspection.spec.js`.

## 5. M5 FR status — end to end vs server only

| FR | Server | Driver app |
|---|---|---|
| **FR1** on-time proof | ✅ complete, tested | ⚠️ fires and files; **judged window + verdict still not visible** |
| **FR2** condition protocol | ✅ capture + export + share | ✅ **complete end to end** |
| **FR3** wallet | ✅ reads · ❌ **dispatcher unbuilt** | ✅ §10.4 anatomy, 2 taps measured; **capture chip still dead** |
| **FR4** incident | ✅ complete, tested | ⚠️ shares via the evidence surface; **no incident-specific entry point** |
| **FR5** summary | ✅ complete | ✅ **complete end to end** (denominator + honest BOL) |

**FR2 and FR5 are now complete end to end.** FR1, FR3 and FR4 are not, and this table says so until they
are.

## 6. Exact next task — Session 5

1. **FR1's judged window and verdict, visible.** On-time is computed against an appointment parsed from
   a rate con; a mis-recorded window silently costs a protection the driver believes they have.
2. **The dead Docs capture chip.** `<button class="capture">` has no `@click`. §23's registry precedent
   applies — *a capability whose destination does not exist is labelled, never linked* — so it either
   gets a destination or it goes.
3. **FR4's own entry point.** Incidents share through the evidence surface; there is no incident-first
   route to a pack.
4. **The F6 expiry dispatcher** (FR3's other half) — unbuilt, not unwired. Five doc types × 30/14/3 is
   fifteen events against §13.1's ceiling of two per day; reuse HANDOFF-081's shape, ordered by
   proximity to expiry.
5. **FR5's EXIT carve-out** — an irrecoverable gap at a state transition is a deadline, not a nag. P1 on
   geofence EXIT, precedent in M2-FR4.
6. **Share-link lifetime.** 90 days may be shorter than a dispute; M3's dunning alone runs 21 days
   before escalation. Tie it to the receivable's state, or make it extendable.
7. **Two §23 entries owed** and deliberately not written yet, because both should be logged when the
   behaviour they describe is final: the prompt-attribution rule (shipped this session, wording
   `prompted: …`) and the Gurmukhi correction (shipped, and it supersedes the "still false" note in
   entry 41). Writing them now while FR1 and FR4 are mid-flight would date them wrong.
8. **M5 DoD close-out** — the full §22.3 sweep and a handoff that states which FRs are complete.

## 7. Blockers and open questions

- **No git remote — thirteen sessions.** Thirty-one commits local on `main`.
- **The harness runtime is growing**: 144 checks, ~3.4 min, because the matrix is surfaces × themes ×
  locales × assertions. Still its own target so `make test` stays at ~8s, but a fifth locale or a sixth
  assertion should be a deliberate decision, not a reflex.
- **The harness covers six top-level surfaces with a planted session.** The evidence surface, condition
  capture and facility profile are not in it — worth adding as session 5 touches them.
- Carried, untouched: the F2 geohash-boundary duplicate miss and `merge_facilities` staleness.

## 8. Commits this session

```
(this commit) docs: HANDOFF-085 — the driver surface
9f4e2d3 Inspection mode: 2 taps, measured rather than asserted
41c691e §6.2's Gurmukhi sentence is now true in all three of its parts
d3feefa There is now a button, and the checklist tells the truth
```

## 9. Key files touched

```
F4      domain/render.py (_detail attributes the prompt)
F6      domain/service.py (documents_for_subject) · public.py
M5      domain/service.py (has_bol; summary carries it) · public.py
API     api/load.py (photos_required, bol_captured on the meter)
UI      surfaces/LoadSurface.vue (denominator, honest BOL, Mono count)
        surfaces/EvidenceSurface.vue (export + share + §15.1 queue + DRIVING guard)
        core/api.js (exportProtectionPack, shareProtectionPack)
        core/tokens.scss (Noto Sans Gurmukhi @font-face + :lang(pa))
        public/fonts/NotoSansGurmukhi.ttf + OFL
        i18n/*.json (9 keys ×6)
HARNESS layout/layout.spec.js (pa in the matrix; clipping assertion)
        layout/inspection.spec.js (NEW — the measured number)
TESTS   f04/test_render.py (+1 attribution)
DOCS    HANDOFF-085.md · HANDOFF.md
```

## 10. Ports / env / flags

**No port, env, migration, flag or config changes.** One new vendored font (Noto Sans Gurmukhi,
OFL 1.1). `make ci` runs lint → test → ui-layout.
