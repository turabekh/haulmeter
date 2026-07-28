<!-- AI-CONTEXT: True-profit load calculator (M8-FR1, PRD §8.8). A full-screen
     LINEAR form (NAV-3 / §202: one input per line, 56 dp, numeric keypad,
     labels above fields). The driver enters the load; the result is the TRUE
     profit — rate minus route fuel (M7 net price), tolls, and the expected
     detention this receiver costs (M8 values each historical stop with the M3
     clock, then averages). The headline is a Meter-treatment figure (Mono,
     ledger-green when it clears, flare when it doesn't), with rate-per-mile
     AFTER dwell and a transparent breakdown + basis (§11.7, never fake
     precision). Live via api.js; offline it degrades honestly (fuel + dwell
     need a session, and it says so). -->
<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import { ArrowLeft } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { formatMoney } from "../core/meter.js";
import { calcTrueProfit, activeStopId, fetchMeter } from "../core/api.js";
import { lastFix } from "../core/location.js";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const { isDriving } = useDriverState();

const form = reactive({
  revenue: 2000, // dollars
  miles: 500,
  tolls: 30, // dollars
  freeMin: 120,
  rateHr: 75, // dollars/hr
});
const result = ref(null);
const submitting = ref(false);

// AI-CONTEXT: the load this calculator was opened FROM (§23 entry 85).
//
// It is reached from the Load tab's More sheet as a bare `/load/calc` — no query
// params — while reading `route.query.receiver`, `.lat` and `.lon` and falling back to
// the NIL UUID and a hardcoded Dallas. Those three parameters have never been supplied
// by anything, so every true-profit figure computed in production valued detention at a
// facility that does not exist and routed fuel from a city the driver was not in.
//
// The load knows its own Rate, its free time, its detention rate and its receiver.
// Asking a driver to retype the first while defaulting the fourth to nothing is the
// same shape as the rate con parsed into fields nobody read.
const prefilled = ref(false);
const loadFacility = ref(null);

onMounted(async () => {
  if (!activeStopId.value) return; // pre-acceptance use: nothing to prefill from
  try {
    const meter = await fetchMeter(activeStopId.value);
    loadFacility.value = meter.facility_id ?? null;
    // §11.7: prefill only what the load actually STATES. A rate con silent on the
    // linehaul leaves the field as it was rather than gaining a confident zero.
    if (meter.rate_cents) {
      form.revenue = (meter.rate_cents / 100).toFixed(2);
      prefilled.value = true;
    }
    if (meter.free_time_minutes != null) form.freeMin = meter.free_time_minutes;
    if (meter.rate_cents_per_hour != null) {
      form.rateHr = Math.round(meter.rate_cents_per_hour / 100);
    }
  } catch {
    /* offline / no session: the form keeps its own defaults and says nothing it
       cannot support — the calculation itself already degrades honestly below */
  }
});

function toCents(dollars) {
  return Math.round(Number(dollars || 0) * 100);
}

async function calculate() {
  submitting.value = true;
  const payload = {
    revenue_cents: toCents(form.revenue),
    loaded_miles: Number(form.miles) || 0,
    mpg: 6.0,
    tolls_cents: toCents(form.tolls),
    // the dock this load is actually going to, before the query param nothing sets
    // and before the nil UUID that made the detention estimate meaningless
    receiver_facility_id:
      loadFacility.value || route.query.receiver || "00000000-0000-0000-0000-000000000000",
    free_time_minutes: Number(form.freeMin) || 0,
    rate_cents_per_hour: toCents(form.rateHr),
    // where the driver IS, which is what a route-fuel estimate is measured from. The
    // Dallas constant behind it is the same invented coordinate §23 entry 67 removed
    // from the import sheet; it stays only as the last resort on a device with no fix.
    // `||` rather than `??` on the query fallback: an absent param makes `Number()`
    // return NaN, which `??` would happily pass through as an origin.
    origin_lat: lastFix.value?.lat ?? (Number(route.query.lat) || 32.7767),
    origin_lon: lastFix.value?.lon ?? (Number(route.query.lon) || -96.797),
  };
  try {
    result.value = await calcTrueProfit(payload);
  } catch {
    // offline / no session: honest local estimate — fuel + dwell need live data
    const miles = payload.loaded_miles;
    const net = payload.revenue_cents - payload.tolls_cents;
    result.value = {
      revenue_cents: payload.revenue_cents,
      fuel_cost_cents: null,
      tolls_cents: payload.tolls_cents,
      expected_detention_cents: null,
      net_cents: net,
      rpm_after_cents: miles ? Math.round(net / miles) : 0,
      fuel_net_cents_per_gal: null,
      basis: { fuel: "needs_session", detention_sample_size: 0 },
    };
  }
  submitting.value = false;
}

const clears = computed(() => (result.value?.net_cents ?? 0) >= 0);
</script>

<template>
  <div class="calc">
    <header class="calc__head">
      <button class="back" type="button" aria-label="Back" @click="router.back()">
        <ArrowLeft :size="24" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="calc__title">{{ t("calc.title") }}</h1>
    </header>

    <form class="fields" @submit.prevent="calculate">
      <label class="field">
        <span class="field__label">{{ t("calc.revenue") }}</span>
        <input v-model="form.revenue" class="field__input" type="number" inputmode="decimal" min="0" />
        <!-- §11.7: the figure NAMES WHO IS SPEAKING. A rate carried over from the load
             and a rate the driver typed carry different confidence, and only the driver
             knows whether the contract is right. Editable either way — this is a
             calculator, not a record. -->
        <span v-if="prefilled" class="field__from">{{ t("calc.from_load") }}</span>
      </label>
      <label class="field">
        <span class="field__label">{{ t("calc.miles") }}</span>
        <input v-model="form.miles" class="field__input" type="number" inputmode="numeric" min="0" />
      </label>
      <label class="field">
        <span class="field__label">{{ t("calc.tolls") }}</span>
        <input v-model="form.tolls" class="field__input" type="number" inputmode="decimal" min="0" />
      </label>
      <label class="field">
        <span class="field__label">{{ t("calc.free_min") }}</span>
        <input v-model="form.freeMin" class="field__input" type="number" inputmode="numeric" min="0" />
      </label>
      <label class="field">
        <span class="field__label">{{ t("calc.rate_hr") }}</span>
        <input v-model="form.rateHr" class="field__input" type="number" inputmode="decimal" min="0" />
      </label>
      <!-- SM-3: a form of number fields is the definition of an interactive
           prompt at speed (Forbidden #11). -->
      <p v-if="isDriving" class="driving-note">{{ t("driving.paused") }}</p>
      <button v-else class="cta" type="submit" :disabled="submitting">{{ t("calc.calculate") }}</button>
    </form>

    <section v-if="result" class="result">
      <div class="result__meter">
        <span class="result__label">{{ t("calc.net") }}</span>
        <span class="result__figure" :class="clears ? 'pos' : 'neg'">{{ formatMoney(result.net_cents) }}</span>
        <span class="result__rpm">{{ formatMoney(result.rpm_after_cents) }} {{ t("calc.rpm") }}</span>
      </div>
      <ul class="breakdown">
        <li class="breakdown__row">
          <span>{{ t("calc.revenue") }}</span>
          <span class="mono">{{ formatMoney(result.revenue_cents) }}</span>
        </li>
        <li class="breakdown__row">
          <span>{{ t("calc.fuel") }}</span>
          <span class="mono neg">{{ result.fuel_cost_cents === null ? "—" : "−" + formatMoney(result.fuel_cost_cents) }}</span>
        </li>
        <li class="breakdown__row">
          <span>{{ t("calc.tolls") }}</span>
          <span class="mono neg">−{{ formatMoney(result.tolls_cents) }}</span>
        </li>
        <li class="breakdown__row">
          <span>{{ t("calc.detention") }}</span>
          <span class="mono neg">{{ result.expected_detention_cents === null ? "—" : "−" + formatMoney(result.expected_detention_cents) }}</span>
        </li>
      </ul>
      <p class="basis">
        {{ result.basis.detention_sample_size }} {{ t("profile.stops_basis") }}
      </p>
    </section>
  </div>
</template>

<style scoped>
.calc {
  padding: var(--s-4);
}
.calc__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-bottom: var(--s-4);
}
.back {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-1);
}
.calc__title {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.fields {
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
/* provenance, in the same quiet register the Load tab uses for the appointment's
   source — a caption under the figure, never a badge competing with it */
.field__from {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-caption-line);
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
  margin-top: var(--s-2);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta:disabled {
  opacity: 0.6;
}
.result {
  margin-top: var(--s-5);
}
.result__meter {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-1);
  padding: var(--s-4) 0;
}
.result__label {
  font-size: var(--type-label-size);
  color: var(--text-2);
}
.result__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-meter-size);
  line-height: var(--type-meter-line);
  font-weight: var(--type-meter-weight);
}
.result__figure.pos {
  color: var(--ledger-500);
}
.result__figure.neg {
  color: var(--flare-500);
}
.result__rpm {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.breakdown {
  list-style: none;
  margin: var(--s-3) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.breakdown__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: var(--s-2) 0;
  border-bottom: 1px solid var(--line-1);
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.mono.neg {
  color: var(--text-2);
}
.basis {
  margin: var(--s-3) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
</style>
