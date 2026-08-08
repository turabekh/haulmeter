<!-- AI-CONTEXT: Map canvas. Live Mapbox GL tiles when VITE_MAPBOX_TOKEN is set
     (M1 activation seam, now wired); otherwise a token-styled placeholder. The
     basemap is a desaturated built-in style — dark at night, light by day
     (design-prd §11.6) — so roads/labels stay muted and the SEMANTIC PINS are the
     only saturated ink. Pins are colored pucks: ICON encodes facility type
     (§11.2 refine), color encodes status, hollow ring = stale (§11.7); 44 dp hit
     areas. When live, pins are
     re-projected onto the moving map; when not, they fall back to a bounds-
     normalized layout. Mapbox GL is dynamically imported so the no-token build
     (and tests) never load the ~200 KB library. -->
<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from "vue";
import { Truck, TreePine, SquareParking, Fuel, Warehouse, Wrench, Circle, UtensilsCrossed, DollarSign, Clock } from "lucide-vue-next";
import {
  statusPresentation,
  isStale,
  placeLabels,
  basemapPreset,
  markerTransform,
} from "../presentation.js";
import { useTheme } from "../theme.js";
import { formatMoney } from "../meter.js";
import { useI18n } from "../i18n.js";
import { readView, rememberView } from "../map-view.js";

const { t } = useI18n();

const props = defineProps({
  pins: { type: Array, default: () => [] },
  // server-side clusters at density (§11.5): { count, lat, lon, status }
  clusters: { type: Array, default: () => [] },
});

// icon encodes facility TYPE (color still encodes status, hollow = stale) — a
// meaningful marker instead of a bare geometric shape (owner-directed §11.2 refine)
const ICONS = {
  truck_stop: Truck,
  rest_area: TreePine,
  parking_property: SquareParking,
  fuel_station: Fuel,
  shipper_receiver: Warehouse,
  // A5: a repair facility drew the bare `Circle` fallback — the one kind on the map a
  // driver looks for while stopped at the roadside was the one with no glyph. The
  // Service chip uses this same Wrench, which is what lets an icon chip mean anything
  // at all (the shared-vocabulary rule PresetChips depends on).
  repair: Wrench,
};
function iconFor(pin) {
  return ICONS[pin.facility_type] || Circle;
}
// `bounds` fires with the current viewport (on load + every pan/zoom) so the surface
// fetches exactly what's in view. `located` fires with the driver's GPS (handoffs +
// the map's own recenter, whose moveend re-emits `bounds`).
const emit = defineEmits(["pinTap", "located", "bounds"]);

const now = Date.now();
const mapEl = ref(null);
const live = ref(false); // true once a GL map is rendering tiles
const positions = ref({}); // facility_id -> { x, y } pixel coords on the live map
const clusterPositions = ref({}); // cluster index -> { x, y }
// AI-CONTEXT: §23 entry 101 fix — a live marker has no position until the map has
// projected it, and until then it sits at the container origin: half a puck off the
// LEFT edge of the screen. The layout harness caught it as a horizontal-overflow
// violation, which is exactly what a driver would have seen as every pin flashing in
// the top-left corner before snapping into place. Markers are not rendered at all
// until the first paint has told them where they belong.
const placed = ref(false);
const zoom = ref(null); // the live map's zoom, for §11.5's label threshold
let map = null;

