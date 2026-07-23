<!-- AI-CONTEXT: Facility card content (design-prd §10.1) shown inside the pin
     bottom sheet. Glanceable: name + status pill + freshness (§11.7) + a money
     figure (Mono, §6.2 T-2) + ONE contextual primary action (§Principle 4 /
     §227). The lead action is contextual by facility:
       · bookable parking_property (M6) -> "Book spot — $XX" (§12.2, one price)
       · fuel-network station (M7)       -> "Fuel here" with the NET price shown
       · everything else                 -> Navigate (external-nav handoff, M1-FR8)
     Each deep-links (NAV-5) to its full-screen flow; Navigate always stays
     reachable as the secondary. A fuel station always shows its best price with an
     HONEST source label — network net, crowd-reported + freshness (§11.7), or an
     EIA regional average — and a "Report diesel price" action feeds the crowd layer
     (M7-FR5), so real per-station prices displace the regional baseline over time. -->
<script setup>
import { computed } from "vue";
import { Navigation, SquareParking, Fuel } from "lucide-vue-next";
import { useRouter } from "vue-router";
import StatusPill from "./StatusPill.vue";
import { freshnessLabel, isStale } from "../presentation.js";
import { formatMoney } from "../meter.js";
import { useI18n } from "../i18n.js";

const props = defineProps({
  pin: { type: Object, required: true },
});
const emit = defineEmits(["navigate", "report", "report-price", "book", "fuel", "handoff"]);
const { t } = useI18n();
const router = useRouter();

function viewFacility() {
  router.push(`/facility/${props.pin.facility_id}`);
}

const now = Date.now();
const fresh = computed(() => freshnessLabel(props.pin.freshness, now));
const stale = computed(() => isStale(props.pin.freshness, now));
const grossFuel = computed(() => props.pin.badges?.find((b) => b.kind === "fuel_price")?.value ?? null);
const isFuel = computed(() => props.pin.facility_type === "fuel_station");
// M6: a bookable badge carries the take-inclusive nightly price in cents.
const nightlyCents = computed(() => props.pin.badges?.find((b) => b.kind === "bookable")?.value ?? null);
const bookable = computed(() => nightlyCents.value !== null);
// a parking property with no bookable badge is fully booked tonight — say so,
// rather than silently dropping the Book button (M6 availability)
const parkingFull = computed(
  () => props.pin.facility_type === "parking_property" && !bookable.value,
);
const bookLabel = computed(() => `${t("facility.book")} — ${formatMoney(nightlyCents.value)}`);
// M7: a fuel_net badge carries {net, gross, savings, is_network, source, as_of,
// sample_size} in cents. `source` is "feed" (network), "crowd", or "regional".
const fuelNet = computed(() => props.pin.badges?.find((b) => b.kind === "fuel_net") ?? null);
const fuelable = computed(() => !!fuelNet.value?.is_network);
// honest provenance under the price: net savings (network), reported age +
// contributor count (crowd, §11.7), or an EIA regional-average disclaimer.
const fuelSource = computed(() => {
  const b = fuelNet.value;
  if (!b || b.is_network) return null; // network shows the savings pill instead
  if (b.source === "crowd") {
    return freshnessLabel({ reported_at: b.as_of, sample_size: b.sample_size }, now) ?? t("fuel.reported");
  }
  if (b.source === "regional") return t("fuel.regional_avg");
  return null;
});
const fuelIndicative = computed(() => fuelNet.value?.indicative === true);
// M10: a free public lot can relay a "leaving soon" spot handoff (never M6).
const freeLot = computed(() =>
  ["truck_stop", "rest_area"].includes(props.pin.facility_type),
);
// parking full/empty reporting only makes sense where there IS parking — never
// on a fuel station or a receiver dock (their crowd signal is price / dock-time)
const reportable = computed(() =>
  ["truck_stop", "rest_area", "parking_property"].includes(props.pin.facility_type),
);
</script>

