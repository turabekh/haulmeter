# HANDOFF-083 — FR1, FR2, FR4 and the share path (M5 session 2 of 3)

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** three M5 FRs used words the code did not support — "auto-fires", "one-tap export",
"shareable" — and all three are now true, on a share path that pins what was sent rather than caching
what the chain currently says.

**Session 2 of 3.** §7 carries the honest gap: **the driver-facing UI for export and share did not land.**

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0048_m05_on_time_consent** (two added: 0047, 0048) |
| Tests | **pytest 922 · vitest 345 · ruff clean · import-linter 30/30** |
| §23 decision log | 42 entries |
| Handoffs | 000 → 083 |
| Git | **26 commits local on `main`, no remote configured** |

## 2. Carry-forward corrections (Step 3), with two corrections to the brief itself

**3.1 divergence — done.** F4 stored `received_at` on records and artifacts; `compose_pack` threw it
away at the composition boundary. It now travels, and a row whose clocks diverge by **≥ 5 minutes**
prints both: `2026-07-20 08:06:00 UTC · filed 14:22`. The threshold is a named constant in the renderer
with its reasoning beside it, not F13 config — it is a statement about evidence, not a tuning knob.

**3.2 font scope — reported plainly: BOTH.** Session 1 vendored five woff2 + five `@font-face` rules
for the app *and* the same faces as TTF for embedding. The app defect does not stand. But the
re-verification premise needed correcting twice, and one gap is worse than supposed:

- **There are no `xx-XL` clipping checks to re-run.** `pseudo-locale.test.js` tests the string
  generator and says so in its own docstring. It never mounts a component and **structurally cannot**:
  vitest runs in jsdom, which has no layout engine, so `getBoundingClientRect` returns zeros and no
  overflow assertion could ever fail. That DoD line has never been mechanically enforced, against any
  font. Logged, not quietly satisfied.
- **T-2 was accidentally safe.** `TheMeter` always set `font-variant-numeric: tabular-nums`; the
  guarantee was delivered by the fallback stack happening to be monospace. It now holds by design and
  by test (`ui/test/typography.test.js`, 6 tests).
- **The Gurmukhi claim is false on all three counts.** §6.2 says Noto Sans Gurmukhi is "mapped as the
  family for `pa` locale; metrics-compatible line-height tokens verified". The font is **not
  vendored**, `--font-gurmukhi` is **applied to nothing** (no `:lang(pa)` rule exists), and no metrics
  verification was ever done — so `pa` renders in Plex Sans, **which has no Gurmukhi coverage at all**.
  Owner-scheduled for session 3.

**3.3 P2 audit — nothing is dropping, because nothing is classified P2.** The only `NotificationTier.P2`
in the tree is in a test. `m03_detention`'s `evidence_only  # company driver (P2)` is a **persona**
reference (PRD §4), not a tier — same token, different namespace, exactly what a future grep would
misread. Rule recorded in §23: **nothing may be filed P2 until a surface renders the digest.**

**3.4 trace — vector plot from located evidence**, no basemap. `render.py` imports no network module of
any kind; the e2e renders it with no services running.

## 3. What was built

| | |
|---|---|
| **`PackTemplate.incident`** | An accident pack announced itself as "Cargo condition report". No migration — never persisted |
| **F4 sharing** (`domain/sharing.py`, `SharedPack`, migration 0047) | render → content hash → F6/MinIO → **SYSTEM record into the chain** → opaque token |
| **`GET /pack/s/{token}`** | The second unauthenticated surface. §17: one link, no session, no images |
| **FR2** | `condition_pack` + `GET /protection/condition/{stop}/export` |
| **FR4** | `incident_pack` on the right template + export + share |
| **FR1** (migration 0048) | `OnTimeConsent` per load; `auto_file_on_arrival` hooked into `POST /load/{stop}/arrive` |

**Export is a view. Share is a record.** Export regenerates and is always current — right for the
driver's own copy. Share pins the bytes, because a pack shared at 14:00 and regenerated at 16:00 after
another photo lands is a **different document**, and the dispute question is never "what does the pack
say now". Revocation ends the hosting, **not the record**: the hash and stored bytes survive, because
closing a link does not unsend a document. Unknown, revoked and expired all return one 404 so tokens
cannot be probed. The **first** open lands in the chain — "they opened it on the 12th" is evidence; the
fourth refresh is not a fourth fact.

**FR1 runs on the arrival that already exists.** The geofence ENTER that starts the detention clock is
the arrival that proves on-time, so no new geofence machinery. Two rules made explicit: **the proof is
filed on every arrival**, opted in or not, because it is the driver's own protection — and **a late
arrival notifies nobody**, because the only notice this FR can send says the driver was on time.

## 4. What live verification caught that the tests did not

Eleven green tests, nine green live checks, and a rendered condition report that **could not do its
job**:

