# HANDOFF-051 — Gate /dev to development builds (dev tool never ships)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, full authz posture, dev directory dev-only, offline fully a mode, admin console operational, M6 self-serve, two F13-config knobs live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–050 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-050)

Closes the pre-deploy footgun flagged since HANDOFF-045: the **`/dev` directory** — a public page with one-click sign-in shortcuts and dev credentials — could have shipped to production. It's now **development-only**, excluded from production builds at the bundler level.

### UI — `router.js` / `AuthSurface`
- The `/dev` route is built from `import.meta.env.DEV`: `const devRoutes = import.meta.env.DEV ? [ { path: "/dev", component: () => import(...DevIndexSurface...) } ] : []`. Vite replaces `import.meta.env.DEV` with `false` in a production build, so the route **and its lazily-imported component chunk are tree-shaken out** — the dev tool and its `dev-driver`/admin credentials are absent from the prod bundle.
- The "Explore all screens (dev directory)" link on the login screen is `v-if="isDev"` (`import.meta.env.DEV`), so it never renders in production.

### Verified this session (in compose)
- UI: **vitest 101 passed** (+1: asserts the `/dev` route is registered when `import.meta.env.DEV` — true under vitest; documents the mechanism) · `vite build` clean.
- **Prod-bundle audit:** after `vite build`, `dist/` has **0** matches for `Sign in as driver` and `dev-driver@longhaul.local` (DevIndexSurface fully excluded). The only remnant is AuthSurface's dead link *text* "Explore all screens (dev directory)" — a harmless string in the compiled template (the button is `v-if`-hidden and points to a route that doesn't exist in prod; no creds, no working link).
- Backend: **unchanged** — pytest **305**, 29 contracts, ruff clean.

## 2. Decisions made (append to Decision Log)

176. **Dev-only surfaces are excluded at build time via `import.meta.env.DEV`, not gated at runtime.** A runtime flag would still ship the component (and its credential hints) in the bundle. Building the route conditionally with a lazy import means Vite tree-shakes the whole DevIndexSurface chunk out of production — the safest posture (the code isn't there to reach). The same pattern fits any future dev-only tool.
177. **A harmless dead string is acceptable; live dev affordances are not.** The compiled AuthSurface template keeps the link's text literal even though `v-if="isDev"` prevents it rendering in prod. That's a static string with no credentials and no reachable target — left as-is rather than contorting the template. The bar is "no dev tooling or secrets are reachable/executable in production," which is met.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input) — security + dev-safety now complete; what's left is polish/features:
- **More F13-config seams** — M3 free-time/rate default, M10 `REDEEM_CENTS_PER_POINT`/`RATE_LIMIT_PER_DAY` (the HANDOFF-041 pattern). **Recommended next**.
- Small polish: approved-review snippets on the public scorecard; fold moderation decisions into the admin audit feed.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), brand name.

**Recommendation:** the **M3 free-time/rate F13-config seam** — the third config exemplar and the one closest to the money (detention terms), or the public-scorecard review snippets (enriches the only outward-facing surface). Both low-risk.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · locale native review (F15, gate green at **261 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged. (`/dev` still serves under `make up` — the dev server runs with `import.meta.env.DEV === true`.)

## 6. How to run (all Docker) — stack is UP

`/dev` works in development (`make up` → http://localhost:9008/dev). A production `vite build` omits it entirely — verified by the dist audit above.
Suite: **pytest 305 · vitest 101 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; full authz posture; dev tooling excluded from prod builds; integration e2e green; offline fully a mode; five product surfaces + a dev-only directory; admin console operational; M6 self-serve; two F13-config knobs live.** Hardening to date: gate /dev (051), fleet membership gate (050), M3/M5 authz sweep (049), load authz gate (048), end-load (047), GET /load/active (046), dev directory + counterparty names (045), M10 earn config (044), audit-log view (043), owner spot CRUD (042), config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`70b8f52` fleet membership gate → this: gate /dev to dev builds (+ this handoff). **116 commits** on `main`, never pushed.

*— End of session. Next: M3 free-time config seam or public-scorecard review snippets. Activation seams await owner/BD inputs (§4).*
