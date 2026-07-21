<!-- AI-CONTEXT: Load tab (design-prd §10.2) — the current stop and its money/
     evidence state, built around The Meter (§9, the signature element). Now
     LIVE: an active stop (api.js activeStopId) drives the Meter off the M3
     detention clock (GET /load/{stop}/meter); the client reconstructs arrival
     and ticks locally. Pre-arrival shows an "I've arrived" CTA; arrived ticks
     free-time down then money up. No active load -> a fixture demo Meter + a
     "Start a load" sheet. DRIVING collapses to a Meter-only glance. S2 dock. -->
<script setup>
import { ref, computed, reactive, onMounted, onUnmounted } from "vue";
import { Check, Camera, Send } from "lucide-vue-next";
import { useRouter } from "vue-router";
import TheMeter from "../core/components/TheMeter.vue";
import BottomSheet from "../core/components/BottomSheet.vue";
import IncidentSheet from "../core/components/IncidentSheet.vue";
import { useDriverState } from "../core/state.js";
import { useI18n } from "../core/i18n.js";
import { computeDetentionState, meterVariant, formatClock, formatMoney } from "../core/meter.js";
import { SAMPLE_STOP } from "../core/fixtures.js";
import {
  activeStopId,
  setActiveStop,
  createActiveLoad,
  arriveAtStop,
  fetchMeter,
  fetchActiveLoad,
  endActiveLoad,
  sendDetentionNotice,
  generateClaim,
  isAuthenticated,
} from "../core/api.js";

const { isDriving } = useDriverState();
const { t } = useI18n();
const router = useRouter();

const live = ref(null); // live meter response, or null (fixture demo)
const arrivalMs = ref(0); // null while a live load is pre-arrival
const now = ref(Date.now());
const starting = ref(false);
const reporting = ref(false); // incident sheet open
const filed = ref(null); // the generated claim result, once filed
const form = reactive({ facility: "", broker: "", freeMin: 120, rateHr: 75 });
let timer = null;

function setupDemo() {
  live.value = null;
  arrivalMs.value = Date.now() - SAMPLE_STOP.arrival_offset_min * 60000;
}

function deriveArrival(m) {
  const base = Date.now();
  if (m.phase === "within_free_time") {
    return base - (m.free_time_minutes * 60 - m.free_time_remaining_seconds) * 1000;
  }
  if (m.phase === "accruing") {
    return base - (m.free_time_minutes * 60 + m.detention_seconds) * 1000;
  }
  return null; // not arrived
}

async function loadMeter() {
  try {
    const m = await fetchMeter(activeStopId.value);
    live.value = m;
    arrivalMs.value = deriveArrival(m);
  } catch {
    setActiveStop(null); // stale/offline -> fall back to the demo
    setupDemo();
  }
}

onMounted(async () => {
  // no locally-remembered stop? ask the server if this driver has one armed
  // (fresh-device resume) before falling back to the demo Meter.
  if (!activeStopId.value && isAuthenticated.value) {
    try {
      await fetchActiveLoad();
    } catch {
      /* offline — demo below */
    }
  }
  if (activeStopId.value) await loadMeter();
  else setupDemo();
  timer = setInterval(() => (now.value = Date.now()), 1000);
});
onUnmounted(() => timer && clearInterval(timer));

const freeMin = computed(() => live.value?.free_time_minutes ?? SAMPLE_STOP.free_time_minutes);
const rateCents = computed(() => live.value?.rate_cents_per_hour ?? SAMPLE_STOP.rate_cents_per_hour);
const preArrival = computed(() => !!live.value && live.value.phase === "not_arrived");

const stopName = computed(() => live.value?.facility_name ?? SAMPLE_STOP.facility_name);
const stopMeta = computed(() => {
  const cp = live.value?.counterparty ?? SAMPLE_STOP.counterparty;
  const appt = live.value ? (live.value.appointment ?? "") : SAMPLE_STOP.appointment;
  return appt ? `${appt} · ${cp}` : cp;
});
const noticeSent = computed(() => (live.value ? live.value.notice_sent : false));

const state = computed(() =>
  computeDetentionState(arrivalMs.value ?? now.value, freeMin.value, rateCents.value, now.value),
);
const withinFree = computed(() => state.value.phase === "within_free_time");
const accruing = computed(() => !!live.value && !preArrival.value && !withinFree.value);
const noticeMsg = ref("");

// a claim is filed once the SERVER says so (live.filed) — persists across tab
// switches/remounts — or optimistically the moment we file it (filed ref).
const isFiled = computed(() => !!(filed.value || live.value?.filed));
const filedAmount = computed(
  () => filed.value?.amount_cents ?? live.value?.detention_cents ?? 0,
);