```
BEFORE   08:06 UTC   Photo
         08:06 UTC   Photo          ← which one is the seals?
         08:06 UTC   Photo
AFTER    08:06 UTC   Photo   trailer exterior
         08:06 UTC   Photo   seals
         08:06 UTC   Photo   load blocking
```

The guided sequence exists so a clerk can tell whether the seals were photographed. The prompt lived in
the artifact's exif and never reached the chained record — and a prompt is a **claim about what an image
shows**, so it belongs in the chain hashed with it. The same look found the second defect: the export
passed no `PackContext`, so a condition report arrived with no facility, no load reference and no
appointment — a photo album for a reader who did not take the pictures. Both now locked by tests.

Also, twice this session my **assertion** was wrong rather than the code: the live script grepped for
`pack_shared` when the renderer humanises payload events to "pack shared". Asserting the raw key tested
my memory of the code, not the document.

## 5. Verified live

```
FR1 arrive        -> on_time=True notice_sent=True
FR2 sequence      -> trailer_exterior · seals · load_blocking · reefer_setpoint
FR2 export        -> 98,020 bytes    FR4 export -> 96,423 bytes
share             -> /pack/s/<token>  hash=669d23ff…  expires 2026-10-24
9/9 checks OK — both titles correct · opens with NO session · the export changed
when evidence landed · the SHARE did not · share and first open in the chain
revoked           -> link 404s, hash preserved
```

Both PDFs were opened and read, not just asserted on.

## 6. Decisions (all four to the recommendation)

Divergence **≥5 min** · FR4 gets its **own template** · share link **signed-equivalent opaque token, 90
days (F13 `f04_share_link_days`), revocable, opens logged** · Gurmukhi **logged now, fixed in session 3**.

## 7. Exact next task — session 3, and the gap this session leaves

**The driver-facing UI for export and share did not land.** The domain and API are complete and tested;
there is no button. I stopped rather than ship UI without its six locales, pseudo-locale pass and
DRIVING guards, which would have failed §22.3 and left a worse mess than an honest gap. **Session 3
opens with it**, alongside the wallet UI, so the whole M5 surface takes one locale sweep instead of two.

Session 3, in order:

1. **The M5 UI**: export/share affordances, the offline "will send when you have signal" state (share
   needs network; capture does not), i18n ×6 + pseudo, DRIVING guards.
2. **FR3**: the F6 expiry **dispatcher** — unbuilt, not unwired (HANDOFF-082 §2). Reuse HANDOFF-081's
   settled shape: where the cap bites, order by proximity to expiry. Five doc types × 30/14/3 is fifteen
   events against §13.1's ceiling of two per day.
3. **Inspection mode measured** at ≤2 taps from cold start, offline.
4. **FR5**: the §10.2 evidence checklist card + the EXIT carve-out (irrecoverable gap = P1 deadline).
5. **Gurmukhi**: vendor the font, `:lang(pa)`, real metrics check.

## 8. Blockers and open questions

- **No git remote — eleven sessions.** Twenty-six commits local on `main`.
- **The `xx-XL` DoD line needs a decision**: a real browser in CI, or an honest restatement. It cannot be
  satisfied in jsdom.
- **Nothing renders the P2 digest.** Rule logged; if anything ever needs P2, the surface comes first.
- Carried, untouched: the F2 geohash-boundary duplicate miss and `merge_facilities` staleness.

## 9. Commits this session

```
(this commit) docs: HANDOFF-083 + §23 ×3
a1cd90f What opening the report caught: "Photo · Photo · Photo"
8654caa FR2 exports, FR4 shares, and FR1 fires on the arrival that already happened
613157d Where the two clocks disagree, the row says so
```

## 10. Key files touched

```
F4     domain/sharing.py (NEW) · domain/models.py (SharedPack) · domain/enums.py (incident)
       domain/service.py (received_at in the pack; prompt into the record) · public.py
       domain/render.py (divergence disclosure, incident title)
M5     domain/service.py (condition_pack, render_pack, share_pack, FR1 consent + auto-file)
       domain/models.py (OnTimeConsent) · public.py
API    api/m05_protection.py (export/share/revoke/consent + _context_for)
       api/share.py (NEW, the counterparty's door) · api/load.py (FR1 hook) · main.py
MIGR   0047_f04_shared_pack · 0048_m05_on_time_consent
TESTS  f04/test_sharing.py (NEW, 7) · f04/test_render.py (+2) · api/test_m05_export_share.py (NEW, 11)
       m05/test_m05.py (+5) · ui/test/typography.test.js (NEW, 6)
DOCS   design-prd §23 ×3 (40–42) · HANDOFF-083.md · HANDOFF.md
```

## 11. Ports / env / flags

**No port or env changes.** Two migrations (0047, 0048). No new flags — M5 rides `m05_protection`. One
new F13 **config** key: `f04_share_link_days` (default 90).

`make ci` leaves Postgres running, so **`make down && make up`** afterwards.
