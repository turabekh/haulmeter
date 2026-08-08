<!-- AI-CONTEXT: "Where do I sleep tonight" solver (M8-FR3, PRD §8.8). One answer
     at day's end: the driver enters remaining HOS and the app ranks stops within
     range — guaranteed-bookable first (M6), then predicted availability (M1),
     then nearest — plus the cheapest fuel on the way (M7) and the guaranteed
     spot. Composed by the backend; this sheet just presents it. Live via api.js
     -> /intel/sleep, on the four-state model — it used to answer a failed lookup with
     an invented plan naming lots that may not exist (§23 entry 131). Distances in miles (never
     localized, F15). -->
<script setup>
import { ref } from "vue";
import { Star, ChevronRight } from "lucide-vue-next";
import { useRouter } from "vue-router";
import StatusPill from "./StatusPill.vue";
import { useI18n } from "../i18n.js";
import { formatMoney } from "../meter.js";
import { fetchSleepPlan } from "../api.js";
import SkeletonRow from "./SkeletonRow.vue";
import { LoadState, Failure, failureOf } from "../load-state.js";

const { t } = useI18n();
const router = useRouter();

// results are actionable: a stop -> its facility profile; the guaranteed spot ->
// straight into the booking checkout
function goFacility(id) {
  if (id) router.push(`/facility/${id}`);
}
function goBook(g) {
  router.push({
    name: "book",
    params: { spotId: g.spot_id },
    query: { name: g.property_name, nightly: g.price_cents_per_night },
  });
}

const hours = ref(3);
const plan = ref(null);
// AI-CONTEXT: §23 entry 131. Like the audit, this is asked for rather than loaded on
// mount, so `null` state means "not asked yet" and shows the form alone.
const planState = ref(null);
const planFailure = ref(null);
const busy = ref(false);

function miles(m) {
  return (m / 1609.344).toFixed(0);
}

async function find() {
  busy.value = true;
  planState.value = LoadState.LOADING;
  try {
    // a real app centers on GPS; fixed center pending geolocation wiring
    plan.value = await fetchSleepPlan({
      lat: 32.7767,
      lon: -96.797,
      hosMinutesRemaining: Math.round(Number(hours.value || 0) * 60),
    });
    planState.value = LoadState.LOADED;
    planFailure.value = null;
  } catch (e) {
    // this answered with `sampleSleepPlan()` — invented lots, with invented prices and
    // an invented guaranteed spot, to a driver deciding where to spend the night on
    // the hours they have left. §11.7's worst shape: a place that is not there.
    plan.value = null;
    planFailure.value = failureOf(e);
    planState.value = LoadState.FAILED;
  }
  busy.value = false;
}
</script>

<template>
  <div class="sleep">
    <label class="field">
      <span class="field__label">{{ t("sleep.hours") }}</span>
      <input v-model="hours" class="field__input" type="number" inputmode="decimal" min="0" max="11" />
    </label>
    <button class="cta" type="button" :disabled="busy" @click="find">{{ t("sleep.find") }}</button>

    <SkeletonRow v-if="planState === LoadState.LOADING" :count="3" />
    <p v-else-if="planState === LoadState.FAILED" class="sleep__failed">
      {{ planFailure === Failure.OFFLINE ? t("system.load_offline") : t("sleep.load_failed") }}
      <button class="sleep__retry" type="button" @click="find">{{ t("system.retry") }}</button>
    </p>
    <template v-else-if="plan">
      <ul v-if="plan.stops.length" class="stops">
        <li v-for="s in plan.stops" :key="s.facility_id">
          <button class="stop" type="button" @click="goFacility(s.facility_id)">
            <div class="stop__main">
              <Star
                v-if="s.guaranteed_bookable"
                :size="16"
                :stroke-width="2"
                class="stop__star"
                aria-hidden="true"
              />
              <span class="stop__name">{{ s.name }}</span>
            </div>
            <div class="stop__right">
              <StatusPill v-if="s.predicted_status" :status="s.predicted_status" />
              <span class="stop__dist">{{ miles(s.distance_m) }} mi</span>
              <ChevronRight :size="16" :stroke-width="2" class="stop__chev" aria-hidden="true" />
            </div>
          </button>
        </li>
      </ul>
      <p v-else class="muted">{{ t("sleep.empty") }}</p>

      <button v-if="plan.guaranteed" class="extra" type="button" @click="goBook(plan.guaranteed)">
        <span class="extra__label">{{ t("sleep.guaranteed") }}</span>
        <span class="extra__val">
          {{ plan.guaranteed.property_name }} ·
          {{ formatMoney(plan.guaranteed.price_cents_per_night) }}
          <ChevronRight :size="15" :stroke-width="2" class="stop__chev" aria-hidden="true" />
        </span>
      </button>
      <button v-if="plan.fuel" class="extra" type="button" @click="goFacility(plan.fuel.facility_id)">
        <span class="extra__label">{{ t("sleep.fuel") }}</span>
        <span class="extra__val">
          {{ plan.fuel.name }} · {{ formatMoney(plan.fuel.net_cents_per_gal) }}/gal
          <ChevronRight :size="15" :stroke-width="2" class="stop__chev" aria-hidden="true" />
        </span>
      </button>
    </template>
  </div>
</template>

<style scoped>
.sleep {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.field__label {
  font-size: var(--type-label-size);
  color: var(--text-2);
}
.field__input {
  min-height: 56px;
  padding: 0 var(--s-3);
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  color: var(--text-1);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-body-size);
}
.cta {
  width: 100%;
  min-height: 56px;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta:disabled {
  opacity: 0.6;
}
.sleep__failed {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: var(--s-3) 0 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.sleep__retry {
  min-height: 48px;
  padding: 0 var(--s-2);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
.stops {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.stop {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  width: 100%;
  padding: var(--s-2) 0;
  border: none;
  border-bottom: 1px solid var(--line-1);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.stop:hover .stop__name,
.stop:hover .stop__chev {
  color: var(--accent-fill);
}
.stop__chev {
  color: var(--text-3);
  flex: none;
}
.stop__main {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-width: 0;
}
.stop__star {
  color: var(--marker-500);
  flex: none;
}
.stop__name {
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.stop__right {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex: none;
}
.stop__dist {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.extra {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  width: 100%;
  padding: var(--s-2) 0;
  border: none;
  border-top: 1px solid var(--line-1);
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.extra__label {
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.extra__val {
  display: flex;
  align-items: center;
  gap: var(--s-1);
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.extra:hover .extra__val {
  color: var(--accent-fill);
}
.muted {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
</style>
