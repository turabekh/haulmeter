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
import { Navigation, SquareParking, Fuel, UtensilsCrossed } from "lucide-vue-next";
import { useRouter } from "vue-router";
import StatusPill from "./StatusPill.vue";
import { freshnessLabel, isStale, SCALE_TYPES } from "../presentation.js";
import { formatMoney } from "../meter.js";
import { useI18n } from "../i18n.js";
import {
  bucketLabelKey,
  cardVendors,
  presenceLabel,
  untilLabel,
  verificationPresentation,
} from "../vendors.js";

const props = defineProps({
  pin: { type: Object, required: true },
  // M13-FR3: vendors discoverable at this facility, already Q-3 ranked by the
  // server. Q-7: an EMPTY list means the section does not render at all — no
  // "nothing here yet!" filler on a card a driver reads in ten seconds.
  vendors: { type: Array, default: () => [] },
  // FR6 / Q-3: promoted content arrives as a SEPARATE prop and renders in its own
  // labelled container below the ranked list. It is never spliced into `vendors`.
  promotions: { type: Array, default: () => [] },
});
const emit = defineEmits([
  "navigate",
  "report",
  "report-price",
  "book",
  "fuel",
  "handoff",
  "vendor",
]);
const { t } = useI18n();
const router = useRouter();

function viewFacility() {
  router.push(`/facility/${props.pin.facility_id}`);
}

const now = Date.now();
const fresh = computed(() => freshnessLabel(props.pin.freshness, now, { feed: t("freshness.feed") }));
const stale = computed(() => isStale(props.pin.freshness, now));
const grossFuel = computed(() => props.pin.badges?.find((b) => b.kind === "fuel_price")?.value ?? null);
const isFuel = computed(() => props.pin.facility_type === "fuel_station");
// TPIMS availability: the "Low" category or an int count, with capacity alongside —
// "Low" is shown verbatim, NEVER parsed to a number (condition A). Absent otherwise.
const availability = computed(() => {
  const a = props.pin.availability;
  if (a === null || a === undefined) return null;
  const cap = props.pin.capacity;
  return cap ? `${a} · ${cap} ${t("facility.spots")}` : `${a} ${t("facility.spots")}`;
});
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
// "net" means AFTER the network discount — only a network station earns that word.
// A crowd-reported pump price or an EIA area estimate is just a per-gallon price.
const fuelUnit = computed(() => (fuelNet.value?.is_network ? `${t("fuel.net")}/gal` : "/gal"));
// honest provenance under the price: net savings (network), reported age +
// contributor count (crowd, §11.7), or an EIA regional-average disclaimer.
const fuelSource = computed(() => {
  const b = fuelNet.value;
  if (!b || b.is_network) return null; // network shows the savings pill instead
  if (b.source === "crowd") {
    return freshnessLabel({ reported_at: b.as_of, sample_size: b.sample_size }, now) ?? t("fuel.reported");
  }
  if (b.source === "regional") {
    // §11.7 honesty: label the EIA period (data time), not ingest time — "regional
    // avg · wk of Jul 20". as_of is the week_of date (YYYY-MM-DD).
    const wk = b.as_of
      ? ` · ${t("fuel.week_of")} ${new Date(b.as_of + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}`
      : "";
    return `${t("fuel.regional_avg")}${wk}`;
  }
  return null;
});
const fuelIndicative = computed(() => fuelNet.value?.indicative === true);
// M7-FR5 empty state (§15.3): a fuel station priced only by the EIA regional
// estimate (no network feed, no crowd consensus) leads with a "be the first"
// nudge into the price-report sheet — the regional line stays as secondary
// context (§11.7 honesty), and the crowd report displaces the baseline over time.
const fuelEstimateOnly = computed(() => isFuel.value && fuelNet.value?.source === "regional");
// M10: a free public lot can relay a "leaving soon" spot handoff (never M6).
const freeLot = computed(() =>
  ["truck_stop", "rest_area"].includes(props.pin.facility_type),
);
// status reporting only makes sense where the facility HAS a status a passing driver
// can see — never on a fuel station or a receiver dock (their crowd signal is price /
// dock-time). E3.1 adds scales, which are asked whether they are open rather than how
// full they are; ReportSheet derives that from the type, so the affordance is shared.
const reportable = computed(() =>
  ["truck_stop", "rest_area", "parking_property"].includes(props.pin.facility_type) ||
  SCALE_TYPES.has(props.pin.facility_type),
);
const unknownScale = computed(
  () => SCALE_TYPES.has(props.pin.facility_type) && !props.pin.status,
);

