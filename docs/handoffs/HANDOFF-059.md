# HANDOFF-059 — FMCSA operating-authority verification (activation seam #1)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 22 July 2026 · **State:** F1–F15 + M1–M12 complete. Mapbox live, F9 real Claude live. **New this session: the first post-completion activation seam — FMCSA MC#/DOT verification — built end-to-end behind its own F13 flag, key-gated, tests alongside.** Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–058.

---

## 1. What now exists and passes (delta since HANDOFF-058)

HANDOFF-058 closed the browser-testing hardening pass and flagged the next task as an **owner-chosen activation seam** (§3/§4). The owner chose **FMCSA verification** (the cleanest credibility win for the detention product, Decision 190). Built this session, end-to-end:

### The verification seam (F1 Identity)
- **Key-gated FMCSA adapter** (`f01_identity/domain/verifier.py`) — mirrors the F9 model-provider shape exactly: `AuthorityVerifier` Protocol + `VerificationResult`; `FakeAuthorityVerifier` (deterministic, used in every test and whenever no key is set); `StubAuthorityVerifier` (fails loud); `FmcsaVerifier` (real QCMobile REST, `webKey`-gated, `httpx` in a monkeypatch-able module fn); `resolve_verifier()` returns the live adapter when `FMCSA_WEBKEY` is present, else the Fake.
- **Config + env** — new `fmcsa_webkey` setting; `.env.example` placeholder + comment. Free key at mobile.fmcsa.dot.gov. Real key lives in `infra/.env` only.
- **Persistence** — migration **0025** adds `f01.driver_profile.mc_number / dot_number / legal_name / authority_verify_status (verify_status enum: unverified|verified|failed) / authority_verified_at`. All nullable/defaulted — nothing regresses.
- **Service** — `verify_authority(db, account, mc, dot, verifier=None)` runs the (key-gated) lookup and records the outcome; `register_authority_verification(db)` registers the F13 flag idempotently (mirrors module `register_*`). `can_invoice` is **unchanged** (see Decision 193).
- **API** — `POST /auth/verify-authority` (bearer-auth, **flag-gated** → 403 when off, 422 with no identifier) and `GET /auth/me` (authority + verification state + `verification_enabled`). Both compose F1 + F13 publics in the `app.api` layer, keeping f01's domain free of f13.

