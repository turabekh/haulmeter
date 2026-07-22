# HANDOFF-060 — F6 image serving: real evidence-photo thumbnails (activation seam #2)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 22 July 2026 · **State:** F1–F15 + M1–M12 complete. Mapbox live, F9 real Claude live, FMCSA authority verification live (HANDOFF-059). **New this session: F6 image serving — captured evidence photos now persist to object storage (MinIO) and serve back as real thumbnails in the Evidence view.** Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–059.

---

## 1. What now exists and passes (delta since HANDOFF-059)

HANDOFF-059 shipped the FMCSA verification seam and flagged the next activation seam as an owner choice. The owner chose **F6 image serving** (make the just-built Evidence loop tangible). Built this session, end-to-end.

**The gap that existed:** `f04.attach_artifact` hashed captured photo bytes into the tamper-evident chain but **dropped the bytes** (`storage_key` was always null). So the Evidence view showed verified, labeled rows behind a Camera-icon placeholder — never the real image.

### Persist on capture (M5 → F6 object storage)
- **MinIO is now in the evidence write/read path** — API `lifespan` wires `documents.set_default_storage(MinioObjectStorage(...))` at startup, falling back to the in-memory default if MinIO is unreachable. New `minio_bucket` setting (default `longhaul`). MinIO was already in the compose topology (9018/9019).
- **M5 stores the bytes** (`m05_protection/domain/service.py`) — `_persist_photo_bytes()` puts the image to F6 object storage under `evidence/{log_id}/{uuid}` and records the `storage_key` + real content-type (in the artifact `exif`). Both capture paths (`add_condition_photo`, `add_incident_photo`) use it. F4 stays storage-agnostic (its `storage_key` param was always the intended seam).
- **Resilience:** the byte-store is wrapped in try/except — if MinIO hiccups, the artifact + hash still record (chain integrity is never blocked by storage); the image is just "unavailable" to serve. No migration needed (`storage_key` + `exif` already existed on `EvidenceArtifact`).

### Serve (F4 + app.api)
- `f04.stop_evidence` now surfaces `artifact_id` + `has_image` per photo; new `f04.get_artifact(db, id)` public.
- New owner-gated endpoint **`GET /load/{stop_id}/evidence/photo/{artifact_id}`** — verifies the artifact's log belongs to the owned stop (no cross-load peeking), streams the bytes with the stored content-type. 404 no image / 403 not your load.
- **Honest content-type** — the real MIME type flows client→server (`ConditionPhotoIn.content_type`, `addConditionPhoto(..., file.type)`), so a served PNG says `image/png`, not a default.

