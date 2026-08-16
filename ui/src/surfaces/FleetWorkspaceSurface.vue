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
  fetchFleetHolds,
  decideFleetHold,
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

/* AI-CONTEXT: M14 slice 1's approvals queue (E2, D8) — the one place a human decides
 * whether an ELD-derived detention claim is invoiced in the carrier's name.
 *
 * HOLD-ALL IS THE RULES ENGINE for this slice and this screen IS the rule: FR5's engine
 * is PROPOSED and absent, so there is no threshold, no timer and no auto-send anywhere
 * behind this panel.
 *
 * It fails SOFT and separately from the workspace. `holds` is a fourth fetch beside the
 * report and the claims desk, and a fleet whose overlay flag is off gets a 404 from a
 * route gated on `m14_overlay` — which must not blank a workspace whose money figures
 * loaded perfectly. Entry 131's rule, one surface over: independent fetches, independent
 * states.
 */
const holds = ref(null);
const holdsBusy = ref(null);

async function loadHolds(id) {
  try {
    const payload = await fetchFleetHolds(id);
    // AI-CONTEXT: the SHAPE is checked here, at the boundary, and a payload that is not a
    // holds payload is treated exactly like the 404 below (TRAPS §15).
    //
    // This crashed the whole surface for several sessions. `holds` was assigned whatever
    // came back, the template did `holds.holds.length`, and a truthy body without a
    // `holds` array threw inside render — taking the KPIs down with the panel and
    // breaking this file's own stated rule that holds "fails SOFT and separately from the
    // workspace". It surfaced only as a vitest unhandled rejection, so `make ci` exited 1
    // while all 1020 assertions passed and nothing could observe it.
    //
    // Guarding in the TEMPLATE with `holds.holds?.length` would have silenced the crash
    // and rendered the empty state instead — which reads as "no claims are held", a claim
    // about a fleet's money made from a response we could not parse. Absent is the honest
    // rendering, and it is the one the 404 path already chose.
    holds.value = Array.isArray(payload?.holds) ? payload : null;
  } catch {
    // the overlay is off for this fleet, or the module is not enabled on this box. The
    // panel simply is not there — it does not render an error over a working workspace.
    holds.value = null;
  }
}

async function decide(holdId, decision) {
  holdsBusy.value = holdId;
  try {
    await decideFleetHold(activeFleetId.value, holdId, decision);
    await loadHolds(activeFleetId.value);
  } catch {
    /* leave the row where it is — a decision that did not land must not look like one
       that did, which is the whole reason `send_blocked_by` exists on the row */
  } finally {
    holdsBusy.value = null;
  }
}

async function loadWorkspace(id, name) {
  const [report, claims] = await Promise.all([fetchFleetReport(id), fetchFleetClaims(id)]);
  fleet.value = { report, claims };
  fleetName.value = name || "";
  view.value = "workspace";
  await loadHolds(id);
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

      <!-- AI-CONTEXT: M14 slice 1's approvals queue (PRD Extension E2, owner decision D8).
           The one place a human decides whether an ELD-derived detention claim is invoiced
           in the carrier's name. Hold-all is the rules engine for this slice and this
           panel IS the rule — there is no threshold, no timer and no auto-send behind it.

           Rendered only when the overlay answered: a fleet without the flag gets a 404
           from a gated route, and that must not put an error over a workspace whose money
           figures loaded perfectly (entry 131's independent-fetch rule, one surface over). -->
      <section v-if="holds" class="panel holds">
        <h2 class="panel__title">{{ t("fleet.approvals") }}</h2>

        <!-- §11.7 aimed at the operator: the blocker is stated BEFORE they approve, not
             discovered afterwards when nothing happens. A queue that says "approved"
             while nothing left the box is F-01's shape exactly. -->
        <p v-if="!holds.can_send" class="holds__blocked">
          {{ t("fleet.approvals_blocked") }}
        </p>

        <p v-if="!holds.holds.length" class="holds__empty">{{ t("fleet.approvals_none") }}</p>
        <div v-else class="table-scroll">
          <table class="table">
            <thead>
              <tr>
                <th>{{ t("fleet.driver") }}</th>
                <th>{{ t("fleet.evidence_basis") }}</th>
                <th class="num">{{ t("fleet.decide") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="h in holds.holds" :key="h.hold_id" class="holds__row">
                <td>{{ driverLabel(h.account_id) }}</td>
                <!-- an admin approving an `eld_derived` claim should know that is what
                     they are about to send a broker -->
                <td>{{ t(`fleet.basis.${h.evidence_class}`) }}</td>
                <td class="num holds__actions">
                  <button
                    class="cta cta--sm holds__approve"
                    type="button"
                    :disabled="holdsBusy === h.hold_id"
                    @click="decide(h.hold_id, 'approve')"
                  >
                    {{ t("fleet.approve") }}
                  </button>
                  <button
                    class="cta cta--sm holds__reject"
                    type="button"
                    :disabled="holdsBusy === h.hold_id"
                    @click="decide(h.hold_id, 'reject')"
                  >
                    {{ t("fleet.reject") }}
                  </button>
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
/* AI-CONTEXT: §18 exempts portals from LAW 0's ORDER, not from §6's floors — HANDOFF-121
   §13.13, which found seven portal controls below 48 dp and one `.switch` at 233 × 20.
   These are decision buttons on money, so they are sized like it. */
.holds__actions {
  display: flex;
  gap: var(--s-2);
  justify-content: flex-end;
}
.holds__approve,
.holds__reject {
  min-height: 48px;
  min-width: 96px;
}
.holds__reject {
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
}
/* calm, not red: a pending counsel sign-off is a MODE, not a failure — the same
   restraint §15.1 sets for offline. It is stated plainly and once. */
.holds__blocked {
  margin: 0 0 var(--s-3);
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.holds__empty {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
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
