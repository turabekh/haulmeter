<!-- AI-CONTEXT: Facility card content (design-prd §10.1) shown inside the pin
     bottom sheet. Glanceable: name + status pill + freshness (§11.7) + fuel
     figure (Mono, §6.2 T-2) + ONE primary action (§Principle 4 / §227: the
     parking sheet's single CTA is contextual — Book / Navigate). A bookable
     parking_property (M6) leads with "Book spot — $XX" (§12.2: the button says
     exactly what happens; ONE final price, §Anti-pattern 8 no hidden fees) and
     deep-links to the full-screen booking checkout (NAV-3/NAV-5). Otherwise the
     lead is Navigate, the external-nav deep-link handoff (M1-FR8). -->
<script setup>
import { computed } from "vue";
import { Navigation, SquareParking } from "lucide-vue-next";
import { useRouter } from "vue-router";
import StatusPill from "./StatusPill.vue";
import { freshnessLabel, isStale } from "../presentation.js";
import { formatMoney } from "../meter.js";
import { useI18n } from "../i18n.js";

const props = defineProps({
  pin: { type: Object, required: true },
});
const emit = defineEmits(["navigate", "report", "book"]);
const { t } = useI18n();
const router = useRouter();

function viewFacility() {
  router.push(`/facility/${props.pin.facility_id}`);
}

const now = Date.now();
const fresh = computed(() => freshnessLabel(props.pin.freshness, now));
const stale = computed(() => isStale(props.pin.freshness, now));
const fuel = computed(() => props.pin.badges?.find((b) => b.kind === "fuel_price")?.value ?? null);
// M6: a bookable badge carries the take-inclusive nightly price in cents.
const nightlyCents = computed(() => props.pin.badges?.find((b) => b.kind === "bookable")?.value ?? null);
const bookable = computed(() => nightlyCents.value !== null);
const bookLabel = computed(() => `${t("facility.book")} — ${formatMoney(nightlyCents.value)}`);
</script>

<template>
  <div class="fac">
    <h3 class="fac__name">{{ pin.name }}</h3>
    <div class="fac__row">
      <StatusPill v-if="pin.status" :status="pin.status" :hollow="stale" />
      <span v-if="fresh" class="fac__fresh">{{ fresh }}</span>
    </div>
    <div v-if="fuel !== null" class="fac__fuel">
      <span class="fac__fuel-figure">${{ fuel.toFixed(2) }}</span>
      <span class="fac__fuel-label">{{ t("facility.fuel") }}</span>
    </div>

    <!-- bookable parking leads with Book; everyone else leads with Navigate -->
    <button v-if="bookable" class="cta" type="button" @click="emit('book', pin)">
      <SquareParking :size="20" :stroke-width="2" aria-hidden="true" />
      {{ bookLabel }}
    </button>
    <button v-else class="cta" type="button" @click="emit('navigate', pin)">
      <Navigation :size="20" :stroke-width="2" aria-hidden="true" />
      {{ t("facility.navigate") }}
    </button>

    <button
      v-if="bookable"
      class="cta cta--secondary"
      type="button"
      @click="emit('navigate', pin)"
    >
      {{ t("facility.navigate") }}
    </button>
    <button v-else class="cta cta--secondary" type="button" @click="emit('report', pin)">
      {{ t("map.report") }}
    </button>
    <button class="cta cta--tertiary" type="button" @click="viewFacility">
      {{ t("facility.view") }}
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
.fac__fuel-figure {
  font-family: var(--font-mono);
  font-size: var(--type-title-size);
  font-variant-numeric: tabular-nums;
}
.fac__fuel-label {
  color: var(--text-2);
  font-size: var(--type-caption-size);
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