### UI (EvidenceSurface)
- `api.js` `fetchEvidencePhoto(stopId, artifactId)` — **authenticated fetch → blob → object URL** (bearer auth can't ride a bare `<img src>`); object URLs revoked on unmount.
- `EvidenceSurface` renders a real `<img>` thumbnail (`object-fit: cover`, 44 dp) when `has_image`, gracefully falling back to the Camera icon while loading / if unavailable. `evidence.images_note` copy updated (images are served now, not "at activation"), six locales.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 337 passed** (was 335).
- UI: **vitest 112 passed** (was 111) · `vite build` green.
- **Live-smoked end-to-end**: login as dev-driver → create load → arrive → capture a condition photo with real PNG bytes → `GET /evidence` shows `has_image:true` + `artifact_id` → `GET /evidence/photo/{id}` returns the **exact bytes** with `content-type: image/png`; a second driver gets 403.

## 2. Decisions made (append to Decision Log)

196. **Evidence photo bytes live in F6 object storage; F4 stays storage-agnostic.** F4 records the hash + `storage_key` (its existing seam); the M5 caller (which already imports F6) persists the bytes and passes the key. Keeps the evidence engine free of a storage dependency and reuses F6 as the platform's object-storage owner. Namespaced `evidence/{log_id}/{uuid}` (separate from wallet documents).
197. **Storage never blocks capture.** A failed put leaves `storage_key` null (image unavailable) but the artifact + hash still record — the tamper-evident chain is the invariant, the thumbnail is a convenience. MinIO wiring falls back to in-memory if unreachable; tests keep the in-memory default.
198. **No new F13 flag for this seam.** Image serving completes an already-live M5/F4 capability (consistent with how the Evidence view itself shipped, `966ac3e`), rather than activating a new module. Owner used best judgement → proceed without a flag.
199. **Thumbnails are served, not embedded as data.** Bearer-auth blob fetch → object URL keeps the endpoint owner-gated. (Presigned MinIO URLs were the alternative; deferred — blob fetch needs no bucket-policy/expiry management.)

## 3. Exact next task — pick the next activation seam

Remaining activation seams (from HANDOFF-059 §3, minus FMCSA + F6 images):
- **Stripe/Connect** (M6 payouts) · **fuel partner** (M7) · **collections+legal** (M3/M4) · **IFTA** (M9).
- **Embeddings + voice** seams (real `EMBED_DIM` migration + pgvector ANN index for M2; a speech provider for M11).
- **Brand name** (PRD §17.6) · **F15 locale review** by native speakers (the new `authority.*` + updated `evidence.images_note` strings included).

**Recommendation:** owner names the next seam. Stripe (real payouts) or brand name remain highest-leverage.

**F6 follow-ons (noted, not built):** (a) **document previews** — wallet docs already have `f06.get_document_bytes`; a `GET /.../document/{id}` mirror + `<img>`/PDF preview in the Evidence "documents on file" list is a small next increment. (b) **Embedding the verified thumbnail into the exported evidence-pack PDF** (F4 render seam). (c) presigned URLs if direct-from-MinIO serving is ever wanted.

## 4. Blockers / owner questions

No code blockers — stack green, all suites pass. Image serving runs on MinIO in dev today (no external key needed). Open activation inputs (owner decisions): Stripe/Connect · fuel partner · collections+legal · IFTA · brand name · F15 locale review.

## 5. Port / env changes

New setting **`minio_bucket`** (default `longhaul`; reuses the existing MinIO endpoint/creds). **No migration** — `EvidenceArtifact.storage_key`/`exif` already existed. LOCKED ports unchanged (5438/8008/9008). MinIO on 9018/9019 (already in compose). The API `lifespan` wires MinIO on startup; a restart/recreate picks it up.

## 6. How to run (all Docker) — stack is UP

```
make up        # preflight + full stack (Mapbox + real Claude live via infra/.env)
make ci        # preflight + lint + test (CI parity)
```
Suite: **pytest 337 · vitest 112 · 29 contracts · ruff clean · vite build OK.** Evidence photos persist to MinIO and serve as real thumbnails at `/load/{stop}/evidence/photo/{artifact_id}` (owner-gated).

## 7. Build progress

**F1–F15 + M1–M12 complete; M1 on Mapbox (live); F9 real Claude (live); FMCSA authority verification (live); F6 evidence-image serving (live on MinIO).** This session: lifespan MinIO wiring, byte-persistence on capture (resilient), the owner-gated photo-serving endpoint, honest content-type, and real thumbnails in the Evidence view. Remaining: activation inputs §3.

## 8. Commits this session (local only, never pushed)

Since `1e2ca6f` (FMCSA verification): the F6 image-serving seam (MinIO lifespan wiring + M5 byte-persistence + `f04.get_artifact`/`stop_evidence` fields + `/evidence/photo/{id}` endpoint + content-type passthrough + EvidenceSurface thumbnails + tests) → this handoff. See `git log` on `main`. Never pushed.

*— End of session. Evidence photos are now real, owner-gated thumbnails backed by object storage; capture stays resilient to storage failure. Next: owner names the next seam (Stripe / brand name).*
