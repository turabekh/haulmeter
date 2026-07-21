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
import { Truck, TreePine, SquareParking, Fuel, Warehouse, Circle } from "lucide-vue-next";
import { statusPresentation, isStale } from "../presentation.js";

const props = defineProps({
  pins: { type: Array, default: () => [] },
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
// `located` fires with the driver's GPS so the surface can refetch the overlay
// around them (pins follow the driver, not a fixed center).
const emit = defineEmits(["pinTap", "located"]);

const now = Date.now();
const mapEl = ref(null);
const live = ref(false); // true once a GL map is rendering tiles
const positions = ref({}); // facility_id -> { x, y } pixel coords on the live map
let map = null;
let located = false; // once the driver is centered, stop auto-fitting to pins

const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
// Mapbox Standard (GL v3): modern vector basemap with dynamic lighting. Day/night
// via lightPreset so it reads well in a dark cab; the saturated semantic pins ride
// on top as DOM overlays regardless of basemap (§11.2).
const STYLE = "mapbox://styles/mapbox/standard";
function lightPreset() {
  const hour = new Date().getHours();
  return hour < 7 || hour >= 19 ? "night" : "day";
}

const DALLAS = [-96.797, 32.7767];
function center() {
  if (!props.pins.length) return DALLAS;
  const lat = props.pins.reduce((s, p) => s + p.lat, 0) / props.pins.length;
  const lon = props.pins.reduce((s, p) => s + p.lon, 0) / props.pins.length;
  return [lon, lat];
}

function syncPins() {
  if (!map) return;
  const next = {};
  for (const pin of props.pins) {
    const pt = map.project([pin.lon, pin.lat]);
    next[pin.facility_id] = { x: pt.x, y: pt.y };
  }
  positions.value = next;
}

function fitToPins() {
  if (!map || props.pins.length < 2) return;
  const lats = props.pins.map((p) => p.lat);
  const lons = props.pins.map((p) => p.lon);
  map.fitBounds(
    [
      [Math.min(...lons), Math.min(...lats)],
      [Math.max(...lons), Math.max(...lats)],
    ],
    { padding: 56, maxZoom: 14, duration: 0 },
  );
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
      center: center(),
      zoom: props.pins.length ? 9 : 4,
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
      located = true;
      emit("located", { lat: e.coords.latitude, lon: e.coords.longitude });
    });

    map.on("load", () => {
      map.setConfigProperty("basemap", "lightPreset", lightPreset());
      fitToPins(); // fallback framing until GPS resolves (or if it's denied)
      syncPins();
      live.value = true;
      try {
        geolocate.trigger();
      } catch {
        /* geolocation blocked/unavailable — stay framed on the pins */
      }
    });
    map.on("move", syncPins);
  } catch {
    live.value = false; // WebGL unavailable / offline -> keep the placeholder
  }
});

onUnmounted(() => {
  if (map) map.remove();
});

// pins refresh (new overlay) -> reproject; only refit while we haven't centered
// on the driver (once located, the map stays on them, not the pin bounds)
watch(
  () => props.pins,
  () => {
    if (!live.value) return;
    if (!located) fitToPins();
    syncPins();
  },
  { deep: true },
);

// bounds-normalized fallback layout (used until/unless tiles are live)
const bounds = computed(() => {
  const lats = props.pins.map((p) => p.lat);
  const lons = props.pins.map((p) => p.lon);
  return {
    minLat: Math.min(...lats),
    maxLat: Math.max(...lats),
    minLon: Math.min(...lons),
    maxLon: Math.max(...lons),
  };
});
function fallbackStyle(pin) {
  const b = bounds.value;
  const spanLat = b.maxLat - b.minLat || 1;
  const spanLon = b.maxLon - b.minLon || 1;
  const top = 90 - ((pin.lat - b.minLat) / spanLat) * 80 - 5;
  const left = ((pin.lon - b.minLon) / spanLon) * 80 + 10;
  return { top: `${top}%`, left: `${left}%` };
}

function pinStyle(pin) {
  const p = live.value ? positions.value[pin.facility_id] : null;
  const pos = p ? { top: `${p.y}px`, left: `${p.x}px` } : fallbackStyle(pin);
  return { ...pos, "--pin-color": `var(${statusPresentation(pin.status).token})` };
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
    </button>
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
.pin--stale .pin__puck {
  background: #fff;
  color: var(--pin-color);
  border-color: var(--pin-color);
}
</style>