// once a claim is filed the Meter FREEZES at the filed amount — the clock stops
// ticking, so what you see matches the claim you filed (§9)
const meterLabel = computed(() =>
  preArrival.value ? t("load.waiting") : withinFree.value ? t("load.free_time") : t("load.detention"),
);
const meterFigure = computed(() => {
  if (isFiled.value) return formatMoney(filedAmount.value);
  if (preArrival.value) return live.value.appointment ? live.value.appointment.slice(11, 16) : "—";
  return withinFree.value
    ? formatClock(state.value.freeTimeRemainingSeconds)
    : formatMoney(state.value.amountCents);
});
const meterStatus = computed(() => {
  if (isFiled.value) return t("load.filed_frozen");
  return preArrival.value || withinFree.value
    ? ""
    : `${formatClock(state.value.detentionSeconds)} · $${Math.round(rateCents.value / 100)}/h`;
});
const variant = computed(() => (preArrival.value ? "countdown" : meterVariant(state.value)));

async function onArrive() {
  if (!activeStopId.value) return;
  try {
    await arriveAtStop(activeStopId.value);
    await loadMeter();
  } catch {
    /* offline / queued in a later F12 pass */
  }
}
async function onGenerateClaim() {
  if (!activeStopId.value || filed.value) return;
  try {
    filed.value = await generateClaim(activeStopId.value); // arrive->accrue->FILE (freezes Meter)
    await loadMeter();
  } catch {
    /* offline / queued in a later F12 pass */
  }
}
async function onSendNotice() {
  if (!activeStopId.value) return;
  try {
    const res = await sendDetentionNotice(activeStopId.value); // M3 counterparty notice
    noticeMsg.value = res && res.sent ? t("load.notice_ok") : t("load.notice_early");
    await loadMeter();
  } catch {
    noticeMsg.value = t("load.notice_early");
  }
}

async function startLoad() {
  starting.value = false;
  try {
    await createActiveLoad({
      facility_name: form.facility || "Receiver",
      lat: 32.7767,
      lon: -96.797,
      counterparty: form.broker || "Broker",
      free_time_minutes: Number(form.freeMin) || 120,
      rate_cents_per_hour: Math.round(Number(form.rateHr) || 75) * 100,
    });
    await loadMeter();
  } catch {
    /* offline: the demo Meter stays; queued in a later F12 pass */
  }
}

async function endLoad() {
  const stopId = activeStopId.value;
  if (stopId) await endActiveLoad(stopId); // durable: departs the stop server-side
  else setActiveStop(null);
  filed.value = null;
  setupDemo();
}
</script>