// AI-CONTEXT: §11.2's badge slots, which were specified and never drawn.
//
// "Badge slots: price (fuel), $ (bookable), clock (dwell risk)". The overlay has been
// serializing `fuel_net` (net, gross, savings) and `bookable` (nightly price) since
// the marketplace modules landed, and this canvas rendered exactly one badge — food.
// So the FUEL PRESET painted a screen of stations each carrying a price and showed
// none of them: comparing two pumps meant tapping both, which is the opposite of what
// a price layer is for.
//
// The three slots are mutually exclusive in practice — a fuel station is never
// bookable and a lot never has a pump price — so they do not compete for the shoulder.
// Food can coexist with either, and keeps the top-right it already had.
//
// The CLOCK slot is deliberately still empty: no dwell-risk badge exists in the
// overlay payload, and rendering a slot with nothing behind it is the fake-confidence
// §11.7 forbids. Logged as debt rather than invented.
function priceLabel(pin) {
  const badge = pin.badges?.find((b) => b.kind === "fuel_net");
  if (!badge) return null;
  // the tilde survives onto the map: a regional estimate must not read as a quote
  return `${badge.indicative ? "~" : ""}${formatMoney(badge.net)}`;
}
function isBookable(pin) {
  return (pin.badges || []).some((b) => b.kind === "bookable");
}
// §11.2's third slot, "clock (dwell risk)" — empty until M2-FR3 gave it a signal
// (§23 entry 87). The server decides whether the mark is warranted (sample floor and
// threshold live with the data); this only draws what it is handed.
function dwellRisk(pin) {
  return (pin.badges || []).find((b) => b.kind === "dwell_risk") ?? null;
}

// the price reaches a screen reader even when §11.5's declutter drops the visible
// label: hiding a figure to keep the map readable is a LAYOUT decision, and applying
// it to assistive text would withhold the fact rather than tidy it.
function pinLabel(pin) {
  const price = priceLabel(pin);
  return price ? `${pin.name} · ${price}` : pin.name;
}

// §11.5's declutter rule lives in `core/presentation.js` (§19) so it can be tested
// as arithmetic rather than asserted through a mounted map that never has a viewport
// in a test runner — which is how it would have shipped unexercised.
const priceLabels = computed(() =>
  placeLabels(
    props.pins.map((pin) => ({
      id: pin.facility_id,
      label: priceLabel(pin),
      ...(live.value ? (positions.value[pin.facility_id] ?? {}) : {}),
    })),
    { zoom: live.value ? (zoom.value ?? 0) : null },
  ),
);

// the map is viewport-driven: it never auto-frames to the returned pins (that would
// fight the driver's pan). Whatever the map shows, the surface fetches for.
function overlayLngLat() {
  return [
    ...props.pins.map((p) => [p.lon, p.lat]),
    ...props.clusters.map((c) => [c.lon, c.lat]),
  ];
}

// the map's live viewport as the API's bbox params (min/max lat/lon)
function emitBounds() {
  if (!map) return;
  const b = map.getBounds();
  const sw = b.getSouthWest();
  const ne = b.getNorthEast();
  emit("bounds", { min_lat: sw.lat, min_lon: sw.lng, max_lat: ne.lat, max_lon: ne.lng });
}

const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
// Mapbox Standard (GL v3): modern vector basemap with dynamic lighting. Day/night
// via lightPreset so it reads well in a dark cab; the saturated semantic pins ride
// on top as DOM overlays regardless of basemap (§11.2).
const STYLE = "mapbox://styles/mapbox/standard";
// AI-CONTEXT: §11.6 pairs the night basemap with the DARK THEME, not with the clock —
// see `basemapPreset`. The rule lives in core/ so it can be tested; this reads it and
// re-applies it whenever the driver's theme changes, because a basemap that only
// picked a side at map-load would drift the moment they used the toggle.
const { mode } = useTheme();
const systemDark =
  typeof window !== "undefined" && window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;
const prefersDark = ref(systemDark ? systemDark.matches : true);
function applyPreset() {
  if (!map || !live.value) return;
  try {
    map.setConfigProperty("basemap", "lightPreset", basemapPreset(mode.value, prefersDark.value));
  } catch {
    /* style not ready yet — `load` applies it, and the watcher re-applies after */
  }
}
function onSystemTheme(e) {
  prefersDark.value = e.matches;
}
// the manual override AND the system setting, because §6.1 C-3 is both
watch([mode, prefersDark], applyPreset);
// the moment tiles exist the markers can be projected; without this they wait for the
// next pin change or pan, which is precisely the window they spent at the origin
watch(live, (on) => {
  if (on) nextTick(paintPositions);
});
// new pins render at the origin until something places them; paint on the tick their
// elements exist, or a refetch would flash every marker into the top-left corner
watch(
  () => [props.pins, props.clusters],
  () => nextTick(paintPositions),
  { deep: false },
);

