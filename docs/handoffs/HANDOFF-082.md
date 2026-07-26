# HANDOFF-082 — the evidence pack is a PDF (M5 session 1 of 3)

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** the artifact design-prd §17 has specified since v1.0 now exists — a real,
deterministic, self-describing PDF rendered from a hash chain — and the Foundation DoD assertion that
had quietly stopped requiring it requires it again.

This is **session 1 of 3** on M5 (see §6 for the split). M5's own five FRs are next; nothing in M5 was
touched this session beyond confirming its state.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0046_f08_followed_subjects** (none added) |
| Tests | **pytest 897 · vitest 339 · ruff clean · import-linter 30/30** |
| §23 decision log | 39 entries |
| Handoffs | 000 → 082 |
| Git | **22 commits local on `main`, no remote configured** |
| New dependency | `reportlab>=4.2` (installed 5.0.0) — pure-Python wheel, **no Dockerfile change** |

## 2. What the read-and-verify pass found

The kickoff listed eight findings and asked me not to trust them. Six confirmed, **one materially
wrong**, and **two things nobody had listed**.

**Wrong — F6's expiry engine.** The offsets exist (`REMINDER_OFFSETS = [30, 14, 3]`,
`active_reminder_offset`, `due_reminders`, `mark_reminder_sent`) but **F6 does not import F8 at all and
nothing anywhere calls `due_reminders`.** There is no worker job. It computes what is due and records
what was sent; the dispatching caller does not exist. M5-FR3's alerts are **unbuilt, not unwired** —
budget session 3 accordingly. One piece of good news attached: §13.2 names *"doc expires this week"* as
a **P1 example**, and `get_class` returns `None` for unregistered categories, so expiry alerts need
**no new notification class** and trigger no §22.2 stop.

**Unlisted #1 — the Plex fonts were never vendored.** `tokens.scss` named the families with a system
fallback and the repo held no font file, so the app has been rendering in whatever the device had.
§6.2 calls the type "the professionalism" and permits no other family. That was a claim, not a fact.
Fixed: five faces vendored twice — woff2 for the app, the same faces as TTF beside F4 for embedding.

**Unlisted #2 — the light theme was already approved.** §23, 2026-07-20, all twelve values locked and
contrast-verified. So §17's "shield on white" needed **no new token and no §23 proposal**; only the
print scale is derived. A stale `tokens.scss:6` comment claiming the ramps were "intentionally absent"
was deleted — it was contradicted by the approved mixin 160 lines below it.

**And one more of the same species as the e2e docstring:** `test_incident_capture_produces_shareable_pack`
asserts `chain_valid` on a dataclass. Nothing is shareable; the name says otherwise. Session 2 fixes it.

## 3. What was built

`f04_evidence/domain/render.py` — `render_pack_pdf(pack, context)` fills the seam that raised
`RenderNotEnabled`. `compose_pack` still composes; rendering is a separate concern consuming it, so M3,
M4 and M9 inherit each independently.

**§17 anatomy, in order:** Meter header strip (§9 composition — label above, Mono figure below, same
numbers and wording as every other surface) → parties → load references → event timeline with Mono
timestamps and hairline rules → location trace → artifact thumbnails → hash-verification block.

**`PackContext`** carries what F4 cannot know. The parties are F5's records and a detention total is
M3's arithmetic; F4 owns the chain and refuses to compute either, so the caller supplies them and an
empty section is **omitted rather than rendered blank**.

