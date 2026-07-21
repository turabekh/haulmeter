# HANDOFF-058 — Browser-testing hardening pass (activation live: Mapbox + real Claude)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete. **Mapbox live, F9 real Claude live** (owner added both keys). A full owner-driven browser walkthrough closed a class of "backend works but I can't see it" gaps across the map, booking, fuel, the detention Meter, claims, incidents, onboarding, language, and evidence. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–057.

---

## 1. What now exists and passes (delta since HANDOFF-057)

HANDOFF-057 wired the F9 real-provider adapter (key-gated). This session the owner **added both the Mapbox and Anthropic keys** and then ran a **hands-on browser walkthrough**, clicking every completed feature and reporting each gap. The recurring root cause: features had working backends but **UI stubs or unsurfaced state** ("I did X but nothing happened / I can't see it"). Each was fixed end-to-end with tests. Both **Mapbox and F9 are verified live end-to-end.**

### Map & discovery (M1/M6/M7)
- **Parking report flow wired** (`309ee11`) — `submitReport` was a UI stub; now posts and refreshes the overlay (M1-FR7).
- **Map bottom-sheet polish** — deduped facility name (`7ad4d1c`); **meaningful pin icons** (not rectangles), fully-booked state, clickable sleep results (`98449f1`).
- **Book/Fuel badges** enriched at the API layer (M1 can't import M6/M7, so `/map` overlay composes their `.public`) (`6c8c846`).
- **Booking honesty** (`06dda31`, `98449f1`) — real result surfaced, **409 on double-book**, availability-aware `bookable_summary`, map reflects a booked/full spot.
- **Fuel ≠ parking** (`f769b2d`) — fuel stations show "Fuel here", not a parking "Report status".

### The Meter / detention / claims (M3)
- **Sample vs live** (`a61ec1d`) — the no-load Meter is labeled a **Sample**, not a fake live detention tick.
- **Claim flow fixed** (`f465a7e`, `857f192`) — the Meter **freezes on file** and **stays frozen across tab switches** because `filed` is now **derived from the server** (`claim.state`), not client state. Notice sending gives real feedback and is **tracked** (`start_notice_sent_at`, migration **0024**).
- **Claim detail view** (`360026f`) — `GET /load/{stop}/claim` + `ClaimSurface`: the money, terms, mode, and the GPS-verified evidence chain, in friendly language. Incident filing now confirms (toast).

### Onboarding, locale, evidence (F1/F15/F4/M5)
- **Operating authority at signup** (`019288a`) — `RegisterIn.authority` (own_mc/leased/company) → `upsert_driver_profile(authority_type=…)`; drives claim **mode** (invoice vs evidence_only). AuthSurface 3-option picker.
- **Language selection live** (`1a84d05`) — persistent More-tab picker (native names), localStorage `longhaul.locale`, device-language detection.
- **Condition photos visible** (`96e14f9`) — `m5.condition_photo_count` on the Meter; the Load tab Evidence "Photos" line reflects real captures.
- **Consolidated Evidence view** (`966ac3e`, this session's last task) — `f04.stop_evidence` aggregates **every** F4 log tied to a stop (arrival + condition captures) into one integrity-checked view; `GET /load/{stop}/evidence` composes it with the facility + M5 wallet docs (owner-gated). `EvidenceSurface` shows photos (guided prompt, capture time, verified hash), the GPS timeline, and documents, under one chain badge. "View all evidence →" affordance on the Load tab.

### Demo seed
- **Dallas facility cluster** (`3048008`) + **dev-driver = owner-operator** (`dc0c0b2`) so money/claim flows show real numbers in the browser.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 321 passed** (was 312).
- UI: **vitest 109 passed** (was 101) · `vite build` green.
- **Mapbox live** (real tiles, GPS geolocate, day/night `lightPreset`) and **F9 real Claude live** (owner's key in `infra/.env`) — both smoke-tested end-to-end. Evidence endpoint live-smoked (2 guided photos → aggregated, chain valid).

## 2. Decisions made (append to Decision Log)

190. **Owner-operator vs employee = `authority_type` declared at onboarding.** own_mc/leased invoice (money owed to the driver); company → evidence_only (exported to the carrier). Self-declared today; **FMCSA MC#/DOT verification is a future seam** (§4).
191. **`filed` is server-derived, never client state.** The Meter freeze reads `claim.state != "open"`; it survives navigation and fresh devices because the truth lives on the claim. Same principle applied to `notice_sent` (`start_notice_sent_at`) and `photos_captured` (`condition_photo_count`).
192. **Evidence is aggregated per stop, not per log.** `f04.stop_evidence` unions every evidence log tied to a stop into one chronological, chain-verified view — the driver's single "what have I got for this load". Photo images themselves remain an F6 serving seam (each entry is a verified, labeled row, never a fake thumbnail).

## 3. Exact next task — pick the next activation seam

Core product is feature-complete and hardened through a real browser pass. Remaining work is **activation inputs**, each its own seam:
- **FMCSA verification** (MC#/DOT lookup) to back the self-declared authority (Decision 190).
- **Real photo/document image serving** from F6 (thumbnails in the Evidence view).
- **Stripe/Connect** (M6 payouts) · **fuel partner** (M7) · **collections+legal** (M3/M4) · **IFTA** (M9).
- **Embeddings + voice** seams (Voyage/OpenAI embeddings for M2 semantic search — needs a real `EMBED_DIM` migration + pgvector ANN index; a speech provider for M11 STT/TTS).
- **Brand name** · **F15 locale review** by native speakers.

**Recommendation:** owner names the next seam. Stripe (turns on real payouts) or brand name are the highest-leverage; FMCSA verification is the cleanest next credibility win for the detention product.

## 4. Blockers / owner questions

No code blockers — stack is green and both live keys are in. Open **activation inputs** (owner decisions): Stripe/Connect · fuel partner · collections+legal · IFTA · FMCSA verification · F6 image serving · brand name · F15 locale review. **Mapbox: DONE. F9 real AI: DONE.**

## 5. Port / env changes

None this session. `infra/.env` already carries `MAPBOX_TOKEN` and `ANTHROPIC_API_KEY` (both gitignored; `.env.example` has placeholders). Migration **0024** (`m03.detention_claim.start_notice_sent_at`) is applied. LOCKED ports unchanged (5438/8008/9008).

## 6. How to run (all Docker) — stack is UP

```
make up        # preflight + full stack (Mapbox + real Claude live via infra/.env)
make ci        # preflight + lint + test (CI parity)
```
Suite: **pytest 321 · vitest 109 · 29 contracts · ruff clean · vite build OK.** After editing `infra/.env`, recreate (not just restart) the api container to reload env_file: `docker compose -f infra/docker-compose.yml up -d api`.

## 7. Build progress

**F1–F15 + M1–M12 complete; M1 on Mapbox (live); F9 real Claude (live); full authz posture; admin console complete; M6 self-serve; three F13-config knobs live.** This session: a browser-testing hardening pass — report flow, booking honesty, fuel/parking split, Meter freeze + notice tracking, claim detail, incident feedback, authority onboarding, language selection, photo visibility, and the consolidated Evidence view. Remaining: activation inputs §4.

## 8. Commits this session (local only, never pushed)

Since `c7cc996` (F9 provider): `3048008` seed · `7ad4d1c` sheet dedupe · `309ee11` report flow · `6c8c846` map badges/hermetic · `06dda31` booking result · `98449f1` map polish · `f769b2d` fuel copy · `a61ec1d` Meter Sample · `f465a7e` claim freeze · `857f192` server-derived filed · `360026f` claim detail + incident · `dc0c0b2` demo owner-op · `019288a` authority onboarding · `1a84d05` language picker · `96e14f9` photo visibility · `966ac3e` Evidence view → this handoff. **138 commits** on `main`, never pushed.

*— End of session. Both live keys in, full browser pass done, evidence loop closed end-to-end. Next: owner names the activation seam (Stripe / brand name / FMCSA verification).*
