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
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { Truck, TreePine, SquareParking, Fuel, Warehouse, Circle, UtensilsCrossed } from "lucide-vue-next";
import { statusPresentation, isStale } from "../presentation.js";
import { useI18n } from "../i18n.js";

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
let map = null;

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
function lightPreset() {
  const hour = new Date().getHours();
  return hour < 7 || hour >= 19 ? "night" : "day";
}

// the map opens on the continental US (never a hardcoded city) — the server returns
// cluster bubbles at this span (§11.5); GPS then recenters if the driver allows it.
const US_CENTER = [-98.5, 39.8];
const US_ZOOM = 3.5;

function syncPins() {
  if (!map) return;
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

function zoomToCluster(cluster) {
  if (!map) return;
  map.easeTo({ center: [cluster.lon, cluster.lat], zoom: map.getZoom() + 2, duration: 300 });
}

onMounted(async () => {
  if (!TOKEN) return; // no token -> the placeholder canvas below (activation seam)
  try {
    const mapboxgl = (await import("mapbox-gl")).default;
    await import("mapbox-gl/dist/mapbox-gl.css");
    mapboxgl.accessToken = TOKEN;
    map = new mapboxgl.Map({
      container: mapEl.value,
      style: STYLE,
      center: US_CENTER,
      zoom: US_ZOOM,
    });

    // "locate me": a blue dot + heading that centers on the driver's GPS, with a
    // tap control to re-center. Auto-triggered on load — a driver's map opens on
    // where they are (§10.1). Emits `located` so the surface refetches nearby pins.
    const geolocate = new mapboxgl.GeolocateControl({
      positionOptions: { enableHighAccuracy: true },
      trackUserLocation: true,
      showUserHeading: true,
    });
    map.addControl(geolocate, "bottom-right");
    geolocate.on("geolocate", (e) => {
      // the control recenters the map -> its moveend re-emits `bounds` -> refetch
      emit("located", { lat: e.coords.latitude, lon: e.coords.longitude });
    });

    map.on("load", () => {
      map.setConfigProperty("basemap", "lightPreset", lightPreset());
      syncPins();
      live.value = true;
      emitBounds(); // fetch the initial (continental) viewport
      try {
        geolocate.trigger();
      } catch {
        /* geolocation blocked/unavailable — stay on the continental view */
      }
    });
    map.on("move", syncPins);
    map.on("moveend", emitBounds); // every pan/zoom refetches what's now in view
  } catch {
    live.value = false; // WebGL unavailable / offline -> keep the placeholder
  }
});

onUnmounted(() => {
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

function pinStyle(pin) {
  const p = live.value ? positions.value[pin.facility_id] : null;
  const pos = p ? { top: `${p.y}px`, left: `${p.x}px` } : fallbackLatLon(pin.lat, pin.lon);
  return { ...pos, "--pin-color": `var(${statusPresentation(pin.status).token})` };
}
function clusterStyle(cluster, i) {
  const p = live.value ? clusterPositions.value[i] : null;
  const pos = p ? { top: `${p.y}px`, left: `${p.x}px` } : fallbackLatLon(cluster.lat, cluster.lon);
  return { ...pos, "--pin-color": `var(${statusPresentation(cluster.status).token})` };
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
      :class="{ 'pin--stale': stale(pin) }"
      :style="pinStyle(pin)"
      :aria-label="pin.name"
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
    </button>
    <!-- §11.5: at density the server clusters; a count bubble (dominant status color),
         tap zooms in. -->
    <button
      v-for="(cl, i) in clusters"
      :key="'cl-' + i"
      type="button"
      class="cluster"
      :style="clusterStyle(cl, i)"
      :aria-label="`${cl.count} ${t('map.cluster_label')}`"
      @click="zoomToCluster(cl)"
    >
      <span class="cluster__count">{{ cl.count }}</span>
    </button>
    <!-- data attribution — OSM-derived rows require ODbL credit (PRD §12) -->
    <span class="canvas__credit">{{ t("map.data_credit") }}</span>
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
  color: #fff;
  background: var(--pin-color);
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
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
.pin--stale .pin__puck {
  background: #fff;
  color: var(--pin-color);
  border-color: var(--pin-color);
}
/* §11.5 cluster chip: count + dominant status color */
.cluster {
  position: absolute;
  transform: translate(-50%, -50%);
  min-width: 36px;
  height: 36px;
  padding: 0 var(--s-2);
  border-radius: var(--r-pill);
  background: var(--pin-color);
  color: #fff;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.cluster__count {
  font-size: var(--type-label-size);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
