<!-- AI-CONTEXT: Map surface / the daily-open tab (design-prd §10.1). Anatomy at
     360 dp: full-bleed canvas → preset chips (top) → floating report chip
     (bottom-right, thumb zone) → facility card as a bottom sheet on pin tap.
     DRIVING (§5/§11.4): Corridor mode replaces free-pan; taps deferred-safe.
     Data is fixture-backed pending the M1 HTTP API (see core/fixtures.js). -->
<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useRouter } from "vue-router";
import { CircleDot, Mic, SlidersHorizontal, Bookmark } from "lucide-vue-next";
import MapCanvas from "../core/components/MapCanvas.vue";
import PresetChips from "../core/components/PresetChips.vue";
import BottomSheet from "../core/components/BottomSheet.vue";
import FacilityCard from "../core/components/FacilityCard.vue";
import CorridorStack from "../core/components/CorridorStack.vue";
import ReportSheet from "../core/components/ReportSheet.vue";
import MoreFiltersSheet from "../core/components/MoreFiltersSheet.vue";
import PriceReportSheet from "../core/components/PriceReportSheet.vue";
import VoiceSheet from "../core/components/VoiceSheet.vue";
import SleepSheet from "../core/components/SleepSheet.vue";
import HandoffSheet from "../core/components/HandoffSheet.vue";
import VendorSheet from "../core/components/VendorSheet.vue";
import { useDriverState } from "../core/state.js";
import { useI18n } from "../core/i18n.js";
import { SAMPLE_PINS, sampleHandoffs } from "../core/fixtures.js";
import { lastFix, metersBetween } from "../core/location.js";
import { presetFor, rememberPreset } from "../core/map-presets.js";
import { saved, saveForStop, unsave } from "../core/saved.js";
import { withFoodBadges, foodBadgeFacilityIds } from "../core/vendors.js";
import { statusReportFor, ageLabel } from "../core/presentation.js";
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
  followVendor,
  muteVendor,
  unfollowVendor,
  suggestACook,
  activeStopFacilityId,
  fetchActiveLoad,
  fetchCorridor,
  fetchCorridorVendors,
  fetchScalesAhead,
  fetchFacilityPromotions,
  reviewVendor,
  reportVendor,
} from "../core/api.js";

const { isDriving, state: driverState } = useDriverState();
const { t } = useI18n();
const router = useRouter();

// AI-CONTEXT: §11.3 — "Preset choice persists per state (RESTING→Tonight)" (§23
// entry 82). The preset was a bare `ref("drive")`, so every visit to the map reset to
// Drive: a driver who parked for the night and opened the map to find a shower was
// handed the fuel-and-scales view, every time. The Food FILTERS beside it have been
// persisted since they shipped, which is what makes the omission a miss rather than a
// decision — the pattern was already in this file.
//
// Per STATE, not one global value, because the spec's own example is a rule about
// which preset belongs to which situation: Tonight is the right answer while resting
// and the wrong one while rolling.
const preset = ref(presetFor(driverState.value));
// the driver's choice is remembered against the state they made it in...
watch(preset, (chosen) => rememberPreset(driverState.value, chosen));
// ...and coming back into a state restores what was last used there
watch(driverState, (next) => {
  const remembered = presetFor(next);
  if (remembered !== preset.value) preset.value = remembered;
});

