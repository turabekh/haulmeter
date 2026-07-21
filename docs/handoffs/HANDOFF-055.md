# HANDOFF-055 — M1 live Mapbox tiles (first activation seam flipped on)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, full authz posture, dev tooling excluded from prod, **M1 map now renders live Mapbox tiles**, admin console complete, M6 self-serve, three F13-config knobs live. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–054 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-054)

The **first activation seam is live**: the M1 map renders **real Mapbox GL tiles** (owner supplied a public `pk.*` token). Everything around the map was already live (pins from the real overlay API); this swaps the "tiles pending" placeholder for a styled basemap.

### Owner input received
- The owner created a Mapbox account + **public `pk.*` token** and placed it in `infra/.env` as `MAPBOX_TOKEN=…` (gitignored — never in the repo). Verified valid against the Mapbox API: `dark-v11`, `light-v11`, and a vector-tile fetch all returned **200**.

### Plumbing
- **`infra/docker-compose.yml`** ui service: `environment: VITE_MAPBOX_TOKEN: ${MAPBOX_TOKEN:-}` — Vite exposes the token to the app; empty → placeholder fallback.
- **`infra/.env.example`**: `MAPBOX_TOKEN=` placeholder + comment (public token, URL-restricted, real value in `.env` only).
- **`ui/package.json`**: `mapbox-gl@^3` added (installed; `package-lock.json` updated).

### UI — `MapCanvas.vue` (token-gated)
- When `import.meta.env.VITE_MAPBOX_TOKEN` is set: **dynamically imports** `mapbox-gl` (+ its CSS), creates a GL map with a **desaturated built-in style — `dark-v11` at night (19:00–07:00), `light-v11` by day** (§11.6, so roads/labels stay muted and semantic pins are the only saturated ink), fits to the pins, and **re-projects the pins onto the moving map** (`map.project` on every `move`). When absent: the existing placeholder + bounds-normalized pin layout (unchanged). GL init is wrapped in try/catch → falls back to the placeholder if WebGL is unavailable/offline.
- Because the import is dynamic **and** gated on a compile-time-constant token: with a token, `mapbox-gl` is a **lazy chunk** (fetched only on the map screen); with **no** token, Rollup **dead-code-eliminates it entirely** — the no-token build never ships the ~200 KB library.

### Verified this session (in compose)
- UI: **vitest 101 passed** (test env has no token → fallback path, existing MapSurface tests unchanged) · `vite build` clean (main bundle **261 KB**; `mapbox-gl` split into its own **519 KB gzip lazy chunk** only when the token is present).
- Backend: **unchanged** — pytest **309**, 29 contracts, ruff clean.
- **Live checks:** ui container has `VITE_MAPBOX_TOKEN` set (`pk.…`); dev server up (200), no startup errors; the token authorizes both basemap styles + tiles (200/200/200).

## 2. Decisions made (append to Decision Log)

184. **M1 basemap = built-in Mapbox styles, chosen by time of day; engine = Mapbox GL JS.** Owner picked built-in styles (swappable to a custom Studio style later via one URL) and a real interactive vector map over static raster. Night/day is a local-clock switch (dark-v11 / light-v11) — a truck-relevant signal, refinable to a manual/twilight toggle later. Pins remain DOM overlays re-projected onto the GL map, so §11.2 (44 dp hit areas, shape/fill/hollow semantics) is unchanged.
185. **The Mapbox token is a build/runtime env var (`VITE_MAPBOX_TOKEN` from `MAPBOX_TOKEN` in `infra/.env`), not a repo constant.** A public `pk.*` token ships in the client bundle by design (Mapbox's model) — the protection is URL-restriction on the token, not secrecy — but it still stays out of the repo via the gitignored `.env`. The token-gated dynamic import means the library and token are absent from any build made without the token.

## 3. Exact next task — continue the backlog

Now that one seam is proven end-to-end, the others follow the same "owner provides input → I wire it" shape:
- **Remaining activation seams** (each needs an owner/BD input): Stripe/Connect (M6 charge + owner payout), F9 model provider (M9/M11 real AI), fuel partner (M7), collections+legal (M3/M4), IFTA data (M9), brand name, F15 locale native review.
- **Map follow-ups** (buildable now, incremental): center on the driver's live GPS (geolocation), DRIVING corridor styling on the GL map, a manual day/night toggle, offline tile behavior (F12).
- Optional config seams: M2 `REVIEW_POINTS`, M10 redeem/rate-limit.

**Activation-input checklist for the owner** (to flip on more seams): **Stripe** — publishable + secret keys + Connect settings; **F9** — model provider API key + chosen model; **M7** — fuel-network partner API/credentials; **M3/M4** — collections partner + legal sign-off (also satisfies the F13 gates); **IFTA** — data source; **brand name** — final name for copy/emails/PDFs.

**Recommendation:** ask the owner which seam to activate next (Stripe is the biggest revenue unlock; F9 turns M9/M11 from stubs to real AI), or knock out a **map follow-up** (driver-GPS centering) while inputs are gathered.

## 4. Blockers / owner questions

Remaining **activation inputs**: Stripe/Connect keys · F9 provider key+model · fuel partner (M7) · collections+legal (M3/M4) · IFTA data (M9) · brand name · F15 locale native review. **Mapbox: DONE** (token supplied + verified).

## 5. Port / env changes

**`infra/.env`** gains `MAPBOX_TOKEN` (owner-supplied, gitignored); **`infra/.env.example`** gains the placeholder. Compose ui service passes `VITE_MAPBOX_TOKEN`. LOCKED ports untouched. A fresh `docker compose build ui` picks up `mapbox-gl` from `package.json`; the running container had it installed live + was recreated for the env.

## 6. How to run (all Docker) — stack is UP

**See live tiles:** hard-reload http://localhost:9008 → sign in (via `/dev`) → **Map** tab. Real Mapbox basemap (dark at night / light by day) under your semantic pins. No token in `.env` → the placeholder returns automatically.
Suite: **pytest 309 · vitest 101 · 29 contracts · ruff clean**; `vite build` clean (mapbox-gl lazy-chunked), migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; M1 map renders live Mapbox tiles (first activation seam ON); full authz posture; dev tooling excluded from prod; admin console complete; M6 self-serve; three F13-config knobs live.** Hardening/activation to date: Mapbox tiles (055), moderation in audit (054), scorecard snippets (053), M3 terms config (052), gate /dev (051), fleet membership gate (050), M3/M5 authz sweep (049), load authz gate (048), end-load (047), GET /load/active (046), dev directory + counterparty names (045), M10 earn config (044), audit-log view (043), owner spot CRUD (042), config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining: activation seams §3.

## 8. Commits this session (local only, never pushed)

`1888348` moderation in audit → this: M1 live Mapbox tiles (+ this handoff). **120 commits** on `main`, never pushed.

*— End of session. Mapbox seam flipped on + verified. Next: pick the next activation seam (Stripe / F9) with owner inputs, or a map follow-up (driver-GPS centering). §3 has the owner input checklist.*
