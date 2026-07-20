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
import { ref, reactive, computed } from "vue";
import { ArrowLeft } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { formatMoney } from "../core/meter.js";
import { calcTrueProfit } from "../core/api.js";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();

const form = reactive({
  revenue: 2000, // dollars
  miles: 500,
  tolls: 30, // dollars
  freeMin: 120,
  rateHr: 75, // dollars/hr
});
const result = ref(null);
const submitting = ref(false);

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
    receiver_facility_id: route.query.receiver || "00000000-0000-0000-0000-000000000000",
    free_time_minutes: Number(form.freeMin) || 0,
    rate_cents_per_hour: toCents(form.rateHr),
    origin_lat: Number(route.query.lat) || 32.7767,
    origin_lon: Number(route.query.lon) || -96.797,
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
      <button class="cta" type="submit" :disabled="submitting">{{ t("calc.calculate") }}</button>
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