**Decisions, all four to the recommendation:** ReportLab (pure-Python wheel; F15's English-only rule
removes the shaping argument for WeasyPrint) · vector trace from located evidence, no basemap ·
byte-identical renders · regenerate on view, persist on share *(the persist half lands in session 2
with FR2/FR4's export)*.

Two further calls worth recording. **Streams stay uncompressed** — the fonts dominate the size anyway
(126 KB total), and an uncompressed pack can be read with `strings` and no PDF library, which removes a
tool from a third party's job. **The dead `RenderNotEnabled` was removed** and the test asserting the
seam was **inverted rather than deleted**, so the record of what changed survives.

## 4. What live verification caught that the tests did not

The byte assertions were green and the document was still wrong. Opening it found **one root cause with
two symptoms**:

```
BEFORE   07:58 · 08:04 · 09:58 · 08:58 · 09:58 · 08:06 · 11:18 · 11:24
AFTER    07:58 · 08:04 · 08:06 · 08:58 · 09:58 · 09:58 · 11:18 · 11:24
```

The chain is ordered by **seq**, because that is what the hashes commit to. A photo attached after the
fact but stamped with its capture time therefore sits late in the chain and early in the day. Rendering
chain order produced a timeline a clerk reads as sloppy at best — and **the same defect drew the
location trace as a zig-zag between points nobody drove**. Display now sorts by time; the evidence is
untouched and the verification block still covers the seq-ordered chain. Both are locked by tests that
would have caught it.

Also caught by looking: the north arrow sat on top of the start marker, since the first plotted point
is frequently the west- and north-most. Moved.

Not a bug, worth recording so the next reader does not chase it: the artifacts and verification
sections render on **page 2**. `sips` rasterises page 1 only.

## 5. Verified live

```
chain: 8 records, anchored=True
rendered: 125,897 bytes
deterministic: True
16/16 checks OK — %PDF header · %%EOF · byte-identical re-render ·
creation date from the chain (2026-07-20, not today) · Plex Sans + Mono
embedded · /FontFile2 present · Meter figure · parties · references ·
timeline · trace · artifacts · verification · "Hash chain intact"
timestamps greppable without a PDF library: 8
```

The smoke script knows what time it is: the chain is seeded at fixed timestamps and the document date
is asserted against **those**, never against today. An earlier draft compared the current *year* and
would have passed for the wrong reason all year.

## 6. Exact next task — session 2 of 3

**M5-FR1, FR2 and FR4 — the evidence-producing FRs**, all three of which needed the renderer:

- **FR1 on-time proof** is reachable only from a manual `POST /protection/on-time`. PRD §8.5 says
  geofence ENTER inside the appointment window **auto-fires**; nothing hooks it, and the per-load
  opt-in is not stored anywhere.
- **FR2** has the guided sequence and hash-chained photos but **no export** — `condition_pack` does not
  exist.
- **FR4** returns a dataclass from `incident_pack`; "shareable" is currently untrue. This is where the
  persist-on-share half of decision 4 lands: render → F6/MinIO with its own content hash → that hash
  written into the chain as a SYSTEM record.

**Session 3:** FR3 (the expiry dispatcher, which is unbuilt — see §2 — plus inspection mode **measured**
at ≤2 taps cold-start offline) and FR5 nudges, then the full §22.3 sweep.

## 7. Blockers and open questions

- **No git remote — ten sessions running.** Twenty-two commits sit locally on `main`.
- **Open, for session 2:** FR5's gap nudges need a tier. §13.2 covers doc expiry as P1; "you have no
  delivery photos" is not time-critical, so I will propose **P2 digest** — but P2 is *digest only, never
  pushed*, and **no screen renders a digest today**. If you want gap nudges pushed, that is a new
  opt-in class and a §22.2 STOP.
- **Carried, untouched (not this module):** the geohash-boundary duplicate miss in
  `find_duplicate_candidates` and the `merge_facilities` attribute staleness it compounds.
- The vendor portal does not surface `followers_notified` (081); the claimable universe is ten
  facilities (079); no vendor self-delete (§17 Q16); no vendor-registration rate limit.

## 8. Working rules (unchanged — non-negotiable)

Docker-only · **local commits only, NEVER push** · plan first, owner approval, then code · tests with
every change · **AI-CONTEXT comments only** · import-linter authoritative · design-prd governs ALL UI ·
§22.2 never improvises a token, component pattern, navigation structure or notification class · session
ends by writing the next HANDOFF.

**Untouched this session by explicit instruction:** M13, `test_phase_a_law.py`, the `longhaul-evidence:`
hash namespace, the carried F2 blockers. **Phase A holds.**

## 9. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-082 + §23 ×2 — the §17 artifact
fb55fa3 The evidence pack is a PDF again
eba21b7 The fonts §6.2 has always claimed we shipped
```

## 10. Key files touched

```
DEPS     api/pyproject.toml (+reportlab>=4.2; no Dockerfile change)
FONTS    api/app/foundation/f04_evidence/assets/fonts/ (5 TTF + OFL licence)
         ui/public/fonts/ (5 woff2 + licence) · ui/src/core/tokens.scss (@font-face)
F4       api/app/foundation/f04_evidence/domain/render.py (NEW, the §17 artifact)
         .../domain/service.py (seam filled; dead RenderNotEnabled removed)
         public.py (+PackContext, −RenderNotEnabled)
TESTS    api/tests/foundation/f04_evidence/test_render.py (NEW, 12)
         .../test_evidence.py (the seam test INVERTED, not deleted)
         api/tests/e2e/test_common_ground_e2e.py (§7.16(b) renders a real PDF)
DOCS     design-prd.md §23 ×2 (entries 38–39) · HANDOFF-082.md · HANDOFF.md
```

## 11. Ports / env / flags

**No port, env, migration or flag changes.** LOCKED: postgres **5438** · api **8008** · ui **9008**.

**The api image was rebuilt** for reportlab. A running container started before the rebuild will
`ModuleNotFoundError` — this cost me one confusing failure. After pulling this branch:
**`make down && make up`**, which is the same sequence `make ci` already requires.