<template>
  <div class="load">
    <section class="card meter-card" :class="{ 'meter-card--sample': !live }">
      <span v-if="!live" class="sample-tag">{{ t("load.sample") }}</span>
      <TheMeter :label="meterLabel" :figure="meterFigure" :variant="variant" :status="meterStatus" />
    </section>
    <p v-if="!live && !isDriving" class="sample-hint">{{ t("load.sample_hint") }}</p>

    <template v-if="!isDriving">
      <div class="context">
        <span class="context__name">{{ stopName }}</span>
        <span class="context__meta">{{ stopMeta }}</span>
      </div>

      <section class="card">
        <h2 class="card__title">{{ t("load.evidence") }}</h2>
        <ul class="checklist">
          <li class="checklist__item">
            <Check :size="20" :stroke-width="2" class="ok" aria-hidden="true" />
            {{ t("load.bol") }}
          </li>
          <li class="checklist__item">
            <Camera :size="20" :stroke-width="2" aria-hidden="true" />
            {{ t("load.photos") }}
          </li>
          <li class="checklist__item">
            <Send :size="20" :stroke-width="2" :class="{ ok: noticeSent }" aria-hidden="true" />
            {{ noticeSent ? t("load.notice_sent_ok") : t("load.notice_sent") }}
          </li>
        </ul>
      </section>

      <!-- arrive -> accrue -> FILE: the loop closes into a GPS-backed claim -->
      <div v-if="isFiled" class="filed">
        <Check :size="20" :stroke-width="2" class="ok" aria-hidden="true" />
        <span>{{ t("load.filed") }} · {{ formatMoney(filedAmount) }}</span>
        <button class="filed__link" type="button" @click="router.push('/money')">
          {{ t("money.title") }}
        </button>
      </div>

      <!-- pre-arrival: mark arrival (starts the clock) -->
      <button v-if="live && preArrival" class="cta" type="button" @click="onArrive">
        {{ t("load.arrive") }}
      </button>

      <!-- accruing: FILE the GPS-backed claim (freezes the Meter) -->
      <button v-if="accruing && !isFiled" class="cta" type="button" @click="onGenerateClaim">
        {{ t("load.cta.claim") }}
      </button>
      <!-- accruing: warn the broker detention started (once) -->
      <button
        v-if="accruing && !noticeSent && !isFiled"
        class="cta cta--text"
        type="button"
        @click="onSendNotice"
      >
        {{ t("load.cta.notice") }}
      </button>
      <p v-if="noticeMsg" class="notice-msg">{{ noticeMsg }}</p>

      <!-- M5-FR2: camera-first cargo-condition capture for the active stop -->
      <button v-if="live" class="cta cta--text" type="button" @click="router.push('/protection/condition')">
        {{ t("cond.start") }}
      </button>

      <!-- M5-FR4: log an incident (damage / refusal / unsafe) for the active stop -->
      <button v-if="live" class="cta cta--text" type="button" @click="reporting = true">
        {{ t("incident.title") }}
      </button>

      <button v-if="live" class="cta cta--text" type="button" @click="endLoad">{{ t("load.end") }}</button>

      <!-- no active load: the Meter above is a sample; start a real one -->
      <button v-if="!live" class="cta" type="button" @click="starting = true">
        {{ t("load.start") }}
      </button>

      <!-- M8: pre-acceptance decision — cross-link to the true-profit calculator (NAV-5) -->
      <button class="cta cta--text" type="button" @click="router.push('/load/calc')">
        {{ t("load.check_profit") }}
      </button>

      <BottomSheet :open="starting" :title="t('load.start')" @close="starting = false">
        <form class="start" @submit.prevent="startLoad">
          <label class="field">
            <span class="field__label">{{ t("load.facility") }}</span>
            <input v-model="form.facility" class="field__input" type="text" />
          </label>
          <label class="field">
            <span class="field__label">{{ t("load.broker") }}</span>
            <input v-model="form.broker" class="field__input" type="text" />
          </label>
          <label class="field">
            <span class="field__label">{{ t("calc.free_min") }}</span>
            <input v-model="form.freeMin" class="field__input" type="number" inputmode="numeric" />
          </label>
          <label class="field">
            <span class="field__label">{{ t("calc.rate_hr") }}</span>
            <input v-model="form.rateHr" class="field__input" type="number" inputmode="decimal" />
          </label>
          <button class="cta" type="submit">{{ t("load.create") }}</button>
        </form>
      </BottomSheet>

      <BottomSheet :open="reporting" :title="t('incident.title')" @close="reporting = false">
        <IncidentSheet />
      </BottomSheet>
    </template>
  </div>
</template>

<style scoped>
.load {
  padding: var(--s-4);
}
.card {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
  margin-bottom: var(--s-3);
}
.meter-card {
  padding: 0;
  position: relative;
}
.meter-card--sample {
  border-style: dashed;
  opacity: 0.9;
}
.sample-tag {
  position: absolute;
  top: var(--s-2);
  right: var(--s-2);
  z-index: 1;
  padding: 2px var(--s-2);
  border-radius: var(--r-pill);
  background: var(--ink-2, var(--line-1));
  color: var(--text-3);
  font-family: var(--font-mono);
  font-size: var(--type-caption-size);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.sample-hint {
  margin: calc(var(--s-2) * -1) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  text-align: center;
}
.notice-msg {
  margin: calc(var(--s-2) * -1) 0 0;
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-control);
  background: var(--ink-2, var(--line-1));
  color: var(--text-2);
  font-size: var(--type-caption-size);
  text-align: center;
}
.context {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  margin-bottom: var(--s-3);
}
.context__name {
  font-size: var(--type-title-size);
  font-weight: var(--type-title-weight);
}
.context__meta {
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.card__title {
  margin: 0 0 var(--s-3);
  font-size: var(--type-label-size);
  color: var(--text-2);
  font-weight: 500;
}
.checklist {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.checklist__item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.ok {
  color: var(--ledger-500);
}
.filed {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-bottom: var(--s-2);
  padding: var(--s-3);
  border-radius: var(--r-card);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.filed__link {
  margin-left: auto;
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
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
.cta--outline {
  margin-top: var(--s-2);
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
}
/* text button (§8) — secondary cross-links (end load, profit calculator) */
.cta--text {
  margin-top: var(--s-2);
  min-height: 48px;
  background: transparent;
  color: var(--shield-500);
}
.start {
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
  font-size: var(--type-body-size);
}
</style>