// Q-6: at most two here; the rest stay reachable behind "all vendors" in the sheet.
// The server already caps, but a card that rendered whatever it was handed would be
// one API change away from making the map louder — and food enriches pins, it never
// decorates the canvas.
const shownVendors = computed(() => cardVendors(props.vendors));
const moreVendors = computed(() => Math.max(0, props.vendors.length - shownVendors.value.length));

function vendorLine(entry) {
  // §11.7: "3 drivers · 20m" for a crowd confirmation, "vendor says here" for the
  // vendor's own claim. presenceLabel refuses to produce a count for the latter.
  return presenceLabel(entry.presence, now, { vendorSays: t("vendor.says_here") });
}
</script>

<template>
  <div class="fac">
    <h3 class="fac__name">{{ pin.name }}</h3>
    <div class="fac__row">
      <StatusPill v-if="pin.status" :status="pin.status" :hollow="stale" />
      <span v-if="availability" class="fac__avail">{{ availability }}</span>
      <span v-if="fresh" class="fac__fresh">{{ fresh }}</span>
      <!-- §11.7: for a scale, "nobody has said" is a fact worth stating. Silence on a
           card whose whole purpose is open-or-closed reads as "closed" to a tired
           driver, which is exactly the reading that would send them past a live one. -->
      <span v-else-if="unknownScale" class="fac__fresh">{{ t("facility.no_report") }}</span>
    </div>

    <!-- M7: NET price leads for a fuel-network station; savings called out (§12.2).
         Crowd/regional prices show the same figure with an honest source label. -->
    <div v-if="fuelNet" class="fac__fuel">
      <span class="fac__fuel-figure">{{ fuelIndicative ? "~" : "" }}{{ formatMoney(fuelNet.net) }}</span>
      <span class="fac__fuel-label">{{ fuelUnit }}</span>
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

    <!-- M7-FR5 empty state: only a regional estimate here -> invite the first real
         report (§15.3), keeping the regional line above as secondary context -->
    <p v-if="fuelEstimateOnly" class="fac__nudge">{{ t("fuel.be_first") }}</p>

    <!-- M13-FR3 vendor section. Q-7: absent entirely when there is nothing to show,
         so an ordinary truck stop's card is exactly as quiet as it was before. -->
    <section v-if="shownVendors.length" class="fac__vendors">
      <h4 class="fac__vendors-title">
        <UtensilsCrossed :size="16" :stroke-width="2" aria-hidden="true" />
        {{ t("vendor.section_title") }}
      </h4>
      <button
        v-for="v in shownVendors"
        :key="v.vendor_id"
        class="vendor"
        type="button"
        @click="emit('vendor', v)"
      >
        <span class="vendor__name">{{ v.name }}</span>
        <span class="vendor__when">
          {{ t(bucketLabelKey(v.bucket)) }} · {{ t("vendor.until") }} {{ untilLabel(v.ends_at) }}
        </span>
        <span class="vendor__meta">
          <span :style="{ color: `var(${verificationPresentation(v.verify_status).token})` }">
            {{ t(verificationPresentation(v.verify_status).labelKey) }}
          </span>
          <span v-if="vendorLine(v)" class="vendor__fresh">{{ vendorLine(v) }}</span>
          <span v-if="v.sold_out" class="vendor__soldout">{{ t("vendor.sold_out") }}</span>
        </span>
      </button>
      <button
        v-if="moreVendors"
        class="cta cta--tertiary"
        type="button"
        @click="emit('vendor', null)"
      >
        {{ t("vendor.all") }} ({{ vendors.length }})
      </button>

      <!-- the labelled slot. Below the organic list, its own container, always
           carrying the label — never blended into the ranking above (Q-3). -->
      <div v-for="p in promotions" :key="p.promotion_id" class="promo">
        <span class="promo__label">{{ t("vendor.promoted") }}</span>
        <span class="promo__text">{{ p.vendor_name }} · {{ p.text }}</span>
      </div>
    </section>

    <!-- contextual lead action -->
    <button v-if="bookable" class="cta" type="button" @click="emit('book', pin)">
      <SquareParking :size="20" :stroke-width="2" aria-hidden="true" />
      {{ bookLabel }}
    </button>
    <button v-else-if="fuelable" class="cta" type="button" @click="emit('fuel', pin)">
      <Fuel :size="20" :stroke-width="2" aria-hidden="true" />
      {{ t("facility.fuel_here") }}
    </button>
    <button
      v-else-if="fuelEstimateOnly"
      class="cta"
      type="button"
      @click="emit('report-price', pin)"
    >
      <Fuel :size="20" :stroke-width="2" aria-hidden="true" />
      {{ t("facility.report_price") }}
    </button>
    <button v-else class="cta" type="button" @click="emit('navigate', pin)">
      <Navigation :size="20" :stroke-width="2" aria-hidden="true" />
      {{ t("facility.navigate") }}
    </button>

    <!-- secondary: Navigate whenever it isn't the lead; Report only where parking
         is a thing (never a fuel station or a receiver dock) -->
    <button
      v-if="bookable || fuelable || fuelEstimateOnly"
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
         crowd consensus that displaces the regional baseline on this station's pin.
         When only a regional estimate exists the report action already LEADS, so we
         don't repeat it here (fuelEstimateOnly). -->
    <button
      v-if="isFuel && !fuelEstimateOnly"
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
.fac__avail {
  color: var(--text-2);
  font-size: var(--type-caption-size);
  font-variant-numeric: tabular-nums;
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
/* §15.3 empty state: one sentence of purpose inviting the first price report */
.fac__nudge {
  margin: var(--s-3) 0 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
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
/* M13: the food section is a quiet list, not a second card — it must never
   compete with the facility's own status line or its primary action (§7.4) */
.fac__vendors {
  margin-top: var(--s-4);
  padding-top: var(--s-3);
  border-top: 1px solid var(--line-1);
}
.fac__vendors-title {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0 0 var(--s-2);
  color: var(--text-2);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.vendor {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  min-height: 64px;
  padding: var(--s-2) 0;
  background: transparent;
  text-align: left;
}
.vendor__name {
  color: var(--text-1);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.vendor__when {
  color: var(--text-2);
  font-size: var(--type-caption-size);
  font-variant-numeric: tabular-nums;
}
.vendor__meta {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--type-caption-size);
}
.vendor__fresh {
  color: var(--text-3);
}
.vendor__soldout {
  margin-left: auto;
  padding: 2px var(--s-2);
  border-radius: var(--r-pill);
  background: var(--ink-2, var(--line-1));
  color: var(--text-2);
}
/* the promoted slot reads quieter than the organic rows above it: caption type,
   secondary text, and the label carries the marker token already in the system */
.promo {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  margin-top: var(--s-3);
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
}
.promo__label {
  flex: 0 0 auto;
  padding: 2px var(--s-2);
  border-radius: var(--r-pill);
  background: var(--ink-2, var(--line-1));
  color: var(--marker-500);
  font-size: var(--type-caption-size);
  font-weight: 500;
}
.promo__text {
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
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