// the map opens on the continental US (never a hardcoded city) — the server returns
// cluster bubbles at this span (§11.5); GPS then recenters if the driver allows it.
const US_CENTER = [-98.5, 39.8];
const US_ZOOM = 3.5;
// §23 entry 99: metro-wide, not street-level. A driver asking for "Dallas" wants the
// stops around it, and truck stops ring a city rather than sit downtown — measured at
// 0 within 8 km of downtown Dallas and 26 within 25 km, so a tight zoom would open on
// an empty screen and read as broken.
const PLACE_ZOOM = 9;

// AI-CONTEXT: §23 entry 101 — markers move without Vue.
//
// This ran on EVERY frame of a pan and wrote `top`/`left` into reactive state, so a
// full viewport re-projected up to 300 pins, replaced two reactive objects and asked
// Vue to re-render every marker — with `top`/`left`, which forces LAYOUT rather than
// only paint. Markers visibly trailed the tiles they were pinned to.
//
// The hot path is now imperative and transform-only: element refs held OUTSIDE
// reactivity, `translate3d` composed with the centring translate the stylesheet
// already applies, so the compositor moves them and Vue is not involved at all.
//
// `positions` still exists and still feeds §11.5's label declutter — but it settles
// ONCE per gesture (`moveend`) instead of once per frame. The set of visible price
// labels therefore holds steady during a drag and re-deckutters when the map stops,
// which is also better behaviour than labels flickering in and out mid-pan.
const pinEls = new Map(); // facility_id -> element, deliberately NOT reactive
const clusterEls = new Map(); // index -> element

function setPinEl(id, el) {
  if (el) pinEls.set(id, el);
  else pinEls.delete(id);
}
function setClusterEl(i, el) {
  if (el) clusterEls.set(i, el);
  else clusterEls.delete(i);
}

// the composition itself lives in core/ (§19) so it is testable without a GL context
function place(el, x, y) {
  const transform = markerTransform(x, y);
  if (transform) el.style.transform = transform;
}

function paintPositions() {
  if (!map || !live.value) return;
  placed.value = true;
  for (const pin of props.pins) {
    const el = pinEls.get(pin.facility_id);
    if (!el) continue;
    const pt = map.project([pin.lon, pin.lat]);
    place(el, pt.x, pt.y);
  }
  props.clusters.forEach((c, i) => {
    const el = clusterEls.get(i);
    if (!el) return;
    const pt = map.project([c.lon, c.lat]);
    place(el, pt.x, pt.y);
  });
}

// once the gesture settles: the reactive read the declutter rule needs
function settlePositions() {
  if (!map) return;
  zoom.value = map.getZoom();
  const next = {};
  for (const pin of props.pins) {
    const pt = map.project([pin.lon, pin.lat]);
    next[pin.facility_id] = { x: pt.x, y: pt.y };
  }
  positions.value = next;
  const nextC = {};
  props.clusters.forEach((c, i) => {
    const pt = map.project([c.lon, c.lat]);
    nextC[i] = { x: pt.x, y: pt.y };
  });
  clusterPositions.value = nextC;
}

function syncPins() {
  paintPositions();
  settlePositions();
}

function zoomToCluster(cluster) {
  if (!map) return;
  map.easeTo({ center: [cluster.lon, cluster.lat], zoom: map.getZoom() + 2, duration: 300 });
}