const PRESET_TYPES = {
  // E3.1: scales ride the Drive preset, which is the preset for moving forward —
  // exactly when a weigh station is a decision. They are absent from Tonight and
  // Work, where they would be noise (§11.1 keeps the map quiet).
  drive: ["truck_stop", "rest_area", "fuel_station", "weigh_station", "scale"],
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
// whether that default has been replaced by a REAL fix. Distances are measured from
// the driver, so until this is true no origin is sent and no distance is shown —
// a figure measured from a default would be confidently wrong (§11.7).
const located = ref(false);
function onLocated({ lat, lon }) {
  geo.value = { lat, lon };
  located.value = true;
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
  // which dock is the driver's own, so the Work preset can mark it and its card can
  // lead with §10.1's "Arm stop" rung. Never persisted — see api.js.
  fetchActiveLoad().catch(() => {
    /* no session / offline / no load: every pin is just a pin, which is correct */
  });
  // AI-CONTEXT: a driver who opens the map ALREADY driving. The `isDriving` watcher
  // only fires on a transition, so arriving in that state loaded nothing and the
  // corridor sat blank until the next GPS fix moved the driver far enough to trip the
  // refresh throttle. That is the commonest way this screen is reached — the tab is
  // opened mid-journey, not at the moment the truck starts rolling.
  if (isDriving.value) loadAhead();
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
// With a filter applied the two states are DIFFERENT facts: "no cooks work here" and
// "your filter hid them" call for different next actions, and telling a driver the
// first when the second is true would make them stop looking.
const foodEmpty = computed(() => preset.value === "food" && pins.value.length === 0);
const filteredEmpty = computed(() => foodEmpty.value && filtersActive.value);

const rawPins = computed(() => {
  if (livePins.value) return livePins.value; // API already preset-filtered
  const types = PRESET_TYPES[preset.value];
  let list = SAMPLE_PINS.filter((p) => types.includes(p.facility_type));
  if (preset.value === "tonight") {
    list = [...list].sort((a, b) => (PARKING_RANK[a.status] ?? 2) - (PARKING_RANK[b.status] ?? 2));
  }
  return list;
});

// §11.3: the ONE "More filters" sheet. Persisted like the preset is, because the
// choice has to survive into DRIVING — no keyboard is available at speed, so a
// filter is only useful if it was set while stopped and kept applying afterwards.
const FILTERS_KEY = "longhaul.food_filters";
const EMPTY_FILTERS = { q: "", language: "", halal: "" };
function loadFilters() {
  try {
    return { ...EMPTY_FILTERS, ...(JSON.parse(localStorage.getItem(FILTERS_KEY)) || {}) };
  } catch {
    return { ...EMPTY_FILTERS };
  }
}
const filters = ref(loadFilters());
const filtering = ref(false);
const filtersActive = computed(
  () => !!(filters.value.q || filters.value.language || filters.value.halal),
);
watch(
  filters,
  (v) => {
    try {
      localStorage.setItem(FILTERS_KEY, JSON.stringify(v));
    } catch {
      /* private mode — the filter stays for this session only */
    }
    loadVendors();
    if (isDriving.value) loadCorridorFood();
  },
  { deep: true },
);

// M13-FR3: appearances in view drive the pins' food badge and the card section.
// Offline (§15.1): today's cache renders the food layer in a dead zone; a stale
// cache is dropped rather than shown, since dead content is what Q-1 forbids.
const vendorEntries = ref([]);
const facilityVendors = ref([]);
// kept in its own ref, never merged into facilityVendors (Q-3)
const facilityPromotions = ref([]);
const vendorSheet = ref(null);
const vendorTarget = ref(null);

async function loadVendors(bbox = lastBbox) {
  try {
    const entries = await fetchVendorAppearances({
      bbox,
      filters: filters.value,
      origin: located.value ? geo.value : null,
    });
    vendorEntries.value = Array.isArray(entries) ? entries : cachedAppearances();
  } catch {
    vendorEntries.value = cachedAppearances(); // dead zone / flag off / no session
  }
}

// AI-CONTEXT: which way the truck is pointing (§23 entry 81).
//
// Every "ahead" query in this file used to send heading 0 — due north — because the
// location sensor never captured one. `null` here is the honest third state: a
// stationary truck has no heading, and the corridor says so rather than aiming itself
// at the north pole.
const headingDeg = computed(() => lastFix.value?.headingDeg ?? null);

// §11.4's stack, from the server. Held null until the first answer so an empty
// corridor and an unfetched one are different things on screen.
const corridor = ref(null);
// how far, and how long, before the stack is worth re-asking for. At 55 mph 1.5 km is
// about a minute — often enough that the next decision is always on screen, rarely
// enough that a corridor fetch is not riding on the driver's data plan every second.
const CORRIDOR_REFRESH_METERS = 1500;
const CORRIDOR_REFRESH_MS = 90_000;
let corridorAt = 0;
let corridorFrom = null;

async function loadCorridor() {
  if (headingDeg.value === null) return; // no direction -> no "ahead" to compute
  corridorAt = Date.now();
  corridorFrom = { ...geo.value };
  try {
    const ahead = await fetchCorridor({
      lat: geo.value.lat,
      lon: geo.value.lon,
      headingDeg: headingDeg.value,
      preset: preset.value,
    });
    corridor.value = Array.isArray(ahead) ? ahead : [];
  } catch {
    // offline / no session. The last stack stays rather than blanking: the facilities
    // a driver was told about a minute ago are still on this road.
    if (corridor.value === null) corridor.value = [];
  }
}

// DRIVING: food ahead on the current heading, capped at three (Q-6)
const corridorFood = ref([]);
async function loadCorridorFood() {
  try {
    const ahead = await fetchCorridorVendors({
      lat: geo.value.lat,
      lon: geo.value.lon,
      headingDeg: headingDeg.value ?? 0,
      filters: filters.value, // set while stopped, honoured while moving
    });
    corridorFood.value = Array.isArray(ahead) ? ahead : [];
  } catch {
    corridorFood.value = [];
  }
}
// E3.1: scales ahead, server-capped at two. Empty while the layer flag is off.
const corridorScales = ref([]);
async function loadScalesAhead() {
  try {
    const ahead = await fetchScalesAhead({
      lat: geo.value.lat,
      lon: geo.value.lon,
      headingDeg: headingDeg.value ?? 0,
    });
    corridorScales.value = Array.isArray(ahead) ? ahead : [];
  } catch {
    corridorScales.value = [];
  }
}

function loadAhead() {
  loadCorridor();
  loadCorridorFood();
  loadScalesAhead();
}
watch(isDriving, (driving) => {
  if (driving) loadAhead();
});

// AI-CONTEXT: the stack has to MOVE with the truck, which is the half a one-shot
// fetch on the DRIVING transition would miss — a driver who set off an hour ago would
// still be reading the three facilities that were ahead of them then. The sensor
// fires far more often than this needs, so the refresh is throttled on distance and
// time rather than on every fix.
watch(lastFix, (fix) => {
  if (!fix || !isDriving.value || headingDeg.value === null) return;
  geo.value = { lat: fix.lat, lon: fix.lon };
  located.value = true;
  const far =
    !corridorFrom ||
    metersBetween(corridorFrom.lat, corridorFrom.lon, fix.lat, fix.lon) >= CORRIDOR_REFRESH_METERS;
  if (far || Date.now() - corridorAt >= CORRIDOR_REFRESH_MS) loadAhead();
});

async function loadFacilityVendors(facilityId) {
  try {
    const [found, promoted] = await Promise.all([
      fetchVendorsAt(facilityId, { allVendors: true }),
      fetchFacilityPromotions(facilityId).catch(() => []),
    ]);
    facilityVendors.value = Array.isArray(found) ? found : [];
    facilityPromotions.value = Array.isArray(promoted) ? promoted : [];
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

async function submitVendorReview({ rating, text }) {
  const entry = vendorTarget.value;
  if (!entry) return;
  try {
    await reviewVendor(entry.vendor_id, rating, text);
    vendorSheet.value = await fetchVendorSheet(entry.vendor_id); // reflect the new pair
  } catch {
    /* too soon / offline — the sheet already says when they can return */
  }
}

async function reportThisVendor(reason) {
  const entry = vendorTarget.value;
  vendorSheet.value = null;
  if (entry) await reportVendor(entry.vendor_id, reason).catch(() => {});
}

// following re-fetches the sheet rather than flipping a local flag: the server
// decides what one tap changed (the class may have been switched on, an old mute
// may have been cleared), and a screen that guessed could show the wrong state.
async function followThisVendor(on) {
  const entry = vendorTarget.value;
  if (!entry) return;
  try {
    await (on ? followVendor(entry.vendor_id) : unfollowVendor(entry.vendor_id));
    vendorSheet.value = await fetchVendorSheet(entry.vendor_id);
  } catch {
    /* queued offline, or no session — the sheet keeps the state it has */
  }
}

async function muteThisVendor() {
  const entry = vendorTarget.value;
  vendorSheet.value = null;
  if (entry) await muteVendor(entry.vendor_id).catch(() => {});
}

// §10.1's third CTA. A comparison, not a request: the facility id is already in hand.
function isActiveStopPin(pin) {
  return (
    !!activeStopFacilityId.value && String(pin?.facility_id) === String(activeStopFacilityId.value)
  );
}
// NAV-5 cross-link, the same shape as Book and Fuel. The Load tab owns the Meter, the
// arrive CTA and the evidence checklist; duplicating any of that onto a map sheet
// would be two screens telling a driver about one stop.
function openStop() {
  selected.value = null;
  router.push("/load");
}

const selected = ref(null);
function onPinTap(pin) {
  selected.value = pin;
  facilityVendors.value = [];
  facilityPromotions.value = [];
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
// §11.4's saved queue. `now` ticks only while the sheet is closed-or-open on a stopped
// truck; the age it renders is coarse (minutes), so a slow clock is plenty.
const showingSaved = ref(false);
const now = ref(Date.now());
let ageTimer = null;
onMounted(() => {
  ageTimer = setInterval(() => (now.value = Date.now()), 30_000);
});
onUnmounted(() => ageTimer && clearInterval(ageTimer));

const savedIds = computed(() => saved.value.map((item) => item.id));

// the deferred-safe tap. It saves and nothing else — no navigation, no sheet, no
// confirm, because every one of those is a flow and §11.4 exists to prevent flows at
// speed. The corridor card marks itself from `savedIds` and that is the whole feedback.
function saveAhead(entry) {
  saveForStop({
    id: entry.facility_id,
    kind: "facility",
    label: entry.name,
    payload: { facility_type: entry.facility_type, lat: entry.lat, lon: entry.lon },
  });
}

function navigateSaved(row) {
  // the corridor payload has no coordinates today, so this routes through the
  // facility page rather than guessing a destination — a Navigate that might open a
  // map of nowhere is the dead-control pattern with a worse consequence.
  if (row.payload?.lat != null && row.payload?.lon != null) {
    navigate({ lat: row.payload.lat, lon: row.payload.lon });
    showingSaved.value = false;
    return;
  }
  openSavedFacility(row);
}
function openSavedFacility(row) {
  showingSaved.value = false;
  router.push(`/facility/${row.id}`);
}
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

// M13-FR3: the sheet's primary action. The entry carries the LOT's coordinates, so
// this hands off exactly the appearance the driver tapped rather than guessing from
// whatever pin happens to be selected. Reuses the M1-FR8 handoff unchanged.
function navigateToVendor(entry) {
  vendorSheet.value = null;
  if (entry?.lat != null && entry?.lon != null) navigate(entry);
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
  // M1-FR7: post the status (server enforces geofence-presence proof + points,
  // F10/M1), then refresh the overlay so the pin's color updates live. The SIGNAL
  // follows the facility kind, from the same helper that chose the question — a
  // scale's answer must not be filed as a parking reading.
  const target = reportTarget.value;
  reporting.value = false;
  if (!target) return;
  try {
    await postReport(target.facility_id, statusReportFor(target.facility_type).signal, { status });
    await loadOverlay();
    if (isDriving.value) await loadScalesAhead();
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
      <!-- §11.7, and the two states a fixture never had to have. "We don't know which
           way you are pointing" and "this stretch is empty" are different facts and
           lead to different behaviour: the first is worth waiting out, the second is
           worth acting on. Neither is a spinner — a driver at speed reads a sentence
           or nothing. -->
      <p v-if="headingDeg === null" class="corridor-note">{{ t("corridor.no_heading") }}</p>
      <p
        v-else-if="corridor && !corridor.length && !corridorScales.length && !corridorFood.length"
        class="corridor-note"
      >
        {{ t("corridor.empty") }}
      </p>
      <CorridorStack
        :entries="corridor || []"
        :vendors="corridorFood"
        :scales="corridorScales"
        :saved-ids="savedIds"
        @save="saveAhead"
      />
    </template>
    <template v-else>
      <PresetChips v-model="preset" />
      <!-- M8-FR3: the "where do I sleep tonight" solver, surfaced in Tonight -->
      <button v-if="preset === 'tonight'" class="sleep-cta" type="button" @click="solving = true">
        {{ t("sleep.title") }}
      </button>
      <!-- AI-CONTEXT: §11.4's saved queue, arriving where it is useful (§23 entry 83).
           It renders only when STOPPED and only when there is something in it — a
           driver at a dock is the audience, and "Saved · 0" is a control that teaches
           nothing. Composed from the relay banner's own shape one line below, so this
           adds no component pattern; the owner's decision was the DESTINATION, which
           §22 makes a never-improvise category. -->
      <button v-if="savedIds.length" class="saved-chip" type="button" @click="showingSaved = true">
        <Bookmark :size="16" :stroke-width="2" aria-hidden="true" />
        {{ t("saved.title") }}
        <span class="saved-chip__count">{{ savedIds.length }}</span>
      </button>
      <!-- M10-FR2: spots opening nearby — the claimable relay feed -->
      <button v-if="handoffs.length" class="relay-banner" type="button" @click="relaying = true">
        {{ handoffs.length }} {{ t("handoff.nearby") }}
      </button>
      <!-- §11.3: presets stay the interface; ONE filters sheet sits behind the Food
           chip, and only there — the other presets have nothing to narrow yet. -->
      <button
        v-if="preset === 'food'"
        class="filters-chip"
        :class="{ 'filters-chip--on': filtersActive }"
        type="button"
        @click="filtering = true"
      >
        <SlidersHorizontal :size="16" :stroke-width="2" aria-hidden="true" />
        {{ t("filters.button") }}
      </button>

      <!-- two different facts, two different next actions: nobody cooks here, or
           your filter hid them. Saying the first when the second is true would make
           a driver stop looking. -->
      <p v-if="filteredEmpty" class="food-empty">
        {{ t("filters.none_match") }}
        <button class="food-empty__cta" type="button" @click="filters = { ...EMPTY_FILTERS }">
          {{ t("filters.clear") }}
        </button>
      </p>
      <!-- Q-7: one quiet line + the recruitment affordance. No filler, no scolding. -->
      <p v-else-if="foodEmpty" class="food-empty">
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
        :promotions="facilityPromotions"
        :is-active-stop="isActiveStopPin(selected)"
        @open-stop="openStop"
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
        :target="vendorTarget"
        @navigate="navigateToVendor"
        @follow="followThisVendor(true)"
        @unfollow="followThisVendor(false)"
        @confirm="confirmVendorPresence(true)"
        @not-here="confirmVendorPresence(false)"
        @sold-out="reportVendorSoldOut"
        @mute="muteThisVendor"
        @review="submitVendorReview"
        @report="reportThisVendor"
      />
    </BottomSheet>

    <!-- IDLE only. Forbidden #11 bans keyboard input while moving, and §11.4 replaces
         free exploration with the corridor — filters already set keep applying. -->
    <BottomSheet
      :open="filtering && !isDriving"
      :title="t('filters.title')"
      @close="filtering = false"
    >
      <MoreFiltersSheet v-model="filters" @close="filtering = false" />
    </BottomSheet>

    <BottomSheet :open="reporting" :title="t('map.report')" @close="reporting = false">
      <ReportSheet :facility-type="reportTarget?.facility_type" @report="submitReport" />
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

    <!-- AI-CONTEXT: what a corridor tap becomes once the truck stops (§23 entry 83).
         Deliberately carries NO status and NO distance. Both were true when the driver
         tapped, thirty miles ago, and §11.7 forbids showing a stale reading as a
         current one — a lot that read `empty` at 60 mph is exactly the lot that fills
         while you drive to it. The AGE of the tap is shown instead, which is a fact
         that does not decay, and both actions lead somewhere that re-reads the truth:
         Navigate hands off to the nav app, and the facility page loads live intel —
         which is also the honest route to Book, whose nightly price must never be
         quoted from a badge saved half an hour ago. -->
    <BottomSheet :open="showingSaved" :title="t('saved.title')" @close="showingSaved = false">
      <p v-if="!saved.length" class="docs__empty">{{ t("saved.empty") }}</p>
      <ul v-else class="saved">
        <li v-for="row in saved" :key="row.id" class="saved__row">
          <span class="saved__name">{{ row.label }}</span>
          <span class="saved__meta">{{ t("saved.ago") }} {{ ageLabel(row.at, now) }}</span>
          <span class="saved__acts">
            <button class="saved__act" type="button" @click="navigateSaved(row)">
              {{ t("facility.navigate") }}
            </button>
            <button class="saved__act" type="button" @click="openSavedFacility(row)">
              {{ t("facility.view") }}
            </button>
            <button class="saved__act saved__act--rm" type="button" @click="unsave(row.id)">
              {{ t("saved.remove") }}
            </button>
          </span>
        </li>
      </ul>
      <p class="saved__hint">{{ t("saved.hint") }}</p>
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
/* §15.3 at speed: one sentence, body size because it is read in a glance from a
   metre away, and no card — an empty stretch of road is not an event. */
.corridor-note {
  margin: 0;
  padding: var(--s-4) var(--s-4) 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
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
/* §6.5 is 48; §11.2's 44 is a map-PIN exemption and does not reach a button that
   happens to sit on the map. */
.sleep-cta {
  margin: var(--s-2) var(--s-4) 0;
  min-height: 48px;
  border-radius: var(--r-control);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  color: var(--text-1);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.relay-banner {
  margin: var(--s-2) var(--s-4) 0;
  min-height: 48px; /* §6.5 glove spec — was 44 */
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
/* the same pill the preset row uses — no new component pattern (§22.2) */
.filters-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 40px;
  margin: 0 var(--s-4) var(--s-2);
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.filters-chip--on {
  border-color: var(--shield-500);
  color: var(--shield-500);
}
/* the relay banner's shape, one step quieter: the relay is time-critical (a spot is
   opening now) and takes the accent fill; a saved list is patient, so it takes the
   hairline card treatment the sleep CTA beside it already uses (§8). */
.saved-chip {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: var(--s-2) var(--s-4) 0;
  min-height: 48px;
  padding: 0 var(--s-3);
  border-radius: var(--r-control);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  color: var(--text-1);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.saved-chip__count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-3);
}
.saved {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.saved__row {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.saved__name {
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.saved__meta {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
/* §8 tertiary, wrapping — a row of text controls, never three stacked full-bleed
   buttons (the mistake §23 recorded on the Load tab's rung row) */
.saved__acts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1) var(--s-3);
  margin-top: var(--s-1);
}
/* §6.5 is 48 dp in BOTH axes, and only the height was set — so "Remove" measured
   44×48 in Punjabi, where the label is two glyphs. Exactly the defect already recorded
   on `.cap__chip`: a control sized by its content is sized by the SHORTEST locale, so
   height alone can never carry the glove spec. The harness found it at 360 dp. */
.saved__act {
  min-height: 48px;
  min-width: 48px;
  padding: 0 var(--s-2);
  margin-left: calc(var(--s-2) * -1);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.saved__act--rm {
  color: var(--flare-500);
}
.saved__hint {
  margin: var(--s-3) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
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
