<!-- AI-CONTEXT: Money tab (design-prd §10.3 / §238) — the driver's P&L with the
     platform. Anatomy at 360 dp: month summary in The Meter treatment — the
     North Star DRIVER DOLLARS DELIVERED (recovered + fuel saved + audit-flagged,
     M9-FR4) → its breakdown → receivables list (status pills + aging in Mono).
     S3 comfortable density (§7.4). Money is ALWAYS Mono + tabular, never
     truncated (T-2/T-6). LIVE — `/accessorial/owed` and `/money/earnings`, on the
     four-state model (§23 entry 131). No figure on this screen is ever invented; the
     two fetches carry separate states because they fail separately. -->
<script setup>
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import TheMeter from "../core/components/TheMeter.vue";
import BottomSheet from "../core/components/BottomSheet.vue";
import GhostwriterSheet from "../core/components/GhostwriterSheet.vue";
import MarkPaidSheet from "../core/components/MarkPaidSheet.vue";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { formatMoney } from "../core/meter.js";
import { receivableStatusToken } from "../core/presentation.js";
import { fetchOwed, fetchEarnings, fetchMe, markReceivablePaid } from "../core/api.js";
import SkeletonCard from "../core/components/SkeletonCard.vue";
import SkeletonRow from "../core/components/SkeletonRow.vue";
import { LoadState, Failure, failureOf } from "../core/load-state.js";

const { t } = useI18n();
const { isDriving } = useDriverState();
const router = useRouter();
// AI-CONTEXT: audit U-06 lived on these two lines (§23 entry 131). The tab opened
// showing invented receivables and an invented Driver-Dollars-Delivered figure — the
// product's North Star, in Mono, on the Meter — and fell back to the same on failure.
// A driver could have taken that number to a broker.
//
// TWO fetches, TWO states, deliberately not one: `/money/owed` and `/money/earnings`
// fail independently, and collapsing them would blank the list because the summary
// broke, or vice versa. §15.4 wants an error about the thing that actually failed.
const EMPTY_EARNINGS = Object.freeze({
  ddd_cents: 0,
  recovered_cents: 0,
  fuel_saved_cents: 0,
  flagged_cents: 0,
});
const rows = ref([]);
const earnings = ref(EMPTY_EARNINGS);
const owedState = ref(LoadState.LOADING);
const owedFailure = ref(null);
const earningsState = ref(LoadState.LOADING);
const earningsFailure = ref(null);
const drafting = ref(false);
const marking = ref(false);
const me = ref(null); // F1: verified operating authority, shown as a trust pill

async function loadOwed() {
  try {
    rows.value = await fetchOwed();
    owedState.value = LoadState.LOADED;
    owedFailure.value = null;
  } catch (e) {
    rows.value = [];
    owedFailure.value = failureOf(e);
    owedState.value = LoadState.FAILED;
  }
}

async function loadEarnings() {
  try {
    earnings.value = await fetchEarnings();
    earningsState.value = LoadState.LOADED;
    earningsFailure.value = null;
  } catch (e) {
    earnings.value = EMPTY_EARNINGS;
    earningsFailure.value = failureOf(e);
    earningsState.value = LoadState.FAILED;
  }
}

onMounted(async () => {
  await loadOwed();
  await loadEarnings();
  try {
    me.value = await fetchMe();
  } catch {
    me.value = null;
  }
});

function kindLabel(kind) {
  return t(`money.kind.${kind}`);
}
function stateLabel(state) {
  return t(`money.state.${state}`);
}

// AI-CONTEXT: F7's ALLOWED_TRANSITIONS is the authority on what may become
// `recovered`; this is the same rule at the point of OFFER, so the driver is never
// shown a control the ledger will refuse. `recovered` and `written_off` are terminal.
const PAYABLE_STATES = ["invoiced", "acknowledged", "disputed", "escalated"];
const payable = computed(() => rows.value.filter((r) => PAYABLE_STATES.includes(r.state)));

async function onMarkPaid(receivableId) {
  marking.value = false;
  try {
    await markReceivablePaid(receivableId);
  } catch {
    /* offline, or the ledger refused it — the list below is the source of truth */
  }
  try {
    rows.value = await fetchOwed();
    earnings.value = await fetchEarnings(); // Recovered moves the North Star figure
  } catch {
    /* leave what is on screen rather than blanking it */
  }
}
</script>

