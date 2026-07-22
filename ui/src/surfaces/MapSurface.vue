<!-- AI-CONTEXT: Map surface / the daily-open tab (design-prd §10.1). Anatomy at
     360 dp: full-bleed canvas → preset chips (top) → floating report chip
     (bottom-right, thumb zone) → facility card as a bottom sheet on pin tap.
     DRIVING (§5/§11.4): Corridor mode replaces free-pan; taps deferred-safe.
     Data is fixture-backed pending the M1 HTTP API (see core/fixtures.js). -->
<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { CircleDot, Mic } from "lucide-vue-next";
import MapCanvas from "../core/components/MapCanvas.vue";
import PresetChips from "../core/components/PresetChips.vue";
import BottomSheet from "../core/components/BottomSheet.vue";
import FacilityCard from "../core/components/FacilityCard.vue";
import CorridorStack from "../core/components/CorridorStack.vue";
import ReportSheet from "../core/components/ReportSheet.vue";
import VoiceSheet from "../core/components/VoiceSheet.vue";
import SleepSheet from "../core/components/SleepSheet.vue";
import HandoffSheet from "../core/components/HandoffSheet.vue";
import { useDriverState } from "../core/state.js";
import { useI18n } from "../core/i18n.js";
import { SAMPLE_PINS, SAMPLE_CORRIDOR, sampleHandoffs } from "../core/fixtures.js";
import { fetchOverlay, fetchNearbyHandoffs, broadcastHandoff, report as postReport } from "../core/api.js";

const { isDriving } = useDriverState();
const { t } = useI18n();
const router = useRouter();

const preset = ref("drive");
const PRESET_TYPES = {
  drive: ["truck_stop", "rest_area", "fuel_station"],
  tonight: ["truck_stop", "rest_area", "parking_property"],
  work: ["shipper_receiver"],
  fuel: ["fuel_station"],
};
const PARKING_RANK = { empty: 0, some: 1, null: 2, full: 3 };

// the map's fetch center: the driver's GPS once located (MapCanvas @located),
// else a sensible default until then (§10.1 — a real map follows the driver)
const geo = ref({ lat: 32.78, lon: -96.8 });
function onLocated({ lat, lon }) {
  geo.value = { lat, lon };
  loadOverlay(); // pins near the driver, not a fixed point
  loadHandoffs();
}

// live pins from the M1 API when a session exists; otherwise fixtures (§ api.js).
// At real national density the server returns clusters instead (§11.5) — kept in
// `clusters` for the cluster-bubble render; `pins` is empty in that case.
const livePins = ref(null);
const clusters = ref([]);
async function loadOverlay() {
  try {
    const resp = await fetchOverlay({ lat: geo.value.lat, lon: geo.value.lon, preset: preset.value });
    livePins.value = resp.pins;
    clusters.value = resp.clusters || [];
  } catch {
    livePins.value = null; // fall back to fixtures (unauthenticated / offline)
    clusters.value = [];
  }
}
onMounted(loadOverlay);
watch(preset, loadOverlay);

const pins = computed(() => {
  if (livePins.value) return livePins.value; // API already preset-filtered
  const types = PRESET_TYPES[preset.value];
  let list = SAMPLE_PINS.filter((p) => types.includes(p.facility_type));
  if (preset.value === "tonight") {
    list = [...list].sort((a, b) => (PARKING_RANK[a.status] ?? 2) - (PARKING_RANK[b.status] ?? 2));
  }
  return list;
});

const selected = ref(null);
const reporting = ref(false);
const listening = ref(false);
const solving = ref(false);
const relaying = ref(false);
const handoffs = ref([]);

async function loadHandoffs() {
  try {
    handoffs.value = await fetchNearbyHandoffs({ lat: geo.value.lat, lon: geo.value.lon });
  } catch {
    handoffs.value = sampleHandoffs(); // unauthenticated / offline
  }
}
onMounted(loadHandoffs);

function handoff(pin) {
  // M10-FR2: broadcast "leaving soon" from this free lot (backend proves presence)
  selected.value = null;
  broadcastHandoff(pin.facility_id).catch(() => {});
}

