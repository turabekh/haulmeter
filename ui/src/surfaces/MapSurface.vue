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
import PriceReportSheet from "../core/components/PriceReportSheet.vue";
import VoiceSheet from "../core/components/VoiceSheet.vue";
import SleepSheet from "../core/components/SleepSheet.vue";
import HandoffSheet from "../core/components/HandoffSheet.vue";
import VendorSheet from "../core/components/VendorSheet.vue";
import { useDriverState } from "../core/state.js";
import { useI18n } from "../core/i18n.js";
import { SAMPLE_PINS, SAMPLE_CORRIDOR, sampleHandoffs } from "../core/fixtures.js";
import { withFoodBadges, foodBadgeFacilityIds } from "../core/vendors.js";
import {
  fetchOverlay,
  fetchNearbyHandoffs,
  broadcastHandoff,
  report as postReport,
  confirmFuelPrice,
  fetchVendorAppearances,
  cachedAppearances,
  fetchVendorsAt,
  fetchVendorSheet,
  confirmVendor,
  muteVendor,
  suggestACook,
  fetchCorridorVendors,
} from "../core/api.js";

const { isDriving } = useDriverState();
const { t } = useI18n();
const router = useRouter();

const preset = ref("drive");
const PRESET_TYPES = {
  drive: ["truck_stop", "rest_area", "fuel_station"],
  tonight: ["truck_stop", "rest_area", "parking_property"],
  work: ["shipper_receiver"],
  fuel: ["fuel_station"],
  // M13: Food is a filter over the lots vendors actually work, not a new layer —
  // §11.1 caps active layers at two, and the badge does the signalling.
  food: ["truck_stop", "rest_area", "parking_property"],
};
const PARKING_RANK = { empty: 0, some: 1, null: 2, full: 3 };

// the map's fetch center: the driver's GPS once located (MapCanvas @located),
// else a sensible default until then (§10.1 — a real map follows the driver).
// Handoffs stay point-based (nearby); the overlay is viewport-driven (onBounds).
const geo = ref({ lat: 32.78, lon: -96.8 });
function onLocated({ lat, lon }) {
  geo.value = { lat, lon };
  loadHandoffs(); // the map's recenter fires @bounds -> overlay refetch on its own
}

// the continental US, shown until the live map reports its viewport. At national
// span the server returns cluster bubbles (§11.5), never a hardcoded city.
const CONTINENTAL_US = { min_lat: 24, min_lon: -125, max_lat: 50, max_lon: -66 };

// live pins from the M1 API when a session exists; otherwise fixtures (§ api.js).
// At real density the server returns clusters instead (§11.5) — kept in `clusters`
// for the cluster-bubble render; `pins` is empty in that case.
const livePins = ref(null);
const clusters = ref([]);
let lastBbox = CONTINENTAL_US; // the current viewport; a preset flip refetches it
let overlayController = null; // aborts the in-flight fetch when a newer one starts
let boundsTimer = null; // debounce rapid pan/zoom moveend bursts (~300ms)

async function loadOverlay(bbox = lastBbox) {
  lastBbox = bbox;
  if (overlayController) overlayController.abort();
  overlayController = new AbortController();
  try {
    const resp = await fetchOverlay({
      bbox,
      preset: preset.value,
      signal: overlayController.signal,
    });
    livePins.value = resp.pins;
    clusters.value = resp.clusters || [];
  } catch (e) {
    if (e.name === "AbortError") return; // superseded by a newer viewport — keep pins
    livePins.value = null; // fall back to fixtures (unauthenticated / offline)
    clusters.value = [];
  }
}

// MapCanvas @bounds on load + every moveend (pan/zoom). Debounced so a drag settles
// before we hit the API; the AbortController cancels any fetch a newer move outran.
function onBounds(bbox) {
  clearTimeout(boundsTimer);
  boundsTimer = setTimeout(() => {
    loadOverlay(bbox);
    loadVendors(bbox);
  }, 300);
}
onMounted(() => {
  loadOverlay(); // continental clusters until the map reports bounds
  loadVendors();
});
watch(preset, () => loadOverlay()); // preset flip refetches the current viewport

