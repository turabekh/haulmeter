<!-- AI-CONTEXT: "Where do I sleep tonight" solver (M8-FR3, PRD §8.8). One answer
     at day's end: the driver enters remaining HOS and the app ranks stops within
     range — guaranteed-bookable first (M6), then predicted availability (M1),
     then nearest — plus the cheapest fuel on the way (M7) and the guaranteed
     spot. Composed by the backend; this sheet just presents it. Live via api.js
     -> /intel/sleep; offline shows a sample plan. Distances in miles (never
     localized, F15). -->
<script setup>
import { ref } from "vue";
import { Star } from "lucide-vue-next";
import StatusPill from "./StatusPill.vue";
import { useI18n } from "../i18n.js";
import { formatMoney } from "../meter.js";
import { fetchSleepPlan } from "../api.js";
import { sampleSleepPlan } from "../fixtures.js";

const { t } = useI18n();

const hours = ref(3);
const plan = ref(null);
const busy = ref(false);

function miles(m) {
  return (m / 1609.344).toFixed(0);
}

async function find() {
  busy.value = true;
  try {
    // a real app centers on GPS; fixed center pending geolocation wiring
    plan.value = await fetchSleepPlan({
      lat: 32.7767,
      lon: -96.797,
      hosMinutesRemaining: Math.round(Number(hours.value || 0) * 60),
    });
  } catch {
    plan.value = sampleSleepPlan(); // unauthenticated / offline
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

    <template v-if="plan">
      <ul v-if="plan.stops.length" class="stops">
        <li v-for="s in plan.stops" :key="s.facility_id" class="stop">
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
          </div>
        </li>
      </ul>
      <p v-else class="muted">{{ t("sleep.empty") }}</p>

      <div v-if="plan.guaranteed" class="extra">
        <span class="extra__label">{{ t("sleep.guaranteed") }}</span>
        <span class="extra__val">
          {{ plan.guaranteed.property_name }} ·
          {{ formatMoney(plan.guaranteed.price_cents_per_night) }}
        </span>
      </div>
      <div v-if="plan.fuel" class="extra">
        <span class="extra__label">{{ t("sleep.fuel") }}</span>
        <span class="extra__val">
          {{ plan.fuel.name }} · {{ formatMoney(plan.fuel.net_cents_per_gal) }}/gal
        </span>
      </div>
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
  padding: var(--s-2) 0;
  border-bottom: 1px solid var(--line-1);
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
  gap: 2px;
}
.extra__label {
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.extra__val {
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.muted {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
</style>