### UI (design-prd compliant — no new tokens/components)
- **More tab** (`MoreSurface`) — an "Operating authority" section that appears **only when the F13 flag is on**; §202 form (56 dp input, label above, one primary CTA), unblaming inline error (§12.4); verified state shown as **plain text + Check** (§10 — no badges on the More tab). Six-locale copy (en/es/pa/ru/uz/so).
- **Verified §200 status pill** — the sanctioned colored chip surfaces where credibility is **consumed**: `MoneySurface` (the driver's receivables) and `ClaimSurface` (the invoice hero, `invoice` mode only). "MC# ####### · Verified", `ledger-500`.
- `api.js` — `fetchMe()`, `verifyAuthority()`.

### Demo seed
- `seed_demo` now enables the flag and **pre-verifies the dev-driver** (MC# 123456 via the Fake verifier) so the verified pill + More-tab state show in the browser immediately.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 335 passed** (was 321).
- UI: **vitest 111 passed** (was 109) · `vite build` green.
- **Live-smoked**: migration 0025 applied to the dev DB; login as dev-driver → `GET /auth/me` returns `verified:true, mc_number 123456, legal_name "CARRIER 123456 LLC"`; a fresh `POST /auth/verify-authority` verifies live (Fake verifier, no webKey needed). Flag-off path returns 403.

## 2. Decisions made (append to Decision Log)

193. **Authority verification STRENGTHENS credibility; it never GATES the right to invoice.** `can_invoice` stays purely self-declared (own_mc/leased → invoice) so onboarding stays under 60 s and $0 (PRD §7.1, Decision 190). A verified MC# + legal name simply ride along on the claim/invoice as a trust mark. Owner-approved. A company driver who verifies stays `evidence_only` (test-locked).
194. **The FMCSA adapter is a key-gated seam identical in shape to F9's model provider.** Fake everywhere by default (deterministic, no network, no cost), live only when `FMCSA_WEBKEY` is set. `resolve_verifier()` is the single switch. No new architectural pattern — the established activation shape.
195. **Verified state surfaces by consumption context, honoring design-prd §10 vs §200.** Input/action + plain-text verified state on the More tab (§10, no badges); the colored status pill (§200) only on Money/Claim where a broker-facing credibility mark belongs. No new token or component invented — composition per §22.

## 3. Exact next task — pick the next activation seam

The seam list from HANDOFF-058 §3 stands, minus FMCSA (now done):
- **Real photo/document image serving** from F6 (thumbnails in the Evidence view).
- **Stripe/Connect** (M6 payouts) · **fuel partner** (M7) · **collections+legal** (M3/M4) · **IFTA** (M9).
- **Embeddings + voice** seams (real `EMBED_DIM` migration + pgvector ANN index for M2; a speech provider for M11).
- **Brand name** (PRD §17.6) · **F15 locale review** by native speakers (the 10 new `authority.*` strings included).

**Recommendation:** owner names the next seam. Stripe (real payouts) or brand name remain the highest-leverage; F6 image serving is the cleanest self-contained follow-on and would make the just-built Evidence + verified-authority story fully tangible.

**Deeper-verification follow-ons (noted, not blocking):** the verified MC# is currently surfaced from `/auth/me` on the client; embedding the verified legal name directly into the generated claim/invoice PDF (F4 render seam) and handling FMCSA multi-record / reinstated-authority edge cases are the natural next increments when a real `FMCSA_WEBKEY` is added.

## 4. Blockers / owner questions

No code blockers — stack green, all suites pass. **FMCSA verification runs today on the deterministic Fake**; to go live, drop a real `FMCSA_WEBKEY` into `infra/.env` and recreate the api container (below). Open activation inputs (owner decisions): Stripe/Connect · fuel partner · collections+legal · IFTA · F6 image serving · brand name · F15 locale review.

## 5. Port / env changes

New env key **`FMCSA_WEBKEY`** (empty in `.env.example`; real value in `infra/.env` only, gitignored). Migration **0025** (`f01` authority-verification columns + `verify_status` enum) applied to the dev DB. LOCKED ports unchanged (5438/8008/9008). After editing `infra/.env`, recreate (not just restart) api to reload env_file: `docker compose -f infra/docker-compose.yml up -d api`.

## 6. How to run (all Docker) — stack is UP

```
make up        # preflight + full stack (Mapbox + real Claude live via infra/.env)
make ci        # preflight + lint + test (CI parity)
```
Suite: **pytest 335 · vitest 111 · 29 contracts · ruff clean · vite build OK.**
Live FMCSA verification (optional): set `FMCSA_WEBKEY` in `infra/.env`, then `docker compose -f infra/docker-compose.yml up -d api`.

## 7. Build progress

**F1–F15 + M1–M12 complete; M1 on Mapbox (live); F9 real Claude (live); first activation seam — FMCSA authority verification — live behind its own F13 flag (Fake by default, real on webKey).** This session: the verification adapter, migration 0025, `/auth/verify-authority` + `/auth/me`, More-tab verify flow, and the verified §200 pill on Money/Claim. Remaining: activation inputs §3.

## 8. Commits this session (local only, never pushed)

Since `a702ea0` (HANDOFF-058): the FMCSA authority-verification seam (adapter + migration 0025 + endpoints + UI + six-locale copy + tests) → this handoff. See `git log` on `main`. Never pushed.

*— End of session. First activation seam shipped end-to-end, flag-gated and key-gated, all suites green. Next: owner names the next seam (Stripe / brand name / F6 images).*