const pins = computed(() => {
  // Food narrows the view to lots a driver can actually eat at tonight; every other
  // preset keeps its pins and just gains the badge (§11.1 — signals ride on pins).
  const flagged = foodBadgeFacilityIds(vendorEntries.value);
  const base =
    preset.value === "food"
      ? rawPins.value.filter((p) => flagged.has(p.facility_id))
      : rawPins.value;
  return withFoodBadges(base, vendorEntries.value);
});

// Q-7: the Food chip over an empty viewport shows ONE quiet line plus the
// recruitment affordance — never a scolding or celebratory empty state (§15.3).
const foodEmpty = computed(() => preset.value === "food" && pins.value.length === 0);

const rawPins = computed(() => {
  if (livePins.value) return livePins.value; // API already preset-filtered
  const types = PRESET_TYPES[preset.value];
  let list = SAMPLE_PINS.filter((p) => types.includes(p.facility_type));
  if (preset.value === "tonight") {
    list = [...list].sort((a, b) => (PARKING_RANK[a.status] ?? 2) - (PARKING_RANK[b.status] ?? 2));
  }
  return list;
});

// M13-FR3: appearances in view drive the pins' food badge and the card section.
// Offline (§15.1): today's cache renders the food layer in a dead zone; a stale
// cache is dropped rather than shown, since dead content is what Q-1 forbids.
const vendorEntries = ref([]);
const facilityVendors = ref([]);
const vendorSheet = ref(null);
const vendorTarget = ref(null);

async function loadVendors(bbox = lastBbox) {
  try {
    const entries = await fetchVendorAppearances({ bbox });
    vendorEntries.value = Array.isArray(entries) ? entries : cachedAppearances();
  } catch {
    vendorEntries.value = cachedAppearances(); // dead zone / flag off / no session
  }
}

// DRIVING: food ahead on the current heading, capped at three (Q-6)
const corridorFood = ref([]);
async function loadCorridorFood() {
  try {
    const ahead = await fetchCorridorVendors({ lat: geo.value.lat, lon: geo.value.lon });
    corridorFood.value = Array.isArray(ahead) ? ahead : [];
  } catch {
    corridorFood.value = [];
  }
}
watch(isDriving, (driving) => {
  if (driving) loadCorridorFood();
});

async function loadFacilityVendors(facilityId) {
  try {
    const found = await fetchVendorsAt(facilityId, { allVendors: true });
    facilityVendors.value = Array.isArray(found) ? found : [];
  } catch {
    // offline / flag off: fall back to whatever the viewport cache knows
    facilityVendors.value = vendorEntries.value.filter((e) => e.facility_id === facilityId);
  }
}

async function openVendor(entry) {
  // `null` is the card's "all vendors" affordance — the sheet lists the rest
  if (entry === null) {
    selected.value = null;
    return;
  }
  vendorTarget.value = entry;
  selected.value = null;
  try {
    vendorSheet.value = await fetchVendorSheet(entry.vendor_id);
  } catch {
    vendorSheet.value = null;
  }
}

async function confirmVendorPresence(present) {
  const entry = vendorTarget.value;
  vendorSheet.value = null;
  if (!entry) return;
  try {
    await confirmVendor(entry.vendor_id, entry.facility_id, { present });
    await loadVendors();
  } catch {
    /* offline -> queued (F12) and syncs on reconnect */
  }
}

async function reportVendorSoldOut() {
  const entry = vendorTarget.value;
  vendorSheet.value = null;
  if (!entry) return;
  try {
    await confirmVendor(entry.vendor_id, entry.facility_id, { soldOut: true });
    await loadVendors();
  } catch {
    /* offline -> queued */
  }
}

