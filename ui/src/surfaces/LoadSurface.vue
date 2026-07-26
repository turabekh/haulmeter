<!-- AI-CONTEXT: Load tab (design-prd §10.2) — the current stop and its money/
     evidence state, built around The Meter (§9, the signature element). Now
     LIVE: an active stop (api.js activeStopId) drives the Meter off the M3
     detention clock (GET /load/{stop}/meter); the client reconstructs arrival
     and ticks locally. Pre-arrival shows an "I've arrived" CTA; arrived ticks
     free-time down then money up. DRIVING collapses to a Meter-only glance. S2 dock.

     Empty state is §10.2's: "Add a load" by RATE-CON PHOTO as the one action. PRD
     §108 calls the parsed rate con the primary way a load is created, and it had
     never existed outside the Foundation e2e — this tab offered a four-field manual
     form in its place, which now lives inside the import sheet as the fallback for a
     rate con the parse cannot read. -->
<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { Check, Camera, Send } from "lucide-vue-next";
import { useRouter } from "vue-router";
import TheMeter from "../core/components/TheMeter.vue";
import BottomSheet from "../core/components/BottomSheet.vue";
import IncidentSheet from "../core/components/IncidentSheet.vue";
import DocumentCaptureSheet from "../core/components/DocumentCaptureSheet.vue";
import RateConImportSheet from "../core/components/RateConImportSheet.vue";
import { useDriverState } from "../core/state.js";
import { useI18n } from "../core/i18n.js";
import { computeDetentionState, meterVariant, formatClock, formatMoney } from "../core/meter.js";
import { SAMPLE_STOP } from "../core/fixtures.js";
import {
  activeStopId,
  setActiveStop,
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
const reporting = ref(false); // incident sheet open
const incidentToast = ref("");
// the last incident filed in this session, so its pack has a route (FR4)
const lastIncidentId = ref(null);
function onIncidentFiled(e) {
  // AI-CONTEXT: M5-FR4 — the pack was unreachable the moment this toast faded.
  //
  // The incident id arrived in this event and nothing kept it, so a filed incident
  // could never be opened, exported or shared again from the app. Holding it turns
  // the confirmation into a route: file, then look at what you filed. No new
  // navigation structure — the same evidence surface the condition packs use, with
  // the kind carried in the query (§22.2: navigation structure is never-improvise).
  reporting.value = false;
  lastIncidentId.value = e.incident_id ?? null;
  incidentToast.value = e.state === "queued" ? t("incident.queued") : t("incident.logged");
  setTimeout(() => (incidentToast.value = ""), 3500);
}
// AI-CONTEXT: §10.2's CTA ladder is "Arm stop -> Snap BOL -> Send notice -> Generate
// claim", and the Snap BOL rung has never existed. The checklist read `has_bol(stop)`
// — a document scoped to THIS stop — while the only capture sheet in the app filed
// against the account, so the row could never turn green no matter what the driver
// photographed. The endpoint has accepted a stop since the writer shipped.
const snapping = ref(false);
// §10.2's empty-state action. The manual "Start a load" form now lives inside this
// sheet as the fallback when a rate con cannot be read, rather than as a rival action.
const importing = ref(false);
async function onLoadCreated() {
  importing.value = false;
  await loadMeter();
}
async function onBolCaptured() {
  snapping.value = false;
  await loadMeter(); // the checklist row closes the moment the BOL lands
}
const filed = ref(null); // the generated claim result, once filed
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
const photosCaptured = computed(() => live.value?.photos_captured ?? 0);
// §10.2 specifies "photos 2/4". The DENOMINATOR is the feature: a bare count cannot
// tell a driver whether they are finished, and FR5 exists to make a gap visible
// while the driver is still standing where it can be closed.
const photosRequired = computed(() => live.value?.photos_required ?? 0);
const photosDone = computed(
  () => photosRequired.value > 0 && photosCaptured.value >= photosRequired.value,
);
// the row rendered an unconditional tick. A checklist that always says yes is
// decoration — and the honest answer for most stops today is "not yet", which is
// exactly what FR5 is for.
const bolCaptured = computed(() => live.value?.bol_captured === true);

// AI-CONTEXT: M5-FR1's protection is the WINDOW, not the verdict.
//
// The verdict arrives after the fact and is a post-mortem. The failure this FR
// exists to prevent is a mis-parsed appointment silently costing a driver a
// protection they believe they have — and that is only correctable while they are
// still approaching, by ringing the broker. So the window is shown BEFORE arrival,
// with where the value came from: a machine read of a rate con and a value typed by
// hand carry different confidence, and only the driver knows which is right.
//
// There is deliberately no edit control. F5 owns `Stop.appointment_*`, and M5
// building a load-field editor would cross a foundation boundary. Logged as F5 debt.
function hm(iso) {
  return iso ? iso.slice(11, 16) : null;
}
const apptWindow = computed(() => {
  const start = hm(live.value?.appointment);
  const end = hm(live.value?.appointment_end);
  if (!start) return null;
  return end ? `${start}–${end}` : start;
});
const apptSourceKey = computed(() => {
  const src = live.value?.appointment_source;
  return src ? `load.appt_from.${src}` : null;
});

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

// AI-CONTEXT: §10.2's "state-dependent single CTA (Arm stop -> Snap BOL -> Send
// notice -> Generate claim)" — one rung at a time, and the ORDER is the spec's.
//
// It decides which action is PRIMARY, not which are permitted. Snap BOL outranking
// Generate claim reflects that a claim filed without the BOL is a weaker claim, but
// a driver at a receiver that has not produced paperwork yet must still be able to
// file — so the rungs the ladder passes over stay reachable as secondary text
// controls. A ladder that removed capability would be a gate, and §10.2 asks for
// guidance.
const rung = computed(() => {
  if (!live.value) return "start";
  if (isFiled.value) return null;
  if (preArrival.value) return "arrive";
  if (!bolCaptured.value) return "bol";
  if (accruing.value && !noticeSent.value) return "notice";
  if (accruing.value) return "claim";
  return null; // arrived, BOL filed, still inside free time: nothing is owed yet
});

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
    <p v-if="incidentToast" class="toast" role="status">{{ incidentToast }}</p>

    <section class="card meter-card" :class="{ 'meter-card--sample': !live }">
      <span v-if="!live" class="sample-tag">{{ t("load.sample") }}</span>
      <TheMeter :label="meterLabel" :figure="meterFigure" :variant="variant" :status="meterStatus" />
    </section>
    <p v-if="!live && !isDriving" class="sample-hint">{{ t("load.sample_hint") }}</p>

    <template v-if="!isDriving">
      <div class="context">
        <span class="context__name">{{ stopName }}</span>
        <span class="context__meta">{{ stopMeta }}</span>
        <!-- the window, early, in Mono like every other time figure (T-2) -->
        <span v-if="apptWindow" class="context__appt">
          {{ t("load.appointment") }}
          <span class="context__window">{{ apptWindow }}</span>
        </span>
        <span v-if="apptSourceKey" class="context__source">{{ t(apptSourceKey) }}</span>
      </div>

      <section class="card">
        <h2 class="card__title">{{ t("load.evidence") }}</h2>
        <ul class="checklist">
          <li class="checklist__item">
            <Check v-if="bolCaptured" :size="20" :stroke-width="2" class="ok" aria-hidden="true" />
            <Camera v-else :size="20" :stroke-width="2" aria-hidden="true" />
            {{ t("load.bol") }}
          </li>
          <li class="checklist__item">
            <Check v-if="photosDone" :size="20" :stroke-width="2" class="ok" aria-hidden="true" />
            <Camera v-else :size="20" :stroke-width="2" aria-hidden="true" />
            {{ t("load.photos") }}
            <span v-if="photosRequired" class="checklist__count">
              {{ photosCaptured }}/{{ photosRequired }}
            </span>
          </li>
          <li class="checklist__item">
            <Send :size="20" :stroke-width="2" :class="{ ok: noticeSent }" aria-hidden="true" />
            {{ noticeSent ? t("load.notice_sent_ok") : t("load.notice_sent") }}
          </li>
        </ul>
        <button
          v-if="live"
          class="card__link"
          type="button"
          @click="router.push(`/load/${activeStopId}/evidence`)"
        >
          {{ t("evidence.view_all") }}
        </button>
      </section>

      <!-- arrive -> accrue -> FILE: the loop closes into a GPS-backed claim -->
      <button
        v-if="isFiled"
        class="filed"
        type="button"
        @click="router.push(`/claim/${activeStopId}`)"
      >
        <Check :size="20" :stroke-width="2" class="ok" aria-hidden="true" />
        <span>{{ t("load.filed") }} · {{ formatMoney(filedAmount) }}</span>
        <span class="filed__link">{{ t("claim.view") }}</span>
      </button>

      <!-- §10.2: ONE state-dependent CTA. The ladder picks the rung; the rungs it
           passes over stay reachable below as secondary text controls. -->
      <button v-if="rung === 'arrive'" class="cta" type="button" @click="onArrive">
        {{ t("load.arrive") }}
      </button>
      <button v-else-if="rung === 'bol'" class="cta" type="button" @click="snapping = true">
        {{ t("load.cta.bol") }}
      </button>
      <button v-else-if="rung === 'notice'" class="cta" type="button" @click="onSendNotice">
        {{ t("load.cta.notice") }}
      </button>
      <button v-else-if="rung === 'claim'" class="cta" type="button" @click="onGenerateClaim">
        {{ t("load.cta.claim") }}
      </button>

      <!-- passed-over rungs: still available, never competing for the eye -->
      <button
        v-if="accruing && !isFiled && rung !== 'claim'"
        class="cta cta--text"
        type="button"
        @click="onGenerateClaim"
      >
        {{ t("load.cta.claim") }}
      </button>
      <button
        v-if="accruing && !noticeSent && !isFiled && rung !== 'notice'"
        class="cta cta--text"
        type="button"
        @click="onSendNotice"
      >
        {{ t("load.cta.notice") }}
      </button>
      <button
        v-if="live && !preArrival && !bolCaptured && rung !== 'bol'"
        class="cta cta--text"
        type="button"
        @click="snapping = true"
      >
        {{ t("load.cta.bol") }}
      </button>
      <p v-if="noticeMsg" class="notice-msg">{{ noticeMsg }}</p>

      <!-- M5-FR2: camera-first cargo-condition capture for the active stop -->
      <button v-if="live" class="cta cta--text" type="button" @click="router.push('/protection/condition')">
        {{ t("cond.start") }}
      </button>

      <!-- M5-FR4: log an incident (damage / refusal / unsafe) for the active stop -->
      <!-- FR4: what you just filed is one tap away while it is still on your mind.
           Same evidence surface the condition packs use; the kind rides the query. -->
      <button
        v-if="lastIncidentId"
        class="cta cta--text"
        type="button"
        @click="router.push(`/load/${lastIncidentId}/evidence?kind=incident`)"
      >
        {{ t("incident.view") }}
      </button>
      <button v-if="live" class="cta cta--text" type="button" @click="reporting = true">
        {{ t("incident.title") }}
      </button>

      <button v-if="live" class="cta cta--text" type="button" @click="endLoad">{{ t("load.end") }}</button>

      <!-- §10.2's empty state: "Add a load (rate-con photo import) as the ONE action".
           PRD §108 calls the parsed rate con the primary way a load is created; the
           manual form lives inside that sheet as the fallback for a rate con the
           parse cannot read, rather than competing with it out here. -->
      <button v-if="!live" class="cta" type="button" @click="importing = true">
        {{ t("load.rc_add") }}
      </button>

      <!-- M8: pre-acceptance decision — cross-link to the true-profit calculator (NAV-5) -->
      <button
        v-if="live"
        class="cta cta--text"
        type="button"
        @click="router.push('/load/calc')"
      >
        {{ t("load.check_profit") }}
      </button>

      <BottomSheet :open="reporting" :title="t('incident.title')" @close="reporting = false">
        <IncidentSheet @filed="onIncidentFiled" />
      </BottomSheet>

      <BottomSheet :open="importing" :title="t('load.rc_add')" @close="importing = false">
        <RateConImportSheet @created="onLoadCreated" />
      </BottomSheet>

      <BottomSheet :open="snapping" :title="t('load.cta.bol')" @close="snapping = false">
        <DocumentCaptureSheet
          :stop-id="activeStopId"
          fixed-type="bol"
          @captured="onBolCaptured"
        />
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
.card__link {
  margin-top: var(--s-3);
  padding: 0;
  background: transparent;
  border: none;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
  cursor: pointer;
}
.checklist {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
/* the count is a figure, so it is Mono and tabular like every other figure (T-2) */
.context__appt {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  font-size: var(--type-body-size);
  color: var(--text-2);
}
.context__window {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-1);
}
.context__source {
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.checklist__count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-2);
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
  width: 100%;
  margin-bottom: var(--s-2);
  padding: var(--s-3);
  border-radius: var(--r-card);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  font-size: var(--type-body-size);
  color: var(--text-1);
  text-align: left;
  cursor: pointer;
}
.filed__link {
  margin-left: auto;
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.toast {
  margin: 0 0 var(--s-2);
  padding: var(--s-3);
  border-radius: var(--r-control);
  background: var(--shield-500);
  color: var(--on-accent, #fff);
  font-size: var(--type-body-size);
  text-align: center;
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
