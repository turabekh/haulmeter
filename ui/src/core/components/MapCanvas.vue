<!-- AI-CONTEXT: Map canvas. Live Mapbox GL tiles when VITE_MAPBOX_TOKEN is set
     (M1 activation seam, now wired); otherwise a token-styled placeholder. The
     basemap is a desaturated built-in style — dark at night, light by day
     (design-prd §11.6) — so roads/labels stay muted and the SEMANTIC PINS are the
     only saturated ink. Pins carry shape from facility type (§11.2), fill from
     status, hollow when stale (§11.7); 44 dp hit areas. When live, pins are
     re-projected onto the moving map; when not, they fall back to a bounds-
     normalized layout. Mapbox GL is dynamically imported so the no-token build
     (and tests) never load the ~200 KB library. -->
<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { statusPresentation, isStale } from "../presentation.js";

const props = defineProps({
  pins: { type: Array, default: () => [] },
});
const emit = defineEmits(["pinTap"]);

const now = Date.now();
const mapEl = ref(null);
const live = ref(false); // true once a GL map is rendering tiles
const positions = ref({}); // facility_id -> { x, y } pixel coords on the live map
let map = null;

const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
// desaturated built-ins: dark at night, light by day (§11.6). Swappable later.
function styleUrl() {
  const hour = new Date().getHours();
  const night = hour < 7 || hour >= 19;
  return night ? "mapbox://styles/mapbox/dark-v11" : "mapbox://styles/mapbox/light-v11";
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
      style: styleUrl(),
      center: center(),
      zoom: props.pins.length ? 9 : 4,
      attributionControl: true,
    });
    map.on("load", () => {
      fitToPins();
      syncPins();
      live.value = true;
    });
    map.on("move", syncPins);
  } catch {
    live.value = false; // WebGL unavailable / offline -> keep the placeholder
  }
});

onUnmounted(() => {
  if (map) map.remove();
});

// pins refresh (new overlay) -> refit + reproject when live
watch(
  () => props.pins,
  () => {
    if (live.value) {
      fitToPins();
      syncPins();
    }
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
      :class="[`pin--${pin.shape}`, { 'pin--hollow': stale(pin) }]"
      :style="pinStyle(pin)"
      :aria-label="pin.name"
      @click="emit('pinTap', pin)"
    />
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
}
.pin::before {
  content: "";
  width: 18px;
  height: 18px;
  background: var(--pin-color);
  border: 2px solid var(--ink-0);
}
.pin--hollow::before {
  background: transparent;
  border-color: var(--pin-color);
}
.pin--circle::before {
  border-radius: 50%;
}
.pin--square::before {
  border-radius: 2px;
}
.pin--diamond::before {
  transform: rotate(45deg);
}
.pin--small_square::before {
  width: 12px;
  height: 12px;
  border-radius: 1px;
}
</style>
