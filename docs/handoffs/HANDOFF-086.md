# HANDOFF-086 — the harness starts finding dead controls (M5 session 5 of 6)

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** the two owed §23 entries are written, the layout harness stopped re-measuring a
dimension that cannot vary and started catching a bug class this project has produced six times, and
**FR1 and FR4 did not land** — §6 says so plainly.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0048_m05_on_time_consent** (none added) |
| Tests | **pytest 923 · vitest 345 · layout 136/136 · ruff clean · import-linter 30/30** |
| §23 decision log | **44 entries** (the two owed, written) |
| Handoffs | 000 → 086 |
| Git | **34 commits local on `main`, still no remote** |

## 2. Step 3 — the owed entries, and the concession

Written before any code, and the owner's argument was the correct one. Entry 41 had been carrying an
untrue statement — that the Gurmukhi claim was still false — with its correction scheduled for a session
that had not started. **41's third part is now marked superseded in place**, so a reader of 41 alone is
not misled.

The sharper point stands and is now in the log itself: **§6.2's "metrics-compatible line-height tokens
verified" exists because someone recorded an intention as an accomplishment**, and deferring log entries
so they can be reconstructed later is the same mechanism. The prompt-attribution entry also names, in
one place for the first time, the pattern its three precedents share: *when the platform repeats someone
else's claim, the sentence names who is speaking.*

## 3. Step 4 — three of four premises were wrong

| # | Premise | Finding |
|---|---|---|
| 4.1 | F5 has confidence scoring + a correction UI | **False.** The PRD's only "confidence" is M8-FR2, unrelated. Neither `f05_load` nor `f09_ai_gateway` has such a field, and **no appointment-edit path exists anywhere** |
| 4.2 | The capture chip has a destination it lost | **It never had one.** M5 has no document-upload endpoint at all |
| 4.3 | Incidents are reachable only via the evidence surface | **False.** `LoadSurface.vue:293` opens `IncidentSheet` — filing works. The real gap is that a filed incident's **pack** is unreachable: export/share is hardcoded to `"condition"` |
| 4.4 | The theme dimension may be redundant | **Worse — it was broken.** See §4 |

## 4. The harness: measured, then rebalanced

**The theme dimension had never worked.** `theme.js` keeps the mode in a ref and **never persists it**,
so the `longhaul.theme` key the harness had been setting for two sessions was read by nothing, and only
one of four assertions ever stamped `data-theme` itself. It had been running the same theme twice.

Measured properly, dark vs light across all six surfaces:

```
SAME  load · money · docs · more · login
DIFF  map   minFont 12 vs 13   ← Mapbox attribution furniture, already exempt
```

Five of six identical; the single difference is third-party. That matches §23's light-theme entry —
*"Only the 12 color tokens change; type/space/radius/motion/touch are theme-invariant"* — so these
assertions **cannot** vary by theme, by decision rather than by luck. Contrast, the theme-sensitive
property, is computed from tokens in `contrast.test.js`.

| | Before | After |
|---|---|---|
| Matrix | 6 surfaces × 2 themes × 3 locales × 4 | **9 surfaces × 1 theme × 3 locales × 5** |
| Checks | 144 | **136** |
| Runtime | ~3.4 min | ~2.3 min |

Added: **evidence, condition capture, facility profile** — the evidence surface being where session 4's
newest and largest UI landed (export, share, the §15.1 queue, the DRIVING guard) and never checked.

## 5. What the harness caught that no test did

**The fifth assertion — every control does something, or says it cannot — was added *before* the fix and
demonstrated failing on the capture chip**, because an assertion never seen to fail is not yet a test.

```
Error: controls that do nothing when pressed: strip__mic: "" | capture: "Add document"
```

It immediately found a **sixth instance of the bug class nobody knew about**: the status-strip mic, on
**every screen**, dead since the strip was written. The known five were the "suggest a cook" control
with no destination, `categories` collected and never read, `portions` carried through three API layers
to nowhere, `followers_notified` returned and rendered nowhere, and the chip.

