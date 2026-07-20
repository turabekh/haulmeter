<!-- AI-CONTEXT: Fleet Workspace (M12, PRD §8.12) — the FIRST web-first surface
     (design-prd §18): desktop-first, comfortable tables, 1200 dp cap, light
     default, shares ui/core tokens but is NOT a driver-app screen (no tab
     chrome; route meta.portal widens the frame). Now LIVE: create/select a fleet
     (persisted), then fetch its report KPIs + consented-members table + claims
     desk (counterparty recovery rates). Falls back to the fixture demo when
     unauthenticated/offline. Money is Mono/tabular throughout (T-2). -->
<script setup>
import { ref, onMounted } from "vue";
import { useI18n } from "../core/i18n.js";
import { formatMoney } from "../core/meter.js";
import { SAMPLE_FLEET } from "../core/fixtures.js";
import {
  activeFleetId,
  setActiveFleet,
  fetchMyFleets,
  createFleet,
  fetchFleetReport,
  fetchFleetClaims,
} from "../core/api.js";

const { t } = useI18n();
const view = ref("loading"); // loading | demo | picker | create | workspace
const fleet = ref(SAMPLE_FLEET);
const myFleets = ref([]);
const fleetName = ref("");
const newName = ref("");

async function loadWorkspace(id, name) {
  const [report, claims] = await Promise.all([fetchFleetReport(id), fetchFleetClaims(id)]);
  fleet.value = { report, claims };
  fleetName.value = name || "";
  view.value = "workspace";
}

async function init() {
  try {
    myFleets.value = await fetchMyFleets();
    const active = myFleets.value.find((f) => f.fleet_id === activeFleetId.value);
    if (active) {
      await loadWorkspace(active.fleet_id, active.name);
    } else if (myFleets.value.length) {
      setActiveFleet(null);
      view.value = "picker";
    } else {
      view.value = "create";
    }
  } catch {
    fleet.value = SAMPLE_FLEET; // unauthenticated / offline demo
    view.value = "demo";
  }
}
onMounted(init);

async function select(f) {
  setActiveFleet(f.fleet_id);
  await loadWorkspace(f.fleet_id, f.name);
}

async function create() {
  const name = newName.value.trim();
  if (!name) return;
  try {
    const res = await createFleet(name);
    await loadWorkspace(res.fleet_id, name);
  } catch {
    /* offline — demo stays */
  }
}

function backToFleets() {
  setActiveFleet(null);
  init();
}

function pct(rate) {
  return `${Math.round(rate * 100)}%`;
}
function driverLabel(id) {
  return String(id).length > 12 ? String(id).slice(0, 8) : id; // truncate raw UUIDs
}
</script>

<template>
  <div class="fleet">
    <div class="fleet__head">
      <h1 class="fleet__title">{{ t("fleet.title") }}</h1>
      <button
        v-if="view === 'workspace'"
        class="switch"
        type="button"
        @click="backToFleets"
      >
        {{ fleetName }} · {{ t("fleet.your_fleets") }}
      </button>
    </div>

    <!-- create-a-fleet (no fleets yet) -->
    <section v-if="view === 'create'" class="select">
      <p class="select__note">{{ t("fleet.none") }}</p>
      <label class="field">
        <span class="field__label">{{ t("fleet.name") }}</span>
        <input v-model="newName" class="field__input" type="text" @keyup.enter="create" />
      </label>
      <button class="cta" type="button" @click="create">{{ t("fleet.create_go") }}</button>
    </section>

    <!-- pick a fleet -->
    <section v-else-if="view === 'picker'" class="select">
      <h2 class="panel__title">{{ t("fleet.your_fleets") }}</h2>
      <ul class="fleets">
        <li v-for="f in myFleets" :key="f.fleet_id" class="fleets__row">
          <span>{{ f.name }}</span>
          <button class="cta cta--sm" type="button" @click="select(f)">{{ t("fleet.open") }}</button>
        </li>
      </ul>
    </section>

    <!-- the workspace (live) or the fixture demo -->
    <template v-else-if="view === 'workspace' || view === 'demo'">
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
              <td>{{ driverLabel(m.driver_account_id) }}</td>
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
    </template>
  </div>
</template>

<style scoped>
.fleet {
  padding: var(--s-5);
}
.fleet__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
  flex-wrap: wrap;
  margin-bottom: var(--s-4);
}
.switch {
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.select {
  max-width: 480px;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.select__note {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
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
  font-size: var(--type-body-size);
}
.cta {
  min-height: 56px;
  padding: 0 var(--s-4);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta--sm {
  min-height: 40px;
}
.fleets {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.fleets__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.fleet__title {
  margin: 0;
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
