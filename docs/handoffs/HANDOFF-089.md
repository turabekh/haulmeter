# HANDOFF-089 — the wallet gets a way out, and the harness was measuring an error page

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** the document wallet is now writable in **both** directions — a driver can take a
document out and put it back — and the §22.3 layout harness, which has reported 136/136 for four
sessions, was found serving Vite's "Blocked request" page to Playwright.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0050_f06_document_archive_reason** |
| Tests | **pytest 964 · vitest 354 · layout 136/136 · ruff clean · import-linter 30/30** |
| §23 decision log | 46 entries |
| Handoffs | 000 → 089 |
| Git | **48 commits local on `main`, still no remote** |

## 2. What was asked, and what it collided with

The owner asked for a delete option and a way to see archived documents — "full-fledged document
management". Delete is refused twice over: **PRD §17 Q16** keeps hard delete deliberately unbuilt
pending counsel, and **yesterday's §23 entry** says in as many words that an old card is still the
answer to *"what were you carrying at that inspection in March"*.

So the question was put back to the owner as three options, and the answer chosen was
**remove = archive, restorable**. The mis-capture case — a driver photographs a bank card by mistake
and archiving is not enough — was explicitly **left for a §17 Q16 carve-out** rather than smuggled in
under a button label.

## 3. What was built

**Removal is the driver's now.** `POST /protection/documents/{id}/archive` takes a document out of
circulation, not out of existence: it leaves the grid, leaves inspection mode and stops the expiry
ladder while the row and the bytes stay untouched. `POST .../restore` is the half that makes offering
it honest — an irreversible removal is not a decision a driver makes with gloves on at a fuel desk.

**Both are idempotent at the server**, which is why neither needed F12 idempotency bookkeeping: a
removal made in a dead zone replays on reconnect and is simply true again. A replay must also never
**rewrite the reason** — relabelling a supersession as something the driver did would make the archive
state something untrue about how the row got there.

**The archive was already in the database and unreachable.** `documents_for_account` has taken
`include_archived` since it was written and **no route ever passed it** — the third capability found
sitting in F6 with nothing reaching it, after the wallet's writer (session 6) and the viewer (session
7). §17 Q16 keeps these rows forever; until now "forever" meant "invisible to the person they belong
to".

**Every archive row says why it is there and whether Restore will work.** `archive_reason` is a column
because "replaced by a newer one" and "you removed this" lead to different decisions. A blocked
restore **names what is in the way**, and the block is the supersession rule from the other side: two
live CDLs is a question about which is current, asked at a roadside inspection. Permits never block
because they never supersede — one rule, two directions.

**Two defects fixed in passing.** The grid never grouped **by type**, which §10.4 has always specified;
and it derived its own English labels beside a `docs.type.*` catalogue carrying all six locales since
the capture sheet was built, so a Somali driver read "Med Card" in the grid and "Kaarka caafimaadka"
in the form for the same document.

## 4. The harness was green over nothing

Running `make ui-layout` failed **one** check — the inspection 2-tap spec. The page snapshot said:

```
Blocked request. This host ("ui") is not allowed.
To allow this host, add "ui" to `server.allowedHosts` in vite.config.js.
```

Vite's dev-server host check answers an unlisted `Host` header by serving an error page **instead of
the app**. That page has no horizontal overflow, no clipped text and no tap target under 48 dp, so
**135 mobile-first checks passed against a screen that was not ours.** Only the inspection spec
noticed, because it is the only one that *clicks something*.

`allowedHosts: ["ui"]` fixes it. 136/136 now pass against the real app, and the run went from **1.2 m
to 2.5 m** — the cost of actually rendering nine surfaces in three locales.

**Not established:** when this started. The lockfile pins vite 6.4.3 and has since the harness landed,
yet HANDOFF-085 reported a real measured tap count, which an error page cannot produce. The likeliest
story is that the `ui` container's `node_modules` predated the pin and was refreshed when the stack was
recreated this session. **Stated as unresolved rather than guessed at** — the archaeology is worth an
hour if the harness is ever trusted for a release gate.