async function muteThisVendor() {
  const entry = vendorTarget.value;
  vendorSheet.value = null;
  if (entry) await muteVendor(entry.vendor_id).catch(() => {});
}

const selected = ref(null);
function onPinTap(pin) {
  selected.value = pin;
  facilityVendors.value = [];
  loadFacilityVendors(pin.facility_id);
}
const reporting = ref(false);
// Q-7 recruitment affordance: records where a driver wants food (the demand half of
// the vendor recruitment loop) and says so plainly. It promises nothing beyond that.
const suggested = ref(false);
async function suggestCook() {
  suggested.value = true;
  await suggestACook(geo.value.lat, geo.value.lon).catch(() => {});
}
const pricingReport = ref(false); // the diesel-price report sheet (M7-FR5)
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

// M7-FR5: diesel-price contribution. The seed is the station's currently-shown
// price (crowd/regional) so the driver nudges rather than types.
const priceStart = computed(() => reportTarget.value?.badges?.find((b) => b.kind === "fuel_net")?.net ?? 389);
function reportPrice(pin) {
  reportTarget.value = pin;
  selected.value = null;
  pricingReport.value = true;
}
async function submitPrice(cents) {
  // post the per-gallon price (server proves presence + forms the consensus, F10),
  // then refresh the overlay so the pin's price updates once consensus lands.
  const target = reportTarget.value;
  pricingReport.value = false;
  if (!target) return;
  try {
    await confirmFuelPrice(target.facility_id, cents);
    await loadOverlay();
  } catch {
    /* offline -> queued (F12) and syncs on reconnect */
  }
}
</script>

<template>
  <div class="map">
    <template v-if="isDriving">
      <CorridorStack :entries="SAMPLE_CORRIDOR" :vendors="corridorFood" />
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
      <!-- Q-7: one quiet line + the recruitment affordance. No filler, no scolding. -->
      <p v-if="foodEmpty" class="food-empty">
        {{ t("vendor.none_nearby") }}
        <button
          v-if="!suggested"
          class="food-empty__cta"
          type="button"
          @click="suggestCook"
        >
          {{ t("vendor.suggest") }}
        </button>
        <span v-else class="food-empty__done">{{ t("vendor.suggest_thanks") }}</span>
      </p>
      <div class="map__canvas">
        <MapCanvas
          :pins="pins"
          :clusters="clusters"
          @pin-tap="onPinTap"
          @located="onLocated"
          @bounds="onBounds"
        />
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
        :vendors="facilityVendors"
        @vendor="openVendor"
        @navigate="navigate"
        @report="report"
        @report-price="reportPrice"
        @book="book"
        @fuel="fuel"
        @handoff="handoff"
      />
    </BottomSheet>

    <BottomSheet
      :open="!!vendorSheet"
      :title="vendorSheet?.name || ''"
      hide-title
      @close="vendorSheet = null"
    >
      <VendorSheet
        v-if="vendorSheet"
        :sheet="vendorSheet"
        @confirm="confirmVendorPresence(true)"
        @not-here="confirmVendorPresence(false)"
        @sold-out="reportVendorSoldOut"
        @mute="muteThisVendor"
      />
    </BottomSheet>

    <BottomSheet :open="reporting" :title="t('map.report')" @close="reporting = false">
      <ReportSheet @report="submitReport" />
    </BottomSheet>

    <BottomSheet :open="pricingReport" :title="t('fuel.report.title')" @close="pricingReport = false">
      <PriceReportSheet :start-cents="priceStart" @submit="submitPrice" />
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
/* Q-7 / §15.3: one quiet sentence and one action. Deliberately not a card, not a
   banner, not an illustration — an empty stretch of road is not an event. */
.food-empty {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: 0;
  padding: var(--s-2) var(--s-4);
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.food-empty__cta {
  min-height: 48px;
  padding: 0 var(--s-2);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
.food-empty__done {
  color: var(--text-3);
}
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