<template>
  <div class="money">
    <!-- AI-CONTEXT: §23 entry 131 is explicit that THE METER must not gain a loading
         state — §9 and entry 52 already specify how it looks at rest, and a Meter that
         shimmered would put the one living element on the screen in service of a
         network request.
         What happens instead: the CARD is replaced until the figure is known, and The
         Meter renders once, with a real number. That is the distinction the entry
         draws — no loading treatment is applied to The Meter, because The Meter is not
         there yet. Rendering it against `ddd_cents: 0` would be worse than either: a
         confident $0.00 in Mono is a claim about the driver's month. -->
    <SkeletonCard v-if="earningsState === LoadState.LOADING" :count="1" />
    <p v-else-if="earningsState === LoadState.FAILED" class="money__failed">
      {{ earningsFailure === Failure.OFFLINE ? t("system.load_offline") : t("money.earnings_failed") }}
      <button class="money__retry" type="button" @click="loadEarnings">{{ t("system.retry") }}</button>
    </p>
    <!-- North Star: Driver Dollars Delivered (§238 month summary, Meter) -->
    <section v-else class="card meter-card">
      <TheMeter
        :label="t('money.delivered')"
        :figure="formatMoney(earnings.ddd_cents)"
        variant="accruing"
      />
    </section>

    <!-- F1: verified authority — a §200 status pill where credibility is billed -->
    <div v-if="me && me.verified" class="authpill-row">
      <span class="pill authpill">
        MC# {{ me.mc_number }} · {{ t("authority.verified") }}
      </span>
    </div>

    <!-- the breakdown is the same fetch as the Meter, so it appears with it rather
         than rendering three confident $0.00 rows in Mono while one is in flight -->
    <ul v-if="earningsState === LoadState.LOADED" class="breakdown">
      <li class="breakdown__row">
        <span>{{ t("money.recovered") }}</span>
        <span class="mono">{{ formatMoney(earnings.recovered_cents) }}</span>
      </li>
      <li class="breakdown__row">
        <span>{{ t("fuel.saved") }}</span>
        <span class="mono">{{ formatMoney(earnings.fuel_saved_cents) }}</span>
      </li>
      <li v-if="earnings.flagged_cents > 0" class="breakdown__row">
        <span>{{ t("money.flagged") }}</span>
        <span class="mono">{{ formatMoney(earnings.flagged_cents) }}</span>
      </li>
    </ul>

    <h1 class="money__title">{{ t("money.title") }}</h1>
    <SkeletonRow v-if="owedState === LoadState.LOADING" :count="3" />
    <p v-else-if="owedState === LoadState.FAILED" class="money__failed">
      {{ owedFailure === Failure.OFFLINE ? t("system.load_offline") : t("money.load_failed") }}
      <button class="money__retry" type="button" @click="loadOwed">{{ t("system.retry") }}</button>
    </p>
    <!-- AI-CONTEXT: §15.3's empty state, found MISSING while applying the four-state
         rule (§23 entry 131) — which is the rule earning its place on the §22.3 DoD.
         `money.empty` was already written and already translated into all six locales,
         and was rendered by NOTHING: a driver owed nothing got a bare heading over an
         empty list. The same built-and-inert shape as `register_message` before N-01
         and `system.loading` beside it. It says what the tab is FOR and names the one
         action that starts it, which is both halves of §15.3. -->
    <p v-else-if="!rows.length" class="money__empty">{{ t("money.empty") }}</p>
    <ul v-else class="rows">
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

    <!-- AI-CONTEXT: §10.3 SPECIFIES this tab's DRIVING behaviour — "read-only;
         actions deferred" — and it was never implemented, so both flows opened at
         speed. The figures above stay readable, which is the whole of what §10.3
         allows; the two things that ACT withdraw and say when they return.

         The ghostwriter sheet closes with them: the control that opens a flow and
         the flow itself are two different things to guard, which is exactly how the
         Docs capture sheet stayed open at speed. -->
    <template v-if="!isDriving">
      <!-- M9-FR1: the settlement auditor — the company-driver wedge (NAV-5) -->
      <button class="audit-cta" type="button" @click="router.push('/money/audit')">
        {{ t("audit.title") }}
      </button>
      <!-- M11-FR3: the comms ghostwriter — draft the firm message that unsticks pay -->
      <button class="audit-cta" type="button" @click="drafting = true">
        {{ t("ghost.title") }}
      </button>
      <!-- §23 entry 108: the ending a claim never had. Rendered only when something
           is actually payable, so the Money tab of a driver owed nothing stays quiet. -->
      <button
        v-if="payable.length"
        class="audit-cta"
        type="button"
        @click="marking = true"
      >
        {{ t("money.paid.cta") }}
      </button>
    </template>
    <p v-else class="driving-note">{{ t("driving.paused") }}</p>

    <BottomSheet :open="drafting && !isDriving" :title="t('ghost.title')" @close="drafting = false">
      <GhostwriterSheet />
    </BottomSheet>

    <!-- guarded with `!isDriving` like the ghostwriter above: §10.3 defers ACTIONS at
         speed, and a sheet left open across a state change is how the Docs capture
         flow stayed live in a moving truck. -->
    <BottomSheet
      :open="marking && !isDriving"
      :title="t('money.paid.cta')"
      @close="marking = false"
    >
      <MarkPaidSheet :rows="payable" @submit="onMarkPaid" />
    </BottomSheet>
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
/* §15.3's empty line and §15.4's failed line share the body treatment: both are one
   quiet sentence about this list, and neither is an event. Composition only. */
.money__empty {
  margin: 0 var(--s-4);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.money__failed {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: 0 var(--s-4);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.money__retry {
  min-height: 48px;
  padding: 0 var(--s-2);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
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
.authpill-row {
  margin-bottom: var(--s-3);
}
.authpill {
  background: var(--ledger-500);
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
/* DDD breakdown — the three streams behind the North Star figure (M9-FR4) */
.breakdown {
  list-style: none;
  margin: 0 0 var(--s-4);
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
  color: var(--text-2);
}
.mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-body-size);
  color: var(--ledger-500);
}
.audit-cta {
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-4);
  border-radius: var(--r-control);
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
  font-size: var(--type-label-size);
  font-weight: 500;
}
</style>
