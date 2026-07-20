<!-- AI-CONTEXT: Map surface / the daily-open tab (design-prd §10.1). Anatomy at
     360 dp: full-bleed canvas → preset chips (top) → floating report chip
     (bottom-right, thumb zone) → facility card as a bottom sheet on pin tap.
     DRIVING (§5/§11.4): Corridor mode replaces free-pan; taps deferred-safe.
     Data is fixture-backed pending the M1 HTTP API (see core/fixtures.js). -->
<script setup>
import { ref, computed } from "vue";
import { CircleDot } from "lucide-vue-next";
import MapCanvas from "../core/components/MapCanvas.vue";
import PresetChips from "../core/components/PresetChips.vue";
import BottomSheet from "../core/components/BottomSheet.vue";
import FacilityCard from "../core/components/FacilityCard.vue";
import CorridorStack from "../core/components/CorridorStack.vue";
import ReportSheet from "../core/components/ReportSheet.vue";
import { useDriverState } from "../core/state.js";
import { useI18n } from "../core/i18n.js";
import { SAMPLE_PINS, SAMPLE_CORRIDOR } from "../core/fixtures.js";

const { isDriving } = useDriverState();
const { t } = useI18n();

const preset = ref("drive");
const PRESET_TYPES = {
  drive: ["truck_stop", "rest_area", "fuel_station"],
  tonight: ["truck_stop", "rest_area", "parking_property"],
  work: ["shipper_receiver"],
  fuel: ["fuel_station"],
};
const PARKING_RANK = { empty: 0, some: 1, null: 2, full: 3 };

const pins = computed(() => {
  const types = PRESET_TYPES[preset.value];
  let list = SAMPLE_PINS.filter((p) => types.includes(p.facility_type));
  if (preset.value === "tonight") {
    list = [...list].sort(
      (a, b) => (PARKING_RANK[a.status] ?? 2) - (PARKING_RANK[b.status] ?? 2),
    );
  }
  return list;
});

const selected = ref(null);
const reporting = ref(false);

function navigate(pin) {
  const url = `https://www.google.com/maps/dir/?api=1&destination=${pin.lat},${pin.lon}`;
  if (typeof window !== "undefined" && window.open) window.open(url, "_blank");
  selected.value = null;
}
function report() {
  selected.value = null;
  reporting.value = true;
}
function submitReport() {
  // AI-CONTEXT: server enforces geofence-presence proof + points (F10/M1). API seam.
  reporting.value = false;
}
</script>

<template>
  <div class="map">
    <template v-if="isDriving">
      <CorridorStack :entries="SAMPLE_CORRIDOR" />
    </template>
    <template v-else>
      <PresetChips v-model="preset" />
      <div class="map__canvas">
        <MapCanvas :pins="pins" @pin-tap="selected = $event" />
        <button class="report-chip" type="button" :aria-label="t('map.report')" @click="reporting = true">
          <CircleDot :size="24" :stroke-width="2" aria-hidden="true" />
        </button>
      </div>
    </template>

    <BottomSheet :open="!!selected" :title="selected?.name || ''" @close="selected = null">
      <FacilityCard v-if="selected" :pin="selected" @navigate="navigate" @report="report" />
    </BottomSheet>

    <BottomSheet :open="reporting" :title="t('map.report')" @close="reporting = false">
      <ReportSheet @report="submitReport" />
    </BottomSheet>
  </div>
</template>

<style scoped>
.map {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.map__canvas {
  position: relative;
  flex: 1 1 auto;
  min-height: 240px;
}
.report-chip {
  position: absolute;
  right: var(--s-4);
  bottom: var(--s-4);
  width: 56px;
  height: 56px;
  border-radius: var(--r-pill);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  color: var(--shield-500);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-float);
}
</style>