// AI-CONTEXT: §23 entry 99. Moving the VIEW is the only thing this exposes — it
// reuses `easeTo`, the same call the cluster zoom above makes, so the canvas gains
// no new behaviour. Nothing here touches the driver's location: `located` still
// fires from the geolocate control alone, and the surface keeps its own fix.
// `bounds` fires on the resulting move, so the overlay refetches on its own.
function showPlace(lat, lon, zoom = PLACE_ZOOM) {
  if (!map) return;
  map.easeTo({ center: [lon, lat], zoom, duration: 400 });
}
// §23 entry 100: a KEPT-ALIVE canvas is re-shown rather than rebuilt, and Mapbox
// sizes itself to a container it measured while visible. Coming back to a viewport
// that changed while hidden leaves it drawing at the old size until something nudges
// it, so the surface tells it to re-measure on activation.
function remeasure() {
  map?.resize();
}
defineExpose({ showPlace, remeasure, hasRememberedView: () => readView() !== null });

onMounted(async () => {
  systemDark?.addEventListener?.("change", onSystemTheme);
  if (!TOKEN) return; // no token -> the placeholder canvas below (activation seam)
  try {
    const mapboxgl = (await import("mapbox-gl")).default;
    await import("mapbox-gl/dist/mapbox-gl.css");
    mapboxgl.accessToken = TOKEN;
    // §23 entry 100: open where the driver last WAS, not on the country. A remembered
    // view is only ever their own last viewport, so this cannot teleport anyone —
    // and with none stored the continental default is unchanged.
    const remembered = readView();
    map = new mapboxgl.Map({
      container: mapEl.value,
      style: STYLE,
      center: remembered ? [remembered.lon, remembered.lat] : US_CENTER,
      zoom: remembered ? remembered.zoom : US_ZOOM,
      // AI-CONTEXT: Mapbox's default attribution sits BOTTOM-RIGHT, which is where
      // §10.1 puts the report chip, so the compact "i" landed on top of it. Moving it
      // bottom-LEFT only traded one collision for another — measured, it then sat
      // inside the voice chip. It goes TOP-left: the only corner neither of our
      // floating controls uses, and the locate control has the other one.
      //
      // The Mapbox LOGO cannot be repositioned and stays bottom-left, which is why
      // the voice chip moves rather than the logo (see MapSurface).
      attributionControl: false,
    });
    map.addControl(new mapboxgl.AttributionControl({ compact: true }), "top-left");

    // "locate me": a blue dot + heading that centers on the driver's GPS, with a
    // tap control to re-center. Auto-triggered on load — a driver's map opens on
    // where they are (§10.1). Emits `located` so the surface refetches nearby pins.
    const geolocate = new mapboxgl.GeolocateControl({
      positionOptions: { enableHighAccuracy: true },
      trackUserLocation: true,
      showUserHeading: true,
    });
    // AI-CONTEXT: TOP-right, not bottom-right (§23 entry 89). Mapbox puts this
    // control, its attribution bar and its logo along the bottom edge — which is
    // exactly where §10.1 puts the floating report chip and §14 puts the voice chip.
    // Four controls from two owners in one corner, overlapping, was what the owner
    // saw. Ours keep the thumb zone; the library's furniture moves out of it.
    map.addControl(geolocate, "top-right");
    geolocate.on("geolocate", (e) => {
      // the control recenters the map -> its moveend re-emits `bounds` -> refetch
      emit("located", { lat: e.coords.latitude, lon: e.coords.longitude });
    });

    map.on("load", () => {
      syncPins();
      live.value = true;
      applyPreset();
      emitBounds(); // fetch the initial (continental) viewport
      try {
        geolocate.trigger();
      } catch {
        /* geolocation blocked/unavailable — stay on the continental view */
      }
    });
    map.on("move", paintPositions);
    map.on("moveend", settlePositions); // §11.5 declutter, once per gesture
    map.on("moveend", emitBounds); // every pan/zoom refetches what's now in view
    map.on("moveend", () => {
      const c = map.getCenter();
      rememberView(c.lat, c.lng, map.getZoom());
    });
  } catch {
    live.value = false; // WebGL unavailable / offline -> keep the placeholder
  }
});