<template>
  <div class="fac">
    <h3 class="fac__name">{{ pin.name }}</h3>
    <div class="fac__row">
      <StatusPill v-if="pin.status" :status="pin.status" :hollow="stale" />
      <span v-if="fresh" class="fac__fresh">{{ fresh }}</span>
    </div>

    <!-- M7: NET price leads for a fuel-network station; savings called out (§12.2).
         Crowd/regional prices show the same figure with an honest source label. -->
    <div v-if="fuelNet" class="fac__fuel">
      <span class="fac__fuel-figure">{{ fuelIndicative ? "~" : "" }}{{ formatMoney(fuelNet.net) }}</span>
      <span class="fac__fuel-label">{{ t("fuel.net") }}/gal</span>
      <span v-if="fuelNet.savings > 0" class="fac__save">{{ t("fuel.save") }} {{ fuelNet.savings }}¢</span>
      <span v-else-if="fuelSource" class="fac__fuel-src">{{ fuelSource }}</span>
    </div>
    <div v-else-if="grossFuel !== null" class="fac__fuel">
      <span class="fac__fuel-figure">${{ grossFuel.toFixed(2) }}</span>
      <span class="fac__fuel-label">{{ t("facility.fuel") }}</span>
    </div>

    <!-- M6: a fully-booked lot says so (no silent missing button) -->
    <div v-if="parkingFull" class="fac__full">
      <SquareParking :size="16" :stroke-width="2" aria-hidden="true" />
      {{ t("facility.fully_booked") }}
    </div>

    <!-- contextual lead action -->
    <button v-if="bookable" class="cta" type="button" @click="emit('book', pin)">
      <SquareParking :size="20" :stroke-width="2" aria-hidden="true" />
      {{ bookLabel }}
    </button>
    <button v-else-if="fuelable" class="cta" type="button" @click="emit('fuel', pin)">
      <Fuel :size="20" :stroke-width="2" aria-hidden="true" />
      {{ t("facility.fuel_here") }}
    </button>
    <button v-else class="cta" type="button" @click="emit('navigate', pin)">
      <Navigation :size="20" :stroke-width="2" aria-hidden="true" />
      {{ t("facility.navigate") }}
    </button>

    <!-- secondary: Navigate whenever it isn't the lead; Report only where parking
         is a thing (never a fuel station or a receiver dock) -->
    <button
      v-if="bookable || fuelable"
      class="cta cta--secondary"
      type="button"
      @click="emit('navigate', pin)"
    >
      {{ t("facility.navigate") }}
    </button>
    <button
      v-else-if="reportable"
      class="cta cta--secondary"
      type="button"
      @click="emit('report', pin)"
    >
      {{ t("map.report") }}
    </button>
    <!-- M7-FR5: any driver at the pump can report the diesel price; 3 reports form a
         crowd consensus that displaces the regional baseline on this station's pin -->
    <button
      v-if="isFuel"
      class="cta cta--secondary"
      type="button"
      @click="emit('report-price', pin)"
    >
      <Fuel :size="18" :stroke-width="2" aria-hidden="true" />
      {{ t("facility.report_price") }}
    </button>
    <button class="cta cta--tertiary" type="button" @click="viewFacility">
      {{ t("facility.view") }}
    </button>
    <!-- M10-FR2: at a free lot you're leaving, hand your spot to a nearby driver -->
    <button v-if="freeLot" class="cta cta--tertiary" type="button" @click="emit('handoff', pin)">
      {{ t("handoff.leaving") }}
    </button>
  </div>
</template>

<style scoped>
.fac__name {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.fac__row {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-2);
}
.fac__fresh {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.fac__fuel {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  margin-top: var(--s-3);
}
.fac__full {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-3);
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-control);
  background: var(--ink-2, var(--line-1));
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.fac__fuel-figure {
  font-family: var(--font-mono);
  font-size: var(--type-title-size);
  font-variant-numeric: tabular-nums;
}
.fac__fuel-label {
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
/* §11.7: honest provenance under a non-network price (crowd age / regional avg) */
.fac__fuel-src {
  margin-left: auto;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.fac__save {
  margin-left: auto;
  padding: 2px var(--s-2);
  border-radius: var(--r-pill);
  background: var(--ledger-500);
  color: var(--on-accent);
  font-size: var(--type-caption-size);
  font-weight: 500;
}
.cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-4);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta--secondary {
  margin-top: var(--s-2);
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
}
/* tertiary = text button (§8), the cross-link verb to the facility scorecard (NAV-5) */
.cta--tertiary {
  margin-top: var(--s-2);
  min-height: 48px;
  background: transparent;
  color: var(--shield-500);
}
</style>