## 5. Verified live

```
filed a CDL and a permit          wallet: [permit, cdl] · archived: 0
driver removes the permit         reason: removed_by_driver
                                  wallet: [cdl] · archived: 1
inspection mode                   [cdl]                     (it is gone from the officer's screen)
GET the removed document          200, 26 bytes             (the bytes are still there)
renewing the CDL                  cdl     superseded        restorable=False  blocked_by=cdl
                                  permit  removed_by_driver restorable=True
restore the superseded CDL        "a current cdl is already in the wallet"
restore the permit                wallet: [cdl, permit] · archived: 1
```

The refusal names the document in the way; the removal does not destroy anything; and the bytes come
back from real MinIO, so `d8dfc60`'s object-storage fix is still holding.

## 6. Exact next task — Session 9

Unchanged from HANDOFF-088 §6, none of it started this session:

1. **FR5's EXIT carve-out** — verify M2-FR4's micro-review prompt really fires on geofence EXIT
   before relying on it as precedent.
2. **The M5 DoD close-out** — the full §22.3 sweep across every M5 surface. **Now worth more than it
   was**, because §4 means the last four sessions' layout evidence has to be re-earned rather than
   cited.
3. **Then M6**, chosen deliberately for a finish line inside our control rather than by numeric order.

## 7. Debt logged, not worked around

- **The harness does not open sheets.** It measures the nine base surfaces; the archive sheet, the
  confirm sheet, the viewer, the capture sheet and inspection mode all render only on interaction and
  are therefore **unmeasured at 360 dp**. Pre-existing, now load-bearing for more surfaces.
- **The archive control is unmeasured for the same reason** — the harness surface has no session data,
  so `archived_count` is 0 and the control correctly does not render.
- **Hard delete for a mis-capture** remains unbuilt: the §17 Q16 carve-out the owner deferred.
- Carried, untouched: F5 has no path to correct a parsed appointment window; no global voice
  affordance (M11); rate-con import unbuilt; F2 geohash-boundary duplicate miss; `merge_facilities`
  staleness.
- `collect_files.py` sits untracked at the repo root and is not ours to commit or delete.

## 8. Blockers

- **No git remote — seventeen sessions, forty-eight commits, one disk.**

## 9. Commits this session

```
(this commit) docs: HANDOFF-089
§23: delete is remove, and remove is reversible
The layout harness was measuring Vite's error page
A wallet you cannot take anything out of is a drawer that only opens one way
```

## 10. Key files touched

```
MIGRATION  0050_f06_document_archive_reason (archive_reason + backfill to 'superseded')
F6         domain/models.py (archive_reason) · domain/service.py (archive_document,
           restore_document, ARCHIVE_* ; supersede_document delegates) · public.py
M5         domain/service.py (archive_own_document, restore_own_document,
           restore_blocked_by, archived_documents, archived_count, RestoreBlocked;
           wallet gains archived_count) · public.py
API        api/m05_protection.py (GET /documents/archive — declared BEFORE
           /documents/{id} or the UUID route swallows it; POST .../archive; .../restore)
UI         surfaces/DocsSurface.vue (grid grouped by type, translated labels, archive
           control + sheet, confirm sheet, restore)
           core/components/DocumentViewer.vue (Remove; no edit/remove on an archived doc)
           core/api.js (archiveDocument, restoreDocument, fetchArchivedDocuments)
           core/fixtures.js · i18n/*.json (13 keys ×6)
           vite.config.js (allowedHosts — §4)
TESTS      m05/test_documents.py (+13) · api/test_m05_export_share.py (+7)
           ui-components.test.js (+9 DocsSurface)
```

## 11. Ports / env / flags

**No port, env or flag changes.** One migration (0050). The archive rides the existing
`m05_protection` flag.