onUnmounted(() => {
  if (systemDark) systemDark.removeEventListener?.("change", onSystemTheme);
  if (map) map.remove();
});

// a new overlay (the viewport's fetch resolved) -> reproject onto the live map.
// The viewport itself is driver-controlled; we never re-frame to the pins.
watch(
  () => [props.pins, props.clusters],
  () => {
    if (live.value) syncPins();
  },
  { deep: true },
);

// bounds-normalized fallback layout (used until/unless tiles are live)
const bounds = computed(() => {
  const points = overlayLngLat();
  const lons = points.map((p) => p[0]);
  const lats = points.map((p) => p[1]);
  return {
    minLat: Math.min(...lats),
    maxLat: Math.max(...lats),
    minLon: Math.min(...lons),
    maxLon: Math.max(...lons),
  };
});
function fallbackLatLon(lat, lon) {
  const b = bounds.value;
  const spanLat = b.maxLat - b.minLat || 1;
  const spanLon = b.maxLon - b.minLon || 1;
  const top = 90 - ((lat - b.minLat) / spanLat) * 80 - 5;
  const left = ((lon - b.minLon) / spanLon) * 80 + 10;
  return { top: `${top}%`, left: `${left}%` };
}

// §23 entry 101: LIVE markers are pinned at the origin and moved by `paintPositions`
// with a transform, so nothing here re-renders while the map moves. Without a GL map
// — the fallback the layout harness and every unit test measure — the bounds-
// normalised percentages are unchanged.
// `display: none` rather than hidden/transparent: an unplaced marker must have NO BOX
// at all, or it still overhangs the viewport and is still a layout defect — the check
// skips zero-sized elements, and so does a driver's eye.
function unplaced() {
  return live.value && !placed.value ? { display: "none" } : null;
}
function pinStyle(pin) {
  const pos = live.value ? { top: "0", left: "0" } : fallbackLatLon(pin.lat, pin.lon);
  return { ...pos, ...unplaced(), "--pin-color": `var(${statusPresentation(pin.status).token})` };
}
function clusterStyle(cluster) {
  const pos = live.value ? { top: "0", left: "0" } : fallbackLatLon(cluster.lat, cluster.lon);
  return {
    ...pos,
    ...unplaced(),
    "--pin-color": `var(${statusPresentation(cluster.status).token})`,
  };
}
function stale(pin) {
  return isStale(pin.freshness, now);
}
</script>

