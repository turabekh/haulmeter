<!-- AI-CONTEXT: Map canvas. Live Mapbox tiles are an activation seam (token
     pending); until then this is a token-styled placeholder (design-prd §11.6
     night/day, roads/labels desaturated so semantic pins are the only saturated
     elements). Pins carry shape from facility type (§11.2), fill from status,
     hollow when stale (§11.7); 44 dp hit areas. Swap the placeholder for a tile
     layer behind this same interface — pins/handlers are unchanged. -->
<script setup>
import { computed } from "vue";
import { statusPresentation, isStale } from "../presentation.js";

const props = defineProps({
  pins: { type: Array, default: () => [] },
});
const emit = defineEmits(["pinTap"]);

const now = Date.now();
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

function project(pin) {
  const b = bounds.value;
  const spanLat = b.maxLat - b.minLat || 1;
  const spanLon = b.maxLon - b.minLon || 1;
  const top = 90 - ((pin.lat - b.minLat) / spanLat) * 80 - 5;
  const left = ((pin.lon - b.minLon) / spanLon) * 80 + 10;
  return { top: `${top}%`, left: `${left}%` };
}

function pinColor(pin) {
  return `var(${statusPresentation(pin.status).token})`;
}
function stale(pin) {
  return isStale(pin.freshness, now);
}
</script>

<template>
  <div class="canvas" role="application" aria-label="Map">
    <span class="canvas__note">Map · tiles pending</span>
    <button
      v-for="pin in pins"
      :key="pin.facility_id"
      type="button"
      class="pin"
      :class="[`pin--${pin.shape}`, { 'pin--hollow': stale(pin) }]"
      :style="{ ...project(pin), '--pin-color': pinColor(pin) }"
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
