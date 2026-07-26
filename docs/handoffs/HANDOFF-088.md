# HANDOFF-088 — the wallet gets a writer, and FR3 closes

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** **all five M5 FRs are now complete end to end** — the last gap was found by the
owner looking at an empty screen, and it was not missing data.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0048_m05_on_time_consent** (none added) |
| Tests | **pytest 935 · vitest 345 · layout 136/136 · ruff clean · import-linter 30/30** |
| §23 decision log | 45 entries |
| Handoffs | 000 → 088 |
| Git | **40 commits local on `main`, still no remote** |

## 2. What looking at the screen caught

The owner opened the Docs tab and asked why it was empty. Two defects, one visible and one structural.

**Visible:** the surface had **no empty state at all**. §15.3 requires one sentence of purpose plus one
starting action; removing the dead capture chip in session 5 had taken away the only thing below the
button, so an empty wallet rendered *nothing* and read as broken.

**Structural, and the real finding:** every driver-facing document endpoint was a **GET**.

| Who could write a document | |
|---|---|
| M4 accessorial · M9 money · M13 vendor portal | ✅ |
| **A driver** | ❌ **nothing** |

A cook could upload a business licence through the vendor portal; a driver could not upload their own
CDL. **The wallet was a reader with no writer** — which is why the tab was empty, and why the capture
chip had been dead since it was written.

**And that blocked FR3's other half.** F6's expiry engine counts down from `expires_on`, and nothing a
driver did could ever set one. A dispatcher shipped first would have had nothing to dispatch. Building
the notifier before the thing it notifies about is backwards, so both halves landed together.

## 3. What was built

**The writer.** `POST /protection/documents` — typed into F6, scoped to the **stop** for a BOL and to the
**account** for a credential, queued offline like every other capture because a credential is most often
photographed at a scale house. `GET /protection/documents/types` tells the form which types exist and
which of them an expiry date means anything for; a BOL does not expire, and asking for a date that will
never matter teaches a driver the form is not paying attention.

It accepts only the types a **driver** files. A lumper receipt arrives from M4's claim and a settlement
from M9 — offering them here would invite filing a receipt in the wrong place. A settlement is refused
with a 422.

**The capture UI** (§8): guided, one screen, review-before-confirm, works at zero connectivity. **DRIVING:
does not render** — a credential photographed at 65 mph is not a credential.

**The capture chip is back**, which is the round trip worth noting: it shipped with no handler, was
removed under §23's registry precedent (*a capability whose destination does not exist is labelled,
never linked*), and returns now that there is an endpoint for it to reach.

**The notifier.** The 30/14/3 offsets F6 has always computed, dispatched as **P1**. §13.2 names "doc
expires this week" as a P1 example, so **no new notification class and no §22.2 stop**. A daily worker
job runs it.

**The ordering is the design.** §13.1 allows two unprompted notifications per driver per day; five
credentials at 30/14/3 is fifteen events, so most lose. When something has to lose, the survivor should
be the most urgent — the same rule settled for vendor alerts in HANDOFF-081. A reminder is marked sent
when **dispatched**, not delivered: re-offering the same 30-day warning every morning until one gets
through is the nagging §13 exists to prevent. The next rung still comes.

## 4. Verified live

```
wallet before: 0 documents
filed 4 credentials through the endpoint that did not exist
wallet after: 4 documents · expiring strip: 3
a settlement is refused — it arrives from M9, not from a driver

due today, nearest first: [('med_card', 3), ('insurance', 14), ('permit', 30)]
dispatched 3 · sent 2 · suppressed 1
   med card expires in 3 days    -> sent
   insurance expires in 14 days  -> sent
   permit expires in 30 days     -> budget
8/8 checks OK
```

The cap bit exactly where it should: the two most urgent went out, the 30-day permit lost.

## 5. M5 FR status — server vs end to end

| FR | Server | Driver app |
|---|---|---|
| **FR1** on-time proof | ✅ | ✅ **complete end to end** |
| **FR2** condition protocol | ✅ | ✅ **complete end to end** |
| **FR3** wallet | ✅ **writer + dispatcher** | ✅ **complete end to end** |
| **FR4** incident | ✅ | ✅ **complete end to end** |
| **FR5** summary | ✅ | ✅ **complete end to end** |

**All five FRs are complete end to end.** PRD §8.5's DoD also required inspection mode usable offline in
under 2 taps — **measured at 2 taps, offline, session 4**.

## 6. Exact next task — Session 8

M5's FRs are done; what remains is closing it out properly.

1. **FR5's EXIT carve-out** — the one deferred notification item. An irrecoverable gap at a state
   transition is a deadline, not a nag. **Verify M2-FR4's micro-review prompt really fires on geofence
   EXIT** before relying on it as precedent; these premises have been wrong often enough.
2. **The M5 DoD close-out** — the full §22.3 sweep across every M5 surface, and a plain statement of
   what is and is not done.
3. **Then M6.** M5 was chosen because its finish line was entirely inside our control. The next module
   should be chosen the same way — worth a deliberate recommendation rather than defaulting to numeric
   order.

## 7. Debt logged, not worked around

- **F5 has no path to correct a parsed appointment window** (HANDOFF-087 §7). FR1 makes a wrong window
  *visible* before arrival, which is most of the protection, but the driver still cannot fix it and the
  field is F5's.
- **A global voice affordance does not exist** — the status-strip mic stays disabled and labelled; M11.
- **Rate-con import is unbuilt.** §10.2 specifies "Add a load" via rate-con photo on the empty Load tab;
  the document writer now exists to receive one, so this is smaller than it was.

## 8. Blockers

- **No git remote — sixteen sessions, forty commits, one disk.**
- Carried, untouched: the F2 geohash-boundary duplicate miss and `merge_facilities` staleness.

## 9. Commits this session

```
(this commit) docs: HANDOFF-088
bf1bcd9 The wallet had no writer, so the notifier had nothing to say
d33423b An empty Docs tab rendered nothing at all
a2d2743 docs: HANDOFF-087
0d9d8e1 The theme override had no control, and a link could die mid-dispute
```

## 10. Key files touched

```
M5     domain/service.py (capture_document, expiry_reminders_due,
       dispatch_expiry_reminders, DRIVER_DOC_TYPES, EXPIRING_DOC_TYPES) · public.py
API    api/m05_protection.py (POST /documents, GET /documents/types)
WORKER app/worker.py (daily document_expiry job) · app/ingest/runners.py
UI     core/components/DocumentCaptureSheet.vue (NEW — §8 capture)
       surfaces/DocsSurface.vue (empty state, capture chip restored, DRIVING guard)
       core/api.js (captureDocument, fetchDocumentTypes)
       i18n/*.json (17 keys ×6)
DEV    api/scripts/seed_wallet.py (NEW) · Makefile (seed-wallet)
       infra/docker-compose.yml (playwright browser in a named volume)
TESTS  m05/test_documents.py (NEW, 8)
```

## 11. Ports / env / flags

**No port, env, migration or flag changes.** The expiry job rides the existing `m05_protection` flag.
One dev convenience added: `make seed-wallet EMAIL=…`.