<template>
  <div class="canvas" role="application" aria-label="Map">
    <div ref="mapEl" class="canvas__gl" :class="{ 'canvas__gl--on': live }" />
    <span v-if="!live" class="canvas__note">Map · tiles pending</span>
    <button
      v-for="pin in pins"
      :key="pin.facility_id"
      type="button"
      class="pin"
      :ref="(el) => setPinEl(pin.facility_id, el)"
      :class="{ 'pin--stale': stale(pin) }"
      :style="pinStyle(pin)"
      :data-facility="pin.facility_id"
      :aria-label="pinLabel(pin)"
      @click="emit('pinTap', pin)"
    >
      <span class="pin__puck">
        <component :is="iconFor(pin)" :size="15" :stroke-width="2.5" aria-hidden="true" />
      </span>
      <!-- §11.2 badge slot, first use (M13 / §23 E-D2). §11.1 is the reason this is
           a badge and not a second pin: extra signals ride on the pins that already
           exist. Icon + the marker token, never colour alone (C-1). -->
      <span v-if="pin.has_food" class="pin__badge" :aria-label="t('map.preset.food')">
        <UtensilsCrossed :size="10" :stroke-width="3" aria-hidden="true" />
      </span>
      <!-- §11.2's "$ (bookable)" slot. The opposite shoulder from food, because a lot
           with a cook on it legitimately carries both and they must not stack.
           AI-CONTEXT: an ICON, not the character "$" — and that is the layout harness
           talking, not a preference. The first cut set `font-size: 10px` on a text
           glyph, which is both a hardcoded value (§22.3 box 8 is tokens-only) and
           below §6.2's 13 dp floor, and the harness named it at 360 dp in three
           locales within minutes of it being written. The food badge never tripped the
           rule because it was always an icon; a badge disc is 14 dp and no legal type
           size fits inside one, so the slot can only ever hold a glyph. -->
      <span
        v-if="isBookable(pin)"
        class="pin__badge pin__badge--book"
        :aria-label="t('facility.book')"
      >
        <DollarSign :size="10" :stroke-width="3" aria-hidden="true" />
      </span>
      <!-- §11.2's "clock (dwell risk)" slot. Bottom shoulder, so it can never collide
           with food or the bookable $ even though no facility type carries both today.
           `marker` is the caution token — this is a warning, not an error: the dock is
           not broken, it is slow. Icon AND token, never colour alone (C-1). -->
      <span
        v-if="dwellRisk(pin)"
        class="pin__badge pin__badge--dwell"
        :aria-label="t('facility.dwell_risk')"
      >
        <Clock :size="10" :stroke-width="3" aria-hidden="true" />
      </span>
      <!-- §11.2's "price (fuel)" slot. A price is a LABEL, not a glyph, so it obeys
           §11.5's declutter rule — see `priceLabels`. Mono tabular like every other
           figure (T-2), and aria-hidden because the button's own label already names
           the facility; a screen reader reading "$3.94" between two pin names would
           be reading the map, not the place. -->
      <span v-if="priceLabels[pin.facility_id]" class="pin__price" aria-hidden="true">
        {{ priceLabels[pin.facility_id] }}
      </span>
    </button>
    <!-- §11.5: at density the server clusters; a count bubble (dominant status color),
         tap zooms in. -->
    <button
      v-for="(cl, i) in clusters"
      :key="'cl-' + i"
      type="button"
      class="cluster"
      :ref="(el) => setClusterEl(i, el)"
      :style="clusterStyle(cl)"
      :aria-label="`${cl.count} ${t('map.cluster_label')}`"
      @click="zoomToCluster(cl)"
    >
      <span class="cluster__bubble">
        <span class="cluster__count">{{ cl.count }}</span>
      </span>
    </button>
    <!-- AI-CONTEXT: ODbL credit for our OSM-derived facility rows (PRD §12), shown
         only when there is no basemap to carry it. Mapbox's own attribution bar
         already reads "© OpenStreetMap contributors", so while tiles are live this
         printed the same sentence a second time, on top of the first — two identical
         credits stacked in the corner. One visible credit naming OSM contributors
         discharges the obligation; two is not twice as compliant, it is clutter. -->
    <span v-if="!live" class="canvas__credit">{{ t("map.data_credit") }}</span>
  </div>
</template>

<style scoped>
.canvas {
  position: relative;
  height: 100%;
  min-height: 240px;
  background: var(--ink-0);
  overflow: hidden;
}
.canvas__gl {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 200ms ease;
}
.canvas__gl--on {
  opacity: 1;
}
.canvas__credit {
  position: absolute;
  bottom: 2px;
  right: 4px;
  padding: 0 var(--s-1);
  border-radius: var(--r-pill);
  background: var(--ink-1);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  pointer-events: none;
}
.canvas__note {
  position: absolute;
  top: var(--s-3);
  left: 50%;
  transform: translateX(-50%);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  font-family: var(--font-mono);
}
.pin {
  position: absolute;
  width: 44px; /* §11.2: 44 dp hit area */
  height: 44px;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
}
/* color encodes status, icon encodes type, hollow ring encodes stale (§11.7) */
.pin__puck {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--on-accent);
  background: var(--pin-color);
  border: 2px solid var(--on-accent);
  box-shadow: var(--shadow-pin);
  transition: transform 0.12s ease;
}
.pin:hover .pin__puck,
.pin:focus-visible .pin__puck {
  transform: scale(1.12);
}
.pin:focus-visible {
  outline: none;
}
/* the badge rides the puck's top-right shoulder. The puck is 28 dp centred in the
   pin's 44 dp hit area, so these offsets overlap it rather than floating in the
   corner of the (invisible) hit box. The 44 dp target itself is unchanged (§11.2). */
