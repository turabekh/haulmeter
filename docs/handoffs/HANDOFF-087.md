# HANDOFF-087 — closing the driver surface (M5 session 6 of 7)

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** FR1 and FR4 are now complete end to end, a stated colour law that had **no control
at all** is enforced, and share links stopped being able to expire in the middle of a dispute.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0048_m05_on_time_consent** (none added) |
| Tests | **pytest 927 · vitest 345 · layout 136/136 · ruff clean · import-linter 30/30** |
| §23 decision log | **45 entries** |
| Handoffs | 000 → 087 |
| Git | **37 commits local on `main`, still no remote** |

## 2. Which premises in this prompt were wrong

The prompt asked for this list and warned its own copy was frozen at HANDOFF-081. Two findings were
**worse** than stated, three reconciled cleanly:

| # | Premise | Finding |
|---|---|---|
| 4.1 | Theme does not persist | **Worse.** It also had **no control**: nothing anywhere called `useTheme`/`setMode`, so §6.1 C-3's "manual override" was unreachable by any means. Light could only ever come from the OS preference |
| 4.2 | No appointment-correction path | **Confirmed.** F5 owns `Stop.appointment_*`; M5 building an editor would cross a boundary. Logged as F5 debt, not built |
| 4.3 | Incident pack unreachable | **Confirmed, and the mechanism is exact:** the incident id arrived in the `filed` event and **nothing kept it**, so the pack became unopenable the moment the 3.5-second toast faded |
| 4.4 | 9 × 3 × 5 = 136 (product is 135) | **Reconciled: 135 layout checks + 1 inspection measurement**, two spec files in one `testDir`. Not a miscount — the extra is session 4's ≤2-tap measurement |
| 4.5 | Claim duration | **Established from code and PRD.** `DUNNING_DAYS = [3, 10, 21]`, and day 21 is only the *escalation offer*; M3-FR7 then hands the claim to a collection partner whose fees PRD §8.3 prices at "25–30% … higher for **aged/complex** accounts" — the business model assumes escalated claims run long |

## 3. What was built

**The §22.3 two-classes entry (§23 #45).** Checks computable from **tokens** — contrast, six-locale key
parity, tokens-only, the pseudo-locale generator — were genuinely performed from the start. Checks
needing a **rendered surface in a particular state** — 360 dp completeness, thumb zone, ≥48 dp, 200%
reflow, `xx-XL` clipping, and "light theme verified" — could not fail before the harness existed,
because jsdom has no layout engine. Three defects that looked unrelated had one root cause.

**Theme (D).** A row in More — chips, matching the locale list beside it (§8: chips when ≤5 options) —
plus persistence and a boot-time apply so a chosen theme never flashes the other one first. C-3 holds,
and "light theme verified" is checkable for the first time because the app can now be *put into* the
state the check describes.

**FR1 (A).** The appointment window renders **before arrival**, in Mono, with its provenance: *"Read
from your rate con"* versus *"You entered this"*. A parsed value and a typed one carry different
confidence and only the driver knows which is right. **No edit control** — F5 owns the field. Verdict
still shows after arrival.

**FR4 (B).** `IncidentSheet` now emits the incident id, `LoadSurface` keeps it, and a *"View what you
filed"* control routes to the existing evidence surface with the kind in the query. No new navigation
structure (§22.2).

**Share lifetime (C).** Default **90 → 365 days**, F13-tunable, plus driver-initiated `extend`.
Extension is the driver's act deliberately: F4 is foundation and cannot ask M3 whether a claim is live,
and a seam built for a caller that does not exist yet is precisely the bug class the harness's fifth
assertion now watches for.

## 4. What a failing test caught that the design did not

**`extend(days=180)` moved the expiry closer.** With the default raised to a year, the first draft set
`expires_at = now + days` unconditionally, so asking to extend by 180 days *shortened* a link that had
365. A function called `extend` that can cut a link short is a trap for its next caller. It now takes
the later of the two dates, and a test named for the behaviour holds it there.

That is the same class as this session's other findings — a near side built, a far side assumed — and it
was caught by writing the assertion before trusting the code.

## 5. M5 FR status — server vs end to end

| FR | Server | Driver app |
|---|---|---|
| **FR1** on-time proof | ✅ | ✅ **complete end to end** (window + provenance + verdict) |
| **FR2** condition protocol | ✅ | ✅ **complete end to end** |
| **FR3** wallet | ✅ reads · ❌ **dispatcher unbuilt** | ✅ §10.4 anatomy, 2 taps measured |
| **FR4** incident | ✅ | ✅ **complete end to end** (file → view → export → share) |
| **FR5** summary | ✅ | ✅ **complete end to end** |

**Four of five FRs are complete end to end.** FR3 is the last, and only its unattended half remains.

## 6. Exact next task — Session 7

1. **The F6 expiry dispatcher** — FR3's other half and the last thing standing between M5 and its DoD.
   Reported unbuilt rather than unwired; verify that first. Multiple doc types at 30/14/3 against
   §13.1's two-per-day ceiling is a contention problem — reuse HANDOFF-081's shape, ordered by
   proximity to expiry.
2. **FR5's EXIT carve-out** — and **check M2-FR4's micro-review prompt really does fire on geofence
   EXIT** before relying on it as precedent. This prompt's premises have been wrong often enough.
3. **M5 DoD close-out** — the full §22.3 sweep and a plain statement of which FRs are complete.

Both notification items contend for the same budget, so derive the ordering rule once.

## 7. Foundation debt logged this session

**F5 has no path to correct a parsed appointment window.** The value arrives from an AI-Gateway parse
of a rate con and is thereafter immutable in the product. FR1 now makes a wrong window *visible* before
arrival, which is most of the protection — but a driver who spots the error still cannot fix it, and
`Stop.appointment_*` is F5's field. This belongs with F5, alongside the confidence-scoring idea the PRD
gestures at but does not specify. Recorded here rather than worked around in M5.

## 8. Blockers

- **No git remote — fifteen sessions, thirty-seven commits, one disk.**
- **A global voice affordance does not exist** — the status-strip mic stays disabled and labelled; M11.
- Carried, untouched: the F2 geohash-boundary duplicate miss and `merge_facilities` staleness.

## 9. Commits this session

```
(this commit) docs: HANDOFF-087
0d9d8e1 The theme override had no control, and a link could die mid-dispute
```

## 10. Key files touched

```
DOCS  design-prd.md §23 #45 (the two classes of §22.3 check)
F4    domain/sharing.py (default 365, extend_share that never shortens) · public.py
API   api/load.py (appointment_end + appointment_source on the meter)
      api/m05_protection.py (POST /share/{id}/extend)
UI    core/theme.js (persistence + initTheme) · main.js (boot apply)
      surfaces/MoreSurface.vue (Appearance chips; own class so the six-locale
      assertion keeps its meaning)
      surfaces/LoadSurface.vue (window + provenance; retains the incident id)
      core/components/IncidentSheet.vue (emits incident_id)
      surfaces/EvidenceSurface.vue (pack kind from the query)
      i18n/*.json (9 keys ×6)
TESTS f04/test_sharing.py (+3, incl. extend-never-shortens)
```

## 11. Ports / env / flags

**No port, env, migration or flag changes.** One F13 **config** default changed:
`f04_share_link_days` 90 → **365**.
