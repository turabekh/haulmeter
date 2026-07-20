<!-- AI-CONTEXT: Fleet Workspace (M12, PRD §8.12) — the FIRST web-first surface
     (design-prd §18): desktop-first, comfortable tables, 1200 dp cap, light
     default, shares ui/core tokens but is NOT a driver-app screen (no tab
     chrome; route meta.portal widens the frame). Shows the fleet report KPIs +
     the consented-members table + the claims desk (counterparty recovery
     rates). Fixture-backed; live wiring needs a fleet-selection flow (follow-up).
     Money is Mono/tabular throughout (T-2). -->
<script setup>
import { ref } from "vue";
import { useI18n } from "../core/i18n.js";
import { formatMoney } from "../core/meter.js";
import { SAMPLE_FLEET } from "../core/fixtures.js";

const { t } = useI18n();
const fleet = ref(SAMPLE_FLEET);

function pct(rate) {
  return `${Math.round(rate * 100)}%`;
}
</script>

<template>
  <div class="fleet">
    <h1 class="fleet__title">{{ t("fleet.title") }}</h1>

    <!-- KPI row (§18 comfortable density) -->
    <section class="kpis">
      <div class="kpi">
        <span class="kpi__label">{{ t("money.recovered") }}</span>
        <span class="kpi__figure ledger">{{ formatMoney(fleet.report.recovered_cents) }}</span>
      </div>
      <div class="kpi">
        <span class="kpi__label">{{ t("fleet.owed") }}</span>
        <span class="kpi__figure">{{ formatMoney(fleet.report.owed_cents) }}</span>
      </div>
      <div class="kpi">
        <span class="kpi__label">{{ t("fuel.saved") }}</span>
        <span class="kpi__figure ledger">{{ formatMoney(fleet.report.fuel_saved_cents) }}</span>
      </div>
      <div class="kpi">
        <span class="kpi__label">{{ t("fleet.drivers") }}</span>
        <span class="kpi__figure">{{ fleet.report.driver_count }}</span>
      </div>
    </section>

    <div class="grid">
      <!-- Members (M12-FR4) -->
      <section class="panel">
        <h2 class="panel__title">{{ t("fleet.members") }}</h2>
        <table class="table">
          <thead>
            <tr>
              <th>{{ t("fleet.driver") }}</th>
              <th class="num">{{ t("money.recovered") }}</th>
              <th class="num">{{ t("fleet.owed") }}</th>
              <th class="num">{{ t("fuel.saved") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in fleet.report.members" :key="m.driver_account_id">
              <td>{{ m.driver_account_id }}</td>
              <td class="num">{{ formatMoney(m.recovered_cents) }}</td>
              <td class="num">{{ formatMoney(m.owed_cents) }}</td>
              <td class="num">{{ formatMoney(m.fuel_saved_cents) }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Claims desk: which brokers actually pay (M12-FR3) -->
      <section class="panel">
        <h2 class="panel__title">{{ t("fleet.claims") }}</h2>
        <table class="table">
          <thead>
            <tr>
              <th>{{ t("fleet.broker") }}</th>
              <th class="num">{{ t("fleet.owed") }}</th>
              <th class="num">{{ t("fleet.recovery_rate") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(cp, name) in fleet.claims.by_counterparty" :key="name">
              <td>{{ name }}</td>
              <td class="num">{{ formatMoney(cp.owed) }}</td>
              <td class="num" :class="cp.recovery_rate >= 0.75 ? 'good' : 'bad'">
                {{ pct(cp.recovery_rate) }}
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</template>

<style scoped>
.fleet {
  padding: var(--s-5);
}
.fleet__title {
  margin: 0 0 var(--s-4);
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
.kpis {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--s-3);
  margin-bottom: var(--s-5);
}
/* §18 desktop: KPIs spread to a row on wider viewports (min-width only) */
@media (min-width: 720px) {
  .kpis {
    grid-template-columns: repeat(4, 1fr);
  }
  .grid {
    grid-template-columns: 3fr 2fr;
  }
}
.kpi {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.kpi__label {
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.kpi__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
}
.kpi__figure.ledger {
  color: var(--ledger-500);
}
.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--s-4);
}
.panel {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
  overflow-x: auto;
}
.panel__title {
  margin: 0 0 var(--s-3);
  font-size: var(--type-label-size);
  color: var(--text-2);
  font-weight: 500;
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--type-body-size);
}
.table th,
.table td {
  text-align: left;
  padding: var(--s-2) var(--s-3);
  border-bottom: 1px solid var(--line-1);
}
.table th {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  font-weight: 500;
}
.table .num {
  text-align: right;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.good {
  color: var(--ledger-500);
}
.bad {
  color: var(--marker-500);
}
</style>
