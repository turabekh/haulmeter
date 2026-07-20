<!-- AI-CONTEXT: Money tab (design-prd §10.3) — the driver's P&L with the platform.
     Anatomy at 360 dp: month summary in The Meter treatment (recovered total,
     ledger) → receivables list (status pills + aging in Mono) → per-receivable
     next action. S3 comfortable density (max ~7 rows/viewport, §7.4). Money is
     ALWAYS Mono + tabular, never truncated (T-2/T-6). Fixture-backed pending the
     live /accessorial/owed API. -->
<script setup>
import { ref, computed, onMounted } from "vue";
import TheMeter from "../core/components/TheMeter.vue";
import { useI18n } from "../core/i18n.js";
import { formatMoney } from "../core/meter.js";
import { receivableStatusToken } from "../core/presentation.js";
import { fetchOwed, fetchFuelAnalytics } from "../core/api.js";
import { SAMPLE_OWED, SAMPLE_FUEL_ANALYTICS } from "../core/fixtures.js";

const { t } = useI18n();
const rows = ref(SAMPLE_OWED);
const fuel = ref(SAMPLE_FUEL_ANALYTICS);

onMounted(async () => {
  try {
    rows.value = await fetchOwed();
  } catch {
    rows.value = SAMPLE_OWED; // unauthenticated / offline
  }
  try {
    fuel.value = await fetchFuelAnalytics();
  } catch {
    fuel.value = SAMPLE_FUEL_ANALYTICS; // unauthenticated / offline
  }
});

const recoveredCents = computed(() =>
  rows.value.filter((r) => r.state === "recovered").reduce((s, r) => s + r.amount_cents, 0),
);

function kindLabel(kind) {
  return t(`money.kind.${kind}`);
}
function stateLabel(state) {
  return t(`money.state.${state}`);
}
</script>

<template>
  <div class="money">
    <section class="card meter-card">
      <TheMeter
        :label="t('money.recovered')"
        :figure="formatMoney(recoveredCents)"
        variant="accruing"
      />
    </section>

    <h1 class="money__title">{{ t("money.title") }}</h1>
    <ul class="rows">
      <li v-for="r in rows" :key="r.receivable_id" class="row">
        <div class="row__main">
          <span class="row__kind">{{ kindLabel(r.kind) }}</span>
          <span
            class="pill"
            :style="{ '--pill-color': `var(${receivableStatusToken(r.state)})` }"
          >
            {{ stateLabel(r.state) }}
          </span>
        </div>
        <div class="row__right">
          <span class="row__amount">{{ formatMoney(r.amount_cents) }}</span>
          <span class="row__aging">{{ r.aging_days }}d</span>
        </div>
      </li>
    </ul>

    <!-- fuel savings-to-date (design-prd §238 savings row; M7-FR4) -->
    <div v-if="fuel.txn_count > 0" class="savings">
      <div class="savings__main">
        <span class="row__kind">{{ t("fuel.saved") }}</span>
        <span class="savings__gallons">{{ Math.round(fuel.gallons_milli / 1000) }} {{ t("fuel.gallons") }}</span>
      </div>
      <span class="savings__amount">{{ formatMoney(fuel.savings_cents) }}</span>
    </div>
  </div>
</template>

<style scoped>
.money {
  padding: var(--s-4);
}
.card {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  margin-bottom: var(--s-4);
}
.money__title {
  margin: 0 0 var(--s-3);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.row {
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  padding: var(--s-3) var(--s-4);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
}
.row__main {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-width: 0;
}
.row__kind {
  font-size: var(--type-body-size);
  font-weight: 500;
}
.pill {
  padding: 2px var(--s-2);
  border-radius: var(--r-pill);
  font-size: var(--type-caption-size);
  font-weight: 500;
  color: var(--ink-0);
  background: var(--pill-color);
}
.row__right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
.row__amount {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
}
.row__aging {
  font-family: var(--font-mono);
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.savings {
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  margin-top: var(--s-3);
  padding: var(--s-3) var(--s-4);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
}
.savings__main {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-width: 0;
}
.savings__gallons {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.savings__amount {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
  color: var(--ledger-500);
}
</style>