Both resolved by §23's registry precedent — *a capability whose destination does not exist is labelled,
never linked*:

- **The capture chip is gone.** M5 has no upload endpoint; it promised a capability the platform does
  not have, and §22.2's first heuristic is remove rather than add.
- **The mic is disabled and titled**, not deleted. §14.2 asks for a persistent voice mic; a global one
  needs the voice sheet mounted at app level, which is **M11's work, not M5's to invent**.

And the three new surfaces gave up a real **40 dp back button** on the evidence surface at first sight —
the newest UI in the project, and until this session the least verified.

**A separate defect, out of scope, carried:** §6.1 C-3 says the theme is toggled by system setting **and
manual override**, and the override does not survive a reload because nothing persists it. One line to
fix; it is not M5.

## 6. What did NOT land

**FR1 and FR4 were not built.** The harness work — which was sequenced first by agreement, and which had
to be re-measured, rebalanced, extended by a surface tier and an assertion, then chased through two
rounds of findings — took the session.

- **FR1**: the appointment window is still not visible before arrival, not sourced, and not correctable.
  The decision from this session stands: show it early with provenance, edit in place on the Load tab
  writing to the F5 stop, verdict after. **Needs a stop-update path on the server; none exists.**
- **FR4**: a filed incident's pack is still unreachable. Export/share is hardcoded to `"condition"`;
  it needs to key on kind and get an entry point from the incident confirmation.

## 7. M5 FR status — server vs end to end

| FR | Server | Driver app |
|---|---|---|
| **FR1** on-time proof | ✅ complete, tested | ❌ window not visible, not correctable; verdict not shown |
| **FR2** condition protocol | ✅ | ✅ **complete end to end** |
| **FR3** wallet | ✅ reads · ❌ **dispatcher unbuilt** | ✅ §10.4 anatomy, 2 taps measured, dead chip removed |
| **FR4** incident | ✅ complete, tested | ⚠️ filing works; **pack unreachable** |
| **FR5** summary | ✅ | ✅ **complete end to end** |

## 8. Exact next task — Session 6

1. **FR1** — window visible early, sourced, correctable (needs the F5 stop-update path); verdict after.
2. **FR4** — pack keyed by kind, with an entry point from the incident confirmation.
3. **The F6 expiry dispatcher** (FR3's other half) — unbuilt, not unwired. Fifteen events against
   §13.1's ceiling of two per day; reuse HANDOFF-081's shape, ordered by proximity to expiry.
4. **FR5's EXIT carve-out** — irrecoverable gap at a state transition is a deadline, not a nag.
5. **Share-link lifetime** — 90 days may be shorter than a dispute.
6. **M5 DoD close-out** — full §22.3 sweep and a plain statement of which FRs are complete.

## 9. Blockers

- **No git remote — fourteen sessions, thirty-four commits, one disk.** Raised again deliberately. This
  is the largest uninsured risk in the project and it is not a technical one.
- **Theme override does not persist** (§4) — one line, not M5.
- **A global voice affordance does not exist** (§5) — M11.
- Carried, untouched: the F2 geohash-boundary duplicate miss and `merge_facilities` staleness.

## 10. Commits this session

```
(this commit) docs: HANDOFF-086
4cf1732 The harness stops re-measuring themes and starts finding dead controls
715c4d9 §23: the two owed entries, written now rather than reconstructed later
```

## 11. Key files touched

```
DOCS    design-prd.md §23 ×2 (43–44) + entry 41 superseded in place
HARNESS ui/layout/layout.spec.js (themes out, 3 surfaces in, 5th assertion,
        mapbox exemption for imperatively-attached listeners)
UI      surfaces/DocsSurface.vue (capture chip removed, with the reason)
        core/components/StatusStrip.vue (mic disabled + titled)
        surfaces/EvidenceSurface.vue (.back 40 → 48)
        i18n/*.json (voice.unavailable ×6)
```

## 12. Ports / env / flags

**No port, env, migration, flag or config changes.**
