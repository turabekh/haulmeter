# HANDOFF-063 — Brand name decided: "Haulmeter" (PRD §17.6 resolved)

**Project:** Haulmeter (was internal placeholder "LONGHAUL") — Consolidated Trucker Platform
**Date:** 22 July 2026 · **State:** F1–F15 + M1–M12 complete. Live: Mapbox · F9 Claude · FMCSA verification · F6 image serving · F9 Voyage embeddings · M11 on-device voice. **New this session: the product has a name — Haulmeter — wired in from a single source of truth; PRD §17.6 resolved.** Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–062.

---

## 1. What now exists and passes (delta since HANDOFF-062)

Owner chose the brand name **Haulmeter** — trucking-native ("haul") + the product's sole signature element ("meter" / The Meter). This resolves the last of the PRD §17 open questions that was purely a decision (brand name); trademark + domain clearance remain the owner's real-world step.

**Scope was tiny (as expected):** the placeholder only leaked into two user-facing spots — the login wordmark and the dev-directory title. Every other `longhaul` in the repo is **internal infra** that deliberately stays: Docker/DB/MinIO creds `longhaul`, `app_name "longhaul-api"`, and critically the **F4 evidence hash namespace `longhaul-evidence:`** (changing that salt would invalidate every existing evidence hash-chain). No PDF/email currently embeds the brand (a future follow-on when those surfaces get branded).

### The rename
- **Single source of truth `ui/src/core/brand.js`** — `export const BRAND = "Haulmeter"`. A proper noun (identical in all locales), so it lives in core, not i18n. Rendered **mixed-case** as a wordmark — never ALL-CAPS (design-prd T-3; the old "LONGHAUL" all-caps is retired).
- **`AuthSurface`** (login wordmark) and **`DevIndexSurface`** (dev title) now read `BRAND`. Any future brand surface imports the same constant → the next rename is a one-line change.
- **Docs:** design-prd **§23** decision entry logged (owner-approved); PRD **§17.6** updated from "open question" to "decided: Haulmeter, trademark/domain clearance remains."

### Verified this session (in compose)
- UI: **vitest 116 passed** (was 115; +1) · `vite build` green. New test asserts `.auth__brand` renders "Haulmeter" and contains no "LONGHAUL" — locks the placeholder out.
- Backend: **untouched** (brand is UI-only) — **pytest 345 · lint-imports 29/29 · ruff clean** carry over.
- §22.3 DoD: mobile-first (unchanged layout), tokens-only (no visual change beyond the wordmark string; T-3 mixed-case now honored), six locales (brand is locale-invariant), a11y (unchanged).

## 2. Decisions made (append to Decision Log)

206. **Product brand name = "Haulmeter."** Owner decision (design-prd §23, PRD §17.6). Trucking-native + names the signature Meter. One source of truth (`ui/src/core/brand.js`); mixed-case wordmark (T-3, no ALL-CAPS). **Internal identifiers are not the brand and stay unchanged** — Docker/DB/MinIO `longhaul`, `longhaul-api`, and the F4 `longhaul-evidence:` hash namespace (immutable — it anchors existing evidence chains). Trademark + domain clearance are the owner's remaining real-world step.

## 3. Exact next task — pick the next activation seam

Remaining seams (from HANDOFF-062 §3, minus brand name):
- **Stripe/Connect** (M6 payouts) · **fuel partner** (M7) · **collections+legal** (M3/M4) · **IFTA** (M9) — all need an external partner/account.
- **F15 locale review** by native speakers — now unblocked by the brand decision; covers all shipped copy incl. the `voice.*`, `authority.*`, and `evidence.images_note` strings and confirms the wordmark reads well in each script.

**Recommendation:** owner names the next seam. **Stripe** turns on real payouts (highest-leverage, needs a Stripe account to begin); **F15 locale review** is the cleanest non-partner task now that the name is set. The remaining technical seams (Stripe, IFTA) all gate on an external account/partner the owner provisions.

**Brand follow-ons (noted, not built):** brand the exported evidence-pack PDF header (§309) and F8 email from-name/templates once those surfaces are designed (they read `BRAND` when added); a favicon/app-icon + wordmark logo asset; app-store identity. All are downstream of trademark/domain clearance.

## 4. Blockers / owner questions

No code blockers — stack green, all suites pass. **Owner's remaining real-world step for the brand:** trademark clearance + domain/handle acquisition for "Haulmeter." Open activation inputs (owner decisions): Stripe/Connect · fuel partner · collections+legal · IFTA · F15 locale review.

## 5. Port / env changes

None. UI-only string change; no new settings, no migration, no backend change. LOCKED ports unchanged (5438/8008/9008). Internal `longhaul` identifiers (Docker/DB/MinIO/hash namespace) intentionally unchanged.

## 6. How to run (all Docker) — stack is UP

```
make up        # preflight + full stack
make ci        # preflight + lint + test (CI parity)
```
Suite: **pytest 345 · vitest 116 · 29 contracts · ruff clean · vite build OK.** The login screen now reads **Haulmeter**.

## 7. Build progress

**F1–F15 + M1–M12 complete; live: Mapbox · F9 Claude · FMCSA verification · F6 image serving · F9 Voyage embeddings · M11 on-device voice. Brand name = Haulmeter (PRD §17.6 resolved).** This session: `core/brand.js` single source of truth, the two user-facing surfaces wired to it, and the §23/§17.6 decision log. Remaining: activation inputs §3.

## 8. Commits this session (local only, never pushed)

Since `5fb0711` (M11 voice): the brand rename (`core/brand.js` + AuthSurface/DevIndex wordmark + test + design-prd §23 / PRD §17.6 log) → this handoff. See `git log` on `main`. Never pushed.

*— End of session. The product is Haulmeter. Internal infra names deliberately untouched; the wordmark has one home. Next: owner names the seam (Stripe / F15 locale review), and clears the trademark/domain.*