.pin__badge {
  position: absolute;
  top: 4px;
  right: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: var(--r-pill);
  border: 1px solid var(--ink-0);
  background: var(--marker-500);
  color: var(--ink-0);
}
/* §11.2's "$ (bookable)" slot, on the shoulder opposite food so a bookable lot with a
   cook on it shows both without stacking. Same 14 dp disc, same token vocabulary —
   `shield` rather than `marker` because a bookable spot is reassurance, not caution. */
.pin__badge--book {
  right: auto;
  left: 4px;
  background: var(--shield-500);
  color: var(--on-accent);
}
/* §11.2's "price (fuel)" slot. It sits below the puck rather than on it: a price is
   four to six characters and no shoulder disc can hold that. Ink-1 plate with a
   hairline so it stays legible over any basemap, and `pointer-events: none` so the
   label never steals the pin's own 44 dp target (§11.2). */
/* the bottom-right shoulder. Same 14 dp disc and the same token vocabulary as the
   other two slots — a third badge, not a third pattern. */
.pin__badge--dwell {
  top: auto;
  bottom: 4px;
  right: 4px;
  background: var(--marker-500);
  color: var(--ink-0);
}
.pin__price {
  position: absolute;
  top: calc(50% + 14px);
  left: 50%;
  transform: translateX(-50%);
  padding: 0 4px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  color: var(--text-1);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-caption-size);
  line-height: 16px;
  white-space: nowrap;
  pointer-events: none;
}
/* the hollow ring is the §11.7 affordance for "this reading is old", so its fill is
   deliberately theme-INVARIANT — a fill that darkened with the theme would make a stale
   pin read as a filled one at a glance, which is the honesty law failing silently.
   --on-accent is the system's theme-invariant white; it is named for a label on an
   accent fill, and this is the inverse use of the same value. Logged as composition
   (§23 entry 130) rather than inventing a --pin-hollow holding the same white twice. */
.pin--stale .pin__puck {
  background: var(--on-accent);
  color: var(--pin-color);
  border-color: var(--pin-color);
}
/* §11.5 cluster chip: count + dominant status color */
/* AI-CONTEXT: audit U-05 — the cluster was a 36 dp target with NO expanded hit area,
   below §6.5's 48 and below §11.2's deliberate 44 dp map exemption too. §11.2 sets map
   markers at "44 dp hit areas regardless of visual size", and a cluster bubble is that
   species of marker, so 44 is the floor it belongs under rather than 48.
   The fix is the pattern `.pin` already uses — a 44 dp BUTTON around a smaller visual —
   so the bubble still renders at 36 dp and the map is not re-weighted. §23 entry 130's
   warning applies: a touch-target pass that restyles the map is not a touch-target pass.
   The bubble itself moved to `.cluster__bubble`; `.cluster` is now the hit area. */
.cluster {
  position: absolute;
  transform: translate(-50%, -50%);
  width: 44px;
  height: 44px;
  min-width: 44px;
  padding: 0;
  background: transparent;
  border: 0;
  box-shadow: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.cluster__bubble {
  min-width: 36px;
  height: 36px;
  padding: 0 var(--s-2);
  border-radius: var(--r-pill);
  background: var(--pin-color);
  color: var(--on-accent);
  border: 2px solid var(--on-accent);
  box-shadow: var(--shadow-pin);
  display: flex;
  align-items: center;
  justify-content: center;
}
.cluster__count {
  font-size: var(--type-label-size);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