function navigate(pin) {
  const url = `https://www.google.com/maps/dir/?api=1&destination=${pin.lat},${pin.lon}`;
  if (typeof window !== "undefined" && window.open) window.open(url, "_blank");
  selected.value = null;
}
// which facility a parking report will land on (a tapped pin, or the nearest one
// for the floating report chip). Kept so submitReport knows the target.
const reportTarget = ref(null);
function report(pin) {
  reportTarget.value = pin; // from the facility card
  selected.value = null;
  reporting.value = true;
}
function nearestPin() {
  if (!pins.value.length) return null;
  const { lat, lon } = geo.value;
  let best = null;
  let bestD = Infinity;
  for (const p of pins.value) {
    const d = (p.lat - lat) ** 2 + (p.lon - lon) ** 2;
    if (d < bestD) { bestD = d; best = p; }
  }
  return best;
}
function reportChip() {
  reportTarget.value = nearestPin(); // the floating chip reports the nearest lot
  reporting.value = true;
}
function book(pin) {
  // NAV-5 cross-link: deep-link into the full-screen booking checkout. The spot
  // id + take-inclusive nightly ride on the bookable badge (M6 inventory).
  const badge = pin.badges?.find((b) => b.kind === "bookable");
  selected.value = null;
  router.push({
    name: "book",
    params: { spotId: badge?.spot_id ?? pin.facility_id },
    query: { name: pin.name, nightly: badge?.value ?? 0 },
  });
}
function fuel(pin) {
  // NAV-5 cross-link into the full-screen fuel flow; net/gross/savings (cents)
  // ride on the fuel_net badge (M7 net-price layer).
  const badge = pin.badges?.find((b) => b.kind === "fuel_net");
  selected.value = null;
  router.push({
    name: "fuel",
    params: { stationId: badge?.station_ref ?? pin.facility_id },
    query: { name: pin.name, gross: badge?.gross ?? 0, net: badge?.net ?? 0, savings: badge?.savings ?? 0 },
  });
}
async function submitReport(status) {
  // M1-FR7: post the parking status (server enforces geofence-presence proof +
  // points, F10/M1), then refresh the overlay so the pin's color updates live.
  const target = reportTarget.value;
  reporting.value = false;
  if (!target) return;
  try {
    await postReport(target.facility_id, "parking_fullness", { status });
    await loadOverlay();
  } catch {
    /* offline -> the report is queued (F12) and syncs on reconnect */
  }
}
</script>

<template>
  <div class="map">
    <template v-if="isDriving">
      <CorridorStack :entries="SAMPLE_CORRIDOR" />
    </template>
    <template v-else>
      <PresetChips v-model="preset" />
      <!-- M8-FR3: the "where do I sleep tonight" solver, surfaced in Tonight -->
      <button v-if="preset === 'tonight'" class="sleep-cta" type="button" @click="solving = true">
        {{ t("sleep.title") }}
      </button>
      <!-- M10-FR2: spots opening nearby — the claimable relay feed -->
      <button v-if="handoffs.length" class="relay-banner" type="button" @click="relaying = true">
        {{ handoffs.length }} {{ t("handoff.nearby") }}
      </button>
      <div class="map__canvas">
        <MapCanvas :pins="pins" @pin-tap="selected = $event" @located="onLocated" />
        <button class="report-chip" type="button" :aria-label="t('map.report')" @click="reportChip">
          <CircleDot :size="24" :stroke-width="2" aria-hidden="true" />
        </button>
      </div>
    </template>

    <!-- M11-FR5: the copilot wake affordance (on-screen button; headset maps
         here too). Voice is the DRIVING-state input (§14), so it stays present
         in both IDLE and Corridor modes. No always-on hotword. -->
    <button
      class="voice-chip"
      :class="{ 'voice-chip--driving': isDriving }"
      type="button"
      :aria-label="t('voice.mic')"
      @click="listening = true"
    >
      <Mic :size="24" :stroke-width="2" aria-hidden="true" />
    </button>

    <!-- hide-title: keep the name as the dialog's aria-label but let FacilityCard
         render the one visible name header (no duplication) -->
    <BottomSheet :open="!!selected" :title="selected?.name || ''" hide-title @close="selected = null">
      <FacilityCard
        v-if="selected"
        :pin="selected"
        @navigate="navigate"
        @report="report"
        @book="book"
        @fuel="fuel"
        @handoff="handoff"
      />
    </BottomSheet>

    <BottomSheet :open="reporting" :title="t('map.report')" @close="reporting = false">
      <ReportSheet @report="submitReport" />
    </BottomSheet>

    <BottomSheet :open="listening" :title="t('voice.title')" @close="listening = false">
      <VoiceSheet :driving="isDriving" />
    </BottomSheet>

    <BottomSheet :open="solving" :title="t('sleep.title')" @close="solving = false">
      <SleepSheet />
    </BottomSheet>

    <BottomSheet :open="relaying" :title="t('handoff.title')" @close="relaying = false">
      <HandoffSheet :handoffs="handoffs" />
    </BottomSheet>
  </div>
</template>

<style scoped>
.map {
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
}
.voice-chip {
  position: absolute;
  left: var(--s-4);
  bottom: var(--s-4);
  width: 56px;
  height: 56px;
  border-radius: var(--r-pill);
  background: var(--accent-fill);
  color: var(--on-accent);
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-float);
  z-index: 2;
}
/* voice is the DRIVING input (§14): a bigger, centered target in Corridor mode */
.voice-chip--driving {
  left: 50%;
  transform: translateX(-50%);
  width: 72px;
  height: 72px;
}
.sleep-cta {
  margin: var(--s-2) var(--s-4) 0;
  min-height: 44px;
  border-radius: var(--r-control);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  color: var(--text-1);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.relay-banner {
  margin: var(--s-2) var(--s-4) 0;
  min-height: 44px;
  border-radius: var(--r-control);
  background: var(--shield-500);
  color: var(--on-accent);
  border: none;
  font-size: var(--type-label-size);
  font-weight: 500;
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
