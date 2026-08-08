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
import SkeletonCard from "../core/components/SkeletonCard.vue";
import { Failure, failureOf } from "../core/load-state.js";
import {
  activeFleetId,
  setActiveFleet,
  fetchMyFleets,
  createFleet,
  fetchFleetReport,
  fetchFleetClaims,
} from "../core/api.js";

const { t } = useI18n();
// AI-CONTEXT: §23 entry 131. The "demo" view is gone and `failed` replaces it — the
// kickoff's instruction was to ALIGN with this state machine rather than bolt a second
// model beside it, and `view` already had the four states under other names.
// `SAMPLE_FLEET` rendered invented recovery figures and an invented claims desk to
// whoever could not authenticate.
const view = ref("loading"); // loading | failed | picker | create | workspace
const fleet = ref(null);
const fleetFailure = ref(null);
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
  } catch (e) {
    fleet.value = null;
    fleetFailure.value = failureOf(e);
    view.value = "failed";
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

    <!-- §8's card skeleton: the KPI row and the panels below are all cards -->
    <SkeletonCard v-else-if="view === 'loading'" :count="3" />
    <p v-else-if="view === 'failed'" class="fleet__failed">
      {{ fleetFailure === Failure.OFFLINE ? t("system.load_offline") : t("fleet.load_failed") }}
      <button class="fleet__retry" type="button" @click="init">{{ t("system.retry") }}</button>
    </p>
    <!-- the workspace, live. There is no demo any more (§23 entry 131). -->
    <template v-else-if="view === 'workspace'">
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
        <div class="table-scroll">
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
        </div>
      </section>

      <!-- Claims desk: which brokers actually pay (M12-FR3) -->
      <section class="panel">
        <h2 class="panel__title">{{ t("fleet.claims") }}</h2>
        <div class="table-scroll">
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
              <td>{{ cp.name || name }}</td>
              <td class="num">{{ formatMoney(cp.owed) }}</td>
              <td class="num" :class="cp.recovery_rate >= 0.75 ? 'good' : 'bad'">
                {{ pct(cp.recovery_rate) }}
              </td>
            </tr>
          </tbody>
        </table>
        </div>
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
/* AI-CONTEXT: this had NO height at all and measured 233x20 dp — the worst target in
   either portal, and one the audit never counted (§23 entry 132). U-05 described "two
   portal controls (40 dp)"; there were seven below §6.5's floor and this was 20.
   It is the control that changes which fleet the whole screen is about. */
.switch {
  min-height: var(--touch-min);
  padding: 0 var(--s-2);
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
/* AI-CONTEXT: 40 -> --touch-min (§23 entry 132, audit U-05). §6.5's "minimum target
   48 x 48 dp" carries no portal exemption, and §18's own text says these portals are
   "responsive down to tablet/phone" — its only exemption sentence protects the DRIVER
   APP from §18, not the portals from §6. This is the row-level "Open" on each fleet.
   Not raised to §6.5's 56 dp primary height: that is for a screen's one primary action,
   and this is a control inside a list. */
.cta--sm {
  min-height: var(--touch-min);
  min-width: var(--touch-min); /* §6.5 is 48 x 48 — both dimensions */
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
.fleet__failed {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: var(--s-4);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.fleet__retry {
  min-height: 48px;
  padding: 0 var(--s-2);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
/* AI-CONTEXT: `minmax(0, 1fr)`, not `1fr` — the grid form of the same defect twice over
   in this session (§23 entry 132). A grid TRACK, like a flex item, defaults to a minimum
   of min-content, so at 200% text the KPI figures could not shrink and the row ran to
   488 px at 360 dp. `minmax(0, …)` is what lets a track go narrower than its content and
   the content wrap instead. */
.kpis {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
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
/* AI-CONTEXT: §18 says these portals are "responsive down to tablet/phone", and until
   they were registered in the layout harness nobody had checked (§23 entry 132). At 360 dp
   this table ran to 437 px and pushed the whole PAGE sideways — an owner on a phone
   scrolled the header and the property list to read a booking.
   A horizontal scroller around the table is the fix, and it is not a new pattern: the
   harness's own overflow rule names "the preset chip row, the portal rail" as approved
   deliberate scrollers. The table keeps its comfortable desktop density (§18) and stops
   dragging the page with it. */
.table-scroll {
  overflow-x: auto;
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
