# HANDOFF-056 — Map: Standard style + driver-GPS centering

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, M1 map live on Mapbox with GPS centering, full authz posture, dev tooling excluded from prod, admin console complete, three F13-config knobs live. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–055 (hardening/activation).

---

## 1. What now exists and passes (delta since HANDOFF-055)

Two map upgrades the owner asked for: a **better-looking basemap** and **driver-GPS centering**.

### UI — `MapCanvas.vue`
- **Basemap → Mapbox Standard** (`mapbox://styles/mapbox/standard`, GL v3): the modern vector style with dynamic lighting, replacing the flat `dark-v11`/`light-v11`. Day/night via `setConfigProperty("basemap", "lightPreset", …)` (night 19:00–07:00). Owner-directed swap for a nicer look — richer than the §11.6 "desaturated" ideal, but the saturated semantic pins ride on top as DOM overlays so they stay the focal ink; swappable to a custom desaturated Studio style later via one URL.
- **Driver-GPS centering**: adds Mapbox `GeolocateControl` (blue dot + heading + a re-center button, bottom-right), **auto-triggered on load** so the map opens on the driver (§10.1). Emits a `located` event with the driver's coords. Falls back to framing the pins if geolocation is denied/unavailable (wrapped in try/catch). Once located, the map stays on the driver (pin refreshes reproject but no longer refit the bounds).

### UI — `MapSurface.vue`
- New `geo` center (default Dallas until located). On `@located`, it updates `geo` and **refetches the overlay + handoffs around the driver** — so pins follow the driver instead of a fixed point. `fetchOverlay`/`fetchNearbyHandoffs` now use `geo`, not the hardcoded `32.78,-96.8`.

### Verified this session (in compose)
- UI: **vitest 101 passed** (test env has no token → GL/geolocation never run → MapSurface uses the default center, existing tests unchanged) · `vite build` clean (main bundle **262 KB**; `mapbox-gl` still a lazy chunk).
- Backend: **unchanged** — pytest **309**, 29 contracts, ruff clean.
- **Live checks:** the token authorizes the Standard style (200); `GeolocateControl` present in installed mapbox-gl **3.26.0**; dev server up (200), HMR reloaded the surfaces.

## 2. Decisions made (append to Decision Log)

186. **Basemap is Mapbox Standard with a day/night lightPreset — an owner-directed look over the §11.6 "desaturated" default.** The owner found the dark/light-v11 basemap unappealing and chose a richer style. §11.6's intent (semantic pins are the salient element) is preserved structurally: pins are DOM overlays above the GL canvas, always on top, with shape/fill/hollow semantics intact. A custom desaturated Studio style can replace Standard later by swapping one URL — the plumbing is unchanged.
187. **The map centers on the driver's live GPS, and the overlay follows it.** `GeolocateControl` (idiomatic blue dot + re-center) auto-triggers on load; its `geolocate` event drives `MapSurface` to refetch pins/handoffs around the driver. This is the single geolocation source (no double prompts). Denied/unavailable geolocation degrades gracefully to pin-framed. In dev with no seeded facilities near the tester, the map correctly shows their location with sparse/absent pins — honest, not broken.

## 3. Exact next task — continue the backlog

- **Map follow-ups** (buildable now): DRIVING-mode corridor styling on the GL map (§11.4), a manual day/night toggle, offline tile behavior (F12), cluster/perf pass for dense pins.
- **Remaining activation seams** (owner input each): Stripe/Connect (M6), F9 model provider (M9/M11), fuel partner (M7), collections+legal (M3/M4), IFTA data (M9), brand name, F15 locale review.
- Optional config seams: M2 `REVIEW_POINTS`, M10 redeem/rate-limit.

**Activation-input checklist** (unchanged from HANDOFF-055 §3): Stripe keys + Connect; F9 provider key + model; M7 fuel partner creds; M3/M4 collections partner + legal sign-off; IFTA data source; brand name.

**Recommendation:** pick the next **activation seam** (Stripe = revenue; F9 = real AI in M9/M11) and provide its input, or I continue with **map follow-ups** (DRIVING corridor styling / day-night toggle) — all buildable now.

## 4. Blockers / owner questions

Remaining **activation inputs**: Stripe/Connect keys · F9 provider key+model · fuel partner (M7) · collections+legal (M3/M4) · IFTA data (M9) · brand name · F15 locale native review. **Mapbox: DONE.**

## 5. Port / env changes

**None** beyond HANDOFF-055 (`MAPBOX_TOKEN` already in `infra/.env` / example). LOCKED ports untouched.

## 6. How to run (all Docker) — stack is UP

**See it:** hard-reload http://localhost:9008 → sign in (`/dev`) → **Map**. Modern Standard basemap (day/night by clock); the browser prompts for location, then the map centers on you (blue dot) and pins refetch around you. Deny location → it frames the pins. No token in `.env` → placeholder returns.
Suite: **pytest 309 · vitest 101 · 29 contracts · ruff clean**; `vite build` clean (mapbox-gl lazy-chunked).

## 7. Build progress

**F1–F15 + M1–M12: complete; M1 map on Mapbox Standard with driver-GPS centering; every surface live; full authz posture; dev tooling excluded from prod; admin console complete; M6 self-serve; three F13-config knobs live.** Recent: map GPS + style (056), Mapbox tiles (055), moderation in audit (054), scorecard snippets (053), M3 terms config (052), gate /dev (051), fleet membership gate (050), M3/M5 authz sweep (049), load authz gate (048), end-load (047), GET /load/active (046), dev directory + counterparty names (045), M10 earn config (044), audit-log view (043), owner spot CRUD (042), config consumer (041) … (M1–M12 complete at 025). Remaining: activation seams + map follow-ups §3.

## 8. Commits this session (local only, never pushed)

`2c97c53` Mapbox tiles → this: map Standard style + GPS centering (+ this handoff). **121 commits** on `main`, never pushed.

*— End of session. Map looks modern and follows the driver. Next: an activation seam (Stripe/F9) with owner input, or map follow-ups (DRIVING corridor, day/night toggle).*
