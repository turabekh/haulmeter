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
     rate con the parse cannot read.

     AI-CONTEXT: the empty state used to run a FIXTURE LOAD — a ticking $37.52
     detention Meter, a fake facility, a fake counterparty and a fake evidence
     checklist — with a "Sample" pill and a grey caption as the only marks that none
     of it was real. The loudest thing on a screen with no load was money the driver
     had not earned, and the fake stop row and checklist sat OUTSIDE the dashed card
     carrying no mark at all. §11.7 is "Never fake confidence" and §15.3 asks an empty
     state for one sentence of purpose and one starting action. It now renders the
     Meter AT REST — §9's own `--text-1` countdown color, no figure, no clock — and
     nothing that is not the driver's own. §23 entry 52.

     The fixture is gone rather than corrected, because its SHAPE was the defect
     underneath: `SAMPLE_STOP.appointment` was "07:00", a preformatted display string,
     where the live API returns an ISO timestamp. The demo therefore rendered a tidy
     "07:00 · Acme Brokerage" while production rendered
     "2026-07-27T04:10:50.993277+00:00 · TQL" — for every driver, in the one row §10.2
     specifies. A fixture whose shape does not match its endpoint hides the endpoint. -->
<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { Check, Camera, Send, Clock, TriangleAlert, ChevronDown } from "lucide-vue-next";
import { useRouter } from "vue-router";
import TheMeter from "../core/components/TheMeter.vue";
import BottomSheet from "../core/components/BottomSheet.vue";
import IncidentSheet from "../core/components/IncidentSheet.vue";
import DocumentCaptureSheet from "../core/components/DocumentCaptureSheet.vue";
import RateConImportSheet from "../core/components/RateConImportSheet.vue";
import { useDriverState } from "../core/state.js";
import { useI18n } from "../core/i18n.js";
import {
  permission as locationPermission,
  retryLocationPermission,
  lastEvents,
} from "../core/location.js";
import { computeDetentionState, meterVariant, formatClock, formatMoney } from "../core/meter.js";
import {
  activeStopId,
  setActiveStop,
  arriveAtStop,
  fetchMeter,
  fetchActiveLoad,
  fetchStopPackets,
  sendStopPacket,
  online,
  fetchLoadHistory,
  endActiveLoad,
  sendDetentionNotice,
  generateClaim,
  correctAppointment,
  exportProtectionPack,
  isAuthenticated,
} from "../core/api.js";

const { isDriving, isOnSite } = useDriverState();
const { t } = useI18n();
const router = useRouter();

const live = ref(null); // live meter response, or null (no load)
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
// AI-CONTEXT: which artifact the capture sheet is for. The sheet was hardcoded to the
// BOL because the BOL was the only row; A1's checklist asks for four more, and a row a
// driver can read but not satisfy is the same starved defect as a rule whose input
// never arrives. `openCapture` is how each row closes itself.
const snapType = ref("bol");
// §10.2's empty-state action. The manual "Start a load" form now lives inside this
// sheet as the fallback when a rate con cannot be read, rather than as a rival action.
const importing = ref(false);
// AI-CONTEXT: A1 req 5's cross-link (NAV-5 — cross-links are VERBS). A queue nobody can
// reach is a queue that fills up in private, which is worse than the feature being
// absent: the driver believes their paperwork is handled.
//
// ABSENT when empty, like the vendor section and the dwell-risk row. §10.2's Load tab is
// dense already, and a permanent "0 waiting" line is noise on the screen a driver reads
// at a dock.
const waitingPackets = ref([]);
// the packet under review, its editable recipient, and the send's own state. Held
// separately from `waitingPackets` so closing the sheet cannot leave a half-edited
// address written back into the list.
const reviewing = ref(false);
const reviewPacket = ref(null);
const reviewRecipient = ref("");
const reviewError = ref("");
const sending = ref(false);

// oldest first, as the API orders them: a packet from this morning should not be
// buried under one from an hour ago.
const nextPacket = computed(() => waitingPackets.value[0] ?? null);
const packetHeadline = computed(() => {
  const facility = nextPacket.value?.facility_name;
  return facility ? t("packet.ready", { place: facility }) : t("packet.ready_nowhere");
});
const packetReference = computed(() => nextPacket.value?.reference ?? "");
const reviewContents = computed(() => reviewPacket.value?.contents ?? []);
const reviewClaim = computed(() => reviewPacket.value?.claim ?? null);

function openReview() {
  const packet = nextPacket.value;
  if (!packet) return;
  reviewPacket.value = packet;
  reviewRecipient.value = packet.recipient || "";
  reviewError.value = "";
  reviewing.value = true;
}

async function loadPackets() {
  if (!isAuthenticated.value) return;
  try {
    waitingPackets.value = await fetchStopPackets();
  } catch {
    // §15.1: offline is a mode, not an error. `fetchStopPackets` serves its cache on a
    // network failure, so reaching here means there is genuinely nothing to show.
    waitingPackets.value = [];
  }
}

async function onSendPacket() {
  const packet = reviewPacket.value;
  if (!packet || sending.value) return;
  sending.value = true;
  reviewError.value = "";
  try {
    await sendStopPacket(packet.id, reviewRecipient.value.trim() || null);
    waitingPackets.value = waitingPackets.value.filter((p) => p.id !== packet.id);
    reviewing.value = false;
  } catch {
    // §12.4: what happened and what to do. The two cases a driver actually meets are a
    // dead dock and a deployment that cannot address itself (the 503), and both must
    // say so — a tap that appears to work and does nothing is the worse outcome,
    // because the driver would believe their paperwork went out.
    reviewError.value = online.value ? t("packet.send_failed") : t("packet.offline");
  } finally {
    sending.value = false;
  }
}
// §10.2's single-CTA rule, honoured without stranding capability: the rungs the
// ladder passes over and this stop's other actions live one tap away in a sheet.
const more = ref(false);
// AI-CONTEXT: where a finished load goes. Ending a load used to leave no way back to
// it — its evidence log, condition captures and stop-scoped BOL all still stored with
// nothing reaching them. An evidence pack is worth having precisely because it can be
// produced weeks later when a broker disputes it.
//
// §10.2 is silent on history, and navigation is a never-improvise category (§22), so
// this shape is the owner's decision logged in §23: a tertiary control on the Load tab
// opening a sheet (NAV-3), because a load is what this tab is about.
const history = ref([]);
const historyOpen = ref(false);
// AI-CONTEXT: a finished load is named by its ROUTE (§23 entry 74). The row showed
// the first stop's facility alone, so a pickup-and-delivery load was indistinguishable
// from a single delivery to the pickup's dock — and the money beside it was the
// pickup's claim, not the load's.
const expanded = ref(new Set());
const loadExportFailed = ref(null);
// a one-stop load has nothing to expand, so the row goes where it always went
function openRow(h) {
  if ((h.stops?.length ?? 0) < 2) return go(`/load/${h.stop_id}/evidence`);
  const next = new Set(expanded.value);
  next.has(h.load_id) ? next.delete(h.load_id) : next.add(h.load_id);
  expanded.value = next;
}

async function exportLoad(h) {
  try {
    const pack = await exportProtectionPack("load", h.load_id);
    if (pack && typeof document !== "undefined") {
      const a = document.createElement("a");
      a.href = pack.url;
      a.download = pack.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(pack.url), 30000);
    }
  } catch {
    // §12.4: say what happened. An empty catch here is the defect entry 72 records —
    // a control that runs, fails, and leaves the screen exactly as it was.
    loadExportFailed.value = h.load_id;
    setTimeout(() => (loadExportFailed.value = null), 6000);
  }
}

function routeLabel(h) {
  return h.destination_name ? `${h.facility_name} → ${h.destination_name}` : h.facility_name;
}
async function openHistory() {
  historyOpen.value = true;
  try {
    history.value = (await fetchLoadHistory()).loads;
  } catch {
    /* offline: show the last-known list rather than an error screen */
  }
}
function go(path) {
  more.value = false;
  router.push(path);
}
async function onLoadCreated() {
  importing.value = false;
  await loadMeter();
}
async function onBolCaptured() {
  snapping.value = false;
  await loadMeter(); // the checklist row closes the moment the document lands
}
function openCapture(row) {
  if (row.captured) return; // nothing to do; re-filing is the Docs tab's job
  snapType.value = row.item;
  snapping.value = true;
}
const filed = ref(null); // the generated claim result, once filed
// §15.5 shows the card for a permission the DRIVER has to restore. "unavailable"
// (a desktop browser, hardware off) is not that — there is no one-tap fix for it, so
// offering one would be the dead-control pattern.
const locationDenied = computed(() => locationPermission.value === "denied");
// FR1's correction. `datetime-local` wants "YYYY-MM-DDTHH:mm" with no zone.
const apptFixOpen = ref(false);
const apptDraft = ref("");
const apptSaving = ref(false);
function openApptFix() {
  apptDraft.value = live.value?.appointment ? String(live.value.appointment).slice(0, 16) : "";
  apptFixOpen.value = true;
}
async function saveAppointment() {
  if (!activeStopId.value || !apptDraft.value) return;
  apptSaving.value = true;
  try {
    await correctAppointment(activeStopId.value, new Date(apptDraft.value).toISOString());
    apptFixOpen.value = false;
    await loadMeter(); // the window AND its provenance both change
  } catch {
    /* offline: the window is unchanged and the sheet stays open with what was typed */
  } finally {
    apptSaving.value = false;
  }
}
let timer = null;

// no load: the Meter rests. Nothing ticks, nothing is owed, nothing is invented.
function clearLoad() {
  live.value = null;
  arrivalMs.value = null;
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
    setActiveStop(null); // stale/offline -> there is no load to show
    clearLoad();
  }
}

onMounted(async () => {
  // A1: what is waiting for this driver to look at. Failure is silent on purpose — the
  // Load tab's job is the meter, and a paperwork fetch that 500s must not take the
  // detention clock down with it.
  await loadPackets();
  // no locally-remembered stop? ask the server if this driver has one armed
  // (fresh-device resume) before settling on the resting Meter.
  if (!activeStopId.value && isAuthenticated.value) {
    try {
      await fetchActiveLoad();
    } catch {
      /* offline — the Meter rests below */
    }
  }
  if (activeStopId.value) await loadMeter();
  else clearLoad();
  timer = setInterval(() => (now.value = Date.now()), 1000);
});
onUnmounted(() => timer && clearInterval(timer));

// AI-CONTEXT: the card has to ARRIVE, and until this watcher it could not.
//
// The packet is drafted when the server sees the EXIT, and this tab read the queue
// once on mount — so a driver watching the Meter as they pull off the dock saw
// nothing, and the paperwork appeared only if they happened to leave the tab and come
// back. That is the same "it was done and I could not find it" failure the card exists
// to fix, one layer down.
//
// `lastEvents` is F3's own seam for exactly this ("a surface can watch this to react
// to an EXIT without polling the meter"), so no new polling and no new endpoint.
watch(lastEvents, (events) => {
  if ((events || []).some((e) => e.event_type === "EXIT")) loadPackets();
});

const freeMin = computed(() => live.value?.free_time_minutes ?? 0);
const rateCents = computed(() => live.value?.rate_cents_per_hour ?? 0);
const preArrival = computed(() => !!live.value && live.value.phase === "not_arrived");

const stopName = computed(() => live.value?.facility_name ?? "");
// AI-CONTEXT: the counterparty ALONE. This row used to append the appointment, and
// the appointment arrives from the API as an ISO timestamp — so live drivers read
// "2026-07-27T04:10:50.993277+00:00 · TQL" here. §10.2's anatomy asks the stop
// context for facility, appointment and counterparty; the appointment has its own
// row below with its window and its source, which is the one that can say WHERE the
// value came from (M5-FR1). Printing it twice was the other half of the defect.
const stopMeta = computed(() => live.value?.counterparty ?? "");
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

// AI-CONTEXT: A1 requirement 1 — the paperwork rows are CONFIGURATION (F13), per stop
// type, not one hardcoded BOL line. A driver dropping a load has a POD to photograph
// and no seal to record; asking for the wrong artifact is how a checklist teaches
// someone to ignore it.
//
// `kind === "document"` only. `cargo_condition` is also on the configured checklist and
// the photos row below already renders it WITH its 2/4 denominator — two rows saying the
// same thing in different words is worse than one.
const docChecklist = computed(() => {
  const rows = live.value?.checklist;
  if (!Array.isArray(rows)) {
    // an offline payload cached before A1 carries only the single flag. Rendering the
    // old row is truthful; rendering nothing would tell a driver this stop needs no
    // paperwork at all, which is the one answer that is never right.
    return [{ item: "bol", captured: bolCaptured.value, required: true }];
  }
  return rows.filter((r) => r.kind === "document");
});

// §16: status is colour AND icon AND label. The label has to flip too — the glyph alone
// is what a driver misses. `damage` flips to "No damage recorded" rather than a
// not-captured phrasing, because a clean stop is complete, not deficient.
function docLabel(row) {
  return t(`load.doc.${row.item}${row.captured ? "" : "_missing"}`);
}
const nextStop = computed(() => live.value?.next_stop ?? null);

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

// AI-CONTEXT: M5-FR1's verdict, which had no screen (§23 entry 58).
//
// `within_window` is computed and filed on EVERY arrival — in or out of the window,
// opted in or not, because the artifact is the driver's own protection. It reached
// nothing: the only place the API exposed it was the `/arrive` response, which
// `onArrive` discards, so a reload lost it. Meanwhile FR5's protection summary counts
// FOUR documented items and §10.2's checklist rendered three.
//
// The row is a labelled figure, not a sentence: `t()` has no interpolation (F15 debt),
// and this codebase already says "Photos 0/4" and "Appointment 04:26" rather than
// concatenating fragments (§12.5). The window it was judged against is two lines
// above, so repeating it here would be the duplication this tab keeps growing.
const onTime = computed(() => live.value?.on_time ?? null);
const arrivedAt = computed(() => hm(live.value?.arrived_at));

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

// AI-CONTEXT: BEFORE ARRIVAL, the Meter counts down to the appointment (§23 entry 57).
//
// It used to render the appointment as a static `08:26` — the same figure the
// Appointment row states two lines below it, in the largest type on the screen, never
// moving. §9 defines this element as "the counting figure that means your time is
// being measured", so a clock face that never counts is the signature element used as
// a label, and the duplication was the tell.
//
// Seconds to the appointment IS measured time and does tick. Past the appointment it
// counts up instead and takes `marker` — an existing §9 token for exactly this
// urgency, not a new colour — because a driver running late is the case where the
// figure matters most.
const apptMs = computed(() => {
  const iso = live.value?.appointment;
  return iso ? Date.parse(iso) : null;
});
const apptDeltaSeconds = computed(() =>
  apptMs.value === null ? null : Math.round((apptMs.value - now.value) / 1000),
);
const apptPassed = computed(() => apptDeltaSeconds.value !== null && apptDeltaSeconds.value < 0);

// once a claim is filed the Meter FREEZES at the filed amount — the clock stops
// ticking, so what you see matches the claim you filed (§9). With no load it rests:
// §9's own countdown colour (`--text-1`), an em-dash where the figure goes, and no
// status line — the same component in the same place, saying it has nothing to count.
const meterLabel = computed(() => {
  if (!live.value) return t("load.empty_title");
  if (preArrival.value) {
    if (apptDeltaSeconds.value === null) return t("load.waiting");
    return apptPassed.value ? t("load.appt_passed") : t("load.until_appt");
  }
  return withinFree.value ? t("load.free_time") : t("load.detention");
});
const meterFigure = computed(() => {
  if (!live.value) return "—";
  if (isFiled.value) return formatMoney(filedAmount.value);
  if (preArrival.value) {
    if (apptDeltaSeconds.value === null) return "—";
    return formatClock(Math.abs(apptDeltaSeconds.value));
  }
  return withinFree.value
    ? formatClock(state.value.freeTimeRemainingSeconds)
    : formatMoney(state.value.amountCents);
});
const meterStatus = computed(() => {
  if (!live.value) return "";
  if (isFiled.value) return t("load.filed_frozen");
  return preArrival.value || withinFree.value
    ? ""
    : `${formatClock(state.value.detentionSeconds)} · $${Math.round(rateCents.value / 100)}/h`;
});
const variant = computed(() => {
  if (!live.value) return "countdown";
  if (preArrival.value) return apptPassed.value ? "warning" : "countdown";
  return meterVariant(state.value);
});

// AI-CONTEXT: §10.2's "state-dependent single CTA (Arm stop -> Snap BOL -> Send
// notice -> Generate claim)" — one rung at a time, and the ORDER is the spec's.
//
// It decides which action is PRIMARY, not which are permitted. Snap BOL outranking
// Generate claim reflects that a claim filed without the BOL is a weaker claim, but
// a driver at a receiver that has not produced paperwork yet must still be able to
// file — so the rungs the ladder passes over stay reachable as secondary text
// controls. A ladder that removed capability would be a gate, and §10.2 asks for
// guidance.
// AI-CONTEXT: a claim is only offered once there is something to claim (§23 entry 57).
//
// `accruing` turns true the instant free time runs out, when the amount is still
// $0.00, and the claim controls carried no amount guard — so a driver could file a
// claim worth nothing. That is not merely useless: §9 FREEZES the Meter at the filed
// amount, and the UI hides every claim control once `isFiled`, so the screen then
// reads "$0.00 · Claim filed — clock stopped" while detention goes on accruing, with
// no way back. Measured: filed at zero, three minutes later the meter still said
// $0.00 while the server had $4.42, and the only route to the correction was the API.
//
// Guarding the OFFER is the fix rather than unfreezing the Meter, because the freeze
// is deliberate (§9: what you see matches the claim you filed). Nothing is taken away
// — the driver waits seconds, not minutes, for a claim that is worth filing.
const claimable = computed(() => accruing.value && state.value.amountCents > 0);

const rung = computed(() => {
  if (!live.value) return "start";
  if (isFiled.value) return null;
  if (preArrival.value) return "arrive";
  if (!bolCaptured.value) return "bol";
  if (accruing.value && !noticeSent.value) return "notice";
  if (claimable.value) return "claim";
  return null; // arrived, BOL filed, and nothing owed yet
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
  // `claimable` also gates the controls; this is the same rule at the point of action,
  // so a stale render or a double tap cannot file a claim worth nothing.
  if (!activeStopId.value || filed.value || !claimable.value) return;
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
  history.value = []; // re-read on next open: this load just joined it
  const stopId = activeStopId.value;
  filed.value = null;
  if (!stopId) {
    setActiveStop(null);
    clearLoad();
    return;
  }
  // durable: departs the stop server-side, and hands back the next one if the route
  // has further to run (§23 entry 69). Only the last stop empties this tab.
  const next = await endActiveLoad(stopId);
  // leaving by HAND drafts the packet too (api/load.py) — §15.5's "degrade to one-tap,
  // never to nothing". Re-read so the card arrives on the tap, not on the next mount.
  await loadPackets();
  if (next) await loadMeter();
  else clearLoad();
}
</script>

<template>
  <div class="load">
    <p v-if="incidentToast" class="toast" role="status">{{ incidentToast }}</p>

    <!-- AI-CONTEXT: A1 req 5's RESULT, arriving where the driver already is.
         (v2 of this surfacing; the first was a text link and is described below.)

         The automation was correct and invisible. EXIT drafted the packet server-side,
         and the only thing that ever said so on this tab was a `packet.waiting` text
         link — "2 waiting" — that NAVIGATED the driver to /protection/packets to hunt
         for their own paperwork. For a driver who is not comfortable with phones, that
         hunt is the whole failure: the work was done and they could not find it.

         So the finished paperwork ARRIVES as a card at the top of the tab, and Review &
         send opens a sheet OVER this screen (NAV-3). The archive at
         /protection/packets stays as history — this added an inline door, it did not
         remove one.

         ONE action on the card, not two. §8 gives a card "title + figure/status + one
         action max", and §22.2's heuristics are "remove rather than add" and "one
         action rather than two" — so the preview of what is inside lives in the SHEET,
         which is where the driver is reviewing anyway, rather than as a second control
         competing with the Primary. §23 entry 120.

         DRIVING (SM-3): a one-line glance and NO interactive Send. Forbidden #11 bans
         interactive prompts at speed, and a document going to a broker under the
         driver's name is the least appropriate decision to put in front of someone at
         65 mph. The packet is durable; it waits. -->
    <section v-if="waitingPackets.length" class="card packet-card">
      <h2 class="packet-card__title">{{ packetHeadline }}</h2>
      <p v-if="packetReference" class="packet-card__ref">{{ packetReference }}</p>
      <p v-if="isDriving" class="packet-card__driving">{{ t("packet.ready_driving") }}</p>
      <button v-else class="cta packet-card__cta" type="button" @click="openReview">
        {{ t("packet.review") }}
      </button>
    </section>

    <section class="card meter-card">
      <TheMeter :label="meterLabel" :figure="meterFigure" :variant="variant" :status="meterStatus" />
    </section>
    <!-- AI-CONTEXT: §15.5's degraded-location card, which became load-bearing the
         moment the meter started depending on real positions (F3's ping seam).
         "A single persistent Load-tab card explaining exactly what stops working
         (the meter arms manually) with a one-tap fix — never nags beyond that card."
         So: ONE card, on THIS tab, stating the consequence rather than the
         permission, and no toast, no banner, no second ask. It is deliberately not
         `flare` — nothing is broken, the app is just working with less. -->
    <section v-if="locationDenied && !isDriving" class="degraded" role="status">
      <p class="degraded__text">{{ t("load.geo_off") }}</p>
      <button class="degraded__fix" type="button" @click="retryLocationPermission">
        {{ t("load.geo_fix") }}
      </button>
    </section>

    <!-- §15.3: one sentence of what this is, then one action to start. -->
    <p v-if="!live && !isDriving" class="hint">{{ t("load.empty_hint") }}</p>
    <!-- §10.2 DRIVING: "collapses to Meter-only glance card + voice hint". The hint
         names a real destination — VoiceSheet lives on the Map tab — so this is a
         label pointing somewhere, not the dead-control pattern §23 forbids. It is
         text rather than a control: Forbidden #11 rules out interactive prompts at
         speed, and the driver reaches voice where it already is. -->
    <p v-if="isDriving" class="hint">{{ t("voice.unavailable") }}</p>

    <template v-if="!isDriving">
      <!-- everything from here to the ladder describes a REAL stop. With no load
           there is no stop to describe, so none of it renders — an empty state does
           not get to borrow the shape of a working one. -->
      <div v-if="live" class="context">
        <span class="context__name">{{ stopName }}</span>
        <span v-if="stopMeta" class="context__meta">{{ stopMeta }}</span>
        <!-- the window, early, in Mono like every other time figure (T-2) -->
        <span v-if="apptWindow" class="context__appt">
          {{ t("load.appointment") }}
          <span class="context__window">{{ apptWindow }}</span>
        </span>
        <span v-if="apptSourceKey" class="context__source">{{ t(apptSourceKey) }}</span>
        <!-- AI-CONTEXT: FR1's other half. The window is shown with its provenance so a
             driver can catch a MIS-PARSED time while they are still approaching — and
             until now the screen said "this may be wrong" and offered nothing to do
             about it. F5 owns the field, so the write goes through its own endpoint.
             Withdrawn at speed like every other acting control (SM-3). -->
        <button
          v-if="live && !isDriving"
          class="context__fix"
          type="button"
          @click="openApptFix"
        >
          {{ apptWindow ? t("load.appt_fix") : t("load.appt_add") }}
        </button>
      </div>

      <section v-if="live" class="card">
        <h2 class="card__title">{{ t("load.evidence") }}</h2>
        <ul class="checklist">
          <!-- AI-CONTEXT: the LABEL carries the state, not just the icon. This row
               read "BOL captured" whether or not one had been, so the only thing
               saying otherwise was a camera glyph — and §16 requires status to be
               color AND icon AND label, precisely because the glyph alone is what a
               driver misses. The other two rows already flip ("Notice not sent",
               "0/4"); this was the one that could only ever read as done. -->
          <!-- M5-FR1's verdict — the fourth item FR5 has always computed. Three
               states, and §16 gives each colour AND icon AND label, because the glyph
               alone is what a driver misses. -->
          <li class="checklist__item">
            <Check v-if="onTime === true" :size="20" :stroke-width="2" class="ok" aria-hidden="true" />
            <TriangleAlert
              v-else-if="onTime === false"
              :size="20"
              :stroke-width="2"
              class="late"
              aria-hidden="true"
            />
            <Clock v-else :size="20" :stroke-width="2" aria-hidden="true" />
            <span :class="{ late: onTime === false }">
              {{ onTime === null ? t("load.arrival_pending") : onTime ? t("load.on_time") : t("load.late") }}
            </span>
            <span v-if="arrivedAt" class="checklist__count">{{ arrivedAt }}</span>
          </li>
          <li v-for="row in docChecklist" :key="row.item" class="checklist__item">
            <template v-if="row.captured">
              <Check :size="20" :stroke-width="2" class="ok" aria-hidden="true" />
              {{ docLabel(row) }}
            </template>
            <button v-else class="checklist__snap" type="button" @click="openCapture(row)">
              <Camera :size="20" :stroke-width="2" aria-hidden="true" />
              {{ docLabel(row) }}
            </button>
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

      <!-- §10.2's anatomy ends here: the next-stop preview. A driver weighing whether
           to wait out detention is really asking what it costs them later, and the
           answer is the appointment they have to make next. -->
      <section v-if="nextStop" class="next">
        <span class="next__label">{{ t("load.next_stop") }}</span>
        <span class="next__name">{{ nextStop.facility_name }}</span>
        <span v-if="nextStop.appointment" class="next__appt">{{ nextStop.appointment.slice(11, 16) }}</span>
      </section>

      <!-- arrive -> accrue -> FILE: the loop closes into a GPS-backed claim -->
      <button
        v-if="isFiled"
        class="filed"
        type="button"
        @click="router.push(`/claim/${activeStopId}`)"
      >
        <!-- AI-CONTEXT: this row said "Claim filed · $0.00" directly under a Meter
             already reading "$0.00 / Claim filed — clock stopped" — the same fact and
             the same figure, twice, adjacent. What the Meter cannot do is take you to
             the claim, so that is all this row is now. -->
        <Check :size="20" :stroke-width="2" class="ok" aria-hidden="true" />
        <span>{{ t("claim.view") }}</span>
      </button>

      <!-- §10.2: ONE state-dependent CTA. The ladder picks the rung; the rungs it
           passes over stay reachable below as secondary text controls. -->
      <button v-if="rung === 'arrive'" class="cta" type="button" @click="onArrive">
        {{ t("load.arrive") }}
      </button>
      <button v-else-if="rung === 'bol'" class="cta" type="button" @click="openCapture({ item: 'bol' })">
        {{ t("load.cta.bol") }}
      </button>
      <button v-else-if="rung === 'notice'" class="cta" type="button" @click="onSendNotice">
        {{ t("load.cta.notice") }}
      </button>
      <button v-else-if="rung === 'claim'" class="cta" type="button" @click="onGenerateClaim">
        {{ t("load.cta.claim") }}
      </button>

      <!-- AI-CONTEXT: passed-over rungs, and why they are a ROW rather than a stack.
           §8 allows exactly one Primary per screen and grades the rest Secondary
           (outline) then Tertiary (text) — but these were emitted full-bleed, centred
           and accent-coloured under a full-bleed accent Primary, so three tertiary
           controls rendered in the Primary's silhouette. The screen read as four
           stacked buttons, which is the six-button problem §10.2's single-CTA rule
           exists to prevent, reduced in count and not in kind. Auto width in a
           wrapping row keeps them reachable (48 dp, §6.5) while giving the Primary
           back the only full-width shape on the screen.

           The ORDER is §10.2's ladder — Snap BOL -> Send notice -> Generate claim.
           These emitted claim above notice, so the nearer rung sat below the further
           one and the list read against the sequence it was derived from. -->
      <div v-if="live" class="rungs">
        <button
          v-if="!preArrival && !bolCaptured && rung !== 'bol'"
          class="rungs__item"
          type="button"
          @click="openCapture({ item: 'bol' })"
        >
          {{ t("load.cta.bol") }}
        </button>
        <button
          v-if="accruing && !noticeSent && !isFiled && rung !== 'notice'"
          class="rungs__item"
          type="button"
          @click="onSendNotice"
        >
          {{ t("load.cta.notice") }}
        </button>
        <button
          v-if="claimable && !isFiled && rung !== 'claim'"
          class="rungs__item"
          type="button"
          @click="onGenerateClaim"
        >
          {{ t("load.cta.claim") }}
        </button>
        <!-- AI-CONTEXT: §5's ON_SITE, narrowed to this tab by the owner (§23 entry 64).
             §5 asks for capture actions "one tap from anywhere via a persistent action
             chip"; an app-wide chip is a new component pattern AND navigation
             structure, both §22 never-improvise, so the decision was to deliver the
             benefit inside a surface that already exists. Cargo condition is two taps
             the rest of the time (More -> Capture) and one while the truck is parked
             at the dock, which is the only place those photographs can be taken. It
             stays in the More sheet as well: this is a shortcut, not a move. -->
        <button
          v-if="isOnSite"
          class="rungs__item"
          type="button"
          @click="router.push('/protection/condition')"
        >
          {{ t("cond.start") }}
        </button>

        <!-- §10.2: "state-dependent SINGLE CTA". These four are real capabilities and
             none has another home, so they move behind one control into a sheet
             (NAV-3) rather than stacking six buttons under the Meter. Scoped to this
             stop, so it is not a nav drawer (Forbidden #2). -->
        <!-- the modifier is how the layout harness opens this sheet. It cannot click
             by label: every surface is measured under en, xx-XL and pa, so any
             text-based step would break in two of the three. -->
        <button class="rungs__item rungs__item--more" type="button" @click="more = true">
          {{ t("load.more") }}
        </button>
      </div>
      <p v-if="noticeMsg" class="notice-msg">{{ noticeMsg }}</p>

      <!-- §10.2's empty state: "Add a load (rate-con photo import) as the ONE action".
           PRD §108 calls the parsed rate con the primary way a load is created; the
           manual form lives inside that sheet as the fallback for a rate con the
           parse cannot read, rather than competing with it out here. -->
      <button v-if="!live" class="cta" type="button" @click="importing = true">
        {{ t("load.rc_add") }}
      </button>

      <!-- §23-approved: history lives on the Load tab, because a load is what this tab
           is about — tertiary, so §10.2's one empty-state action stays the loud thing.
           §10.2 is silent on history and navigation is a never-improvise category
           (§22), so the shape was the owner's decision rather than a reading. -->
      <button v-if="!live" class="cta cta--text" type="button" @click="openHistory">
        {{ t("load.history") }}
      </button>

      <!-- AI-CONTEXT: the review sheet — A1 req 5 and req 6, over the Load tab.
           Two labelled SECTIONS under ONE Send (owner decision, 2026-08-02): the
           paperwork always, the claim when the driver has already filed one. The
           claim section REPORTS; it never files. Filing opens a receivable, increments
           the broker's claim history and freezes the Meter (§9) — §12.2 requires the
           button to say exactly what it does, and a Send read as being about paperwork
           must not do that on the driver's behalf. The Send label changes with the
           bundle for the same reason. -->
      <BottomSheet
        :open="reviewing"
        :title="t('packet.review_title')"
        @close="reviewing = false"
      >
        <div v-if="reviewPacket" class="review">
          <p class="review__note">{{ t("packet.note") }}</p>

          <section class="review__section">
            <h3 class="review__label">{{ t("packet.section_paperwork") }}</h3>
            <p class="review__where">
              {{ reviewPacket.facility_name || t("load.facility") }}
              <span class="review__ref">{{ reviewPacket.reference || t("packet.no_reference") }}</span>
            </p>
            <!-- §11.7 applied to a document: what a driver is vouching for, named. An
                 empty stop says so rather than showing an empty list. -->
            <ul v-if="reviewContents.length" class="review__items">
              <li v-for="item in reviewContents" :key="item" class="review__item">
                <Check :size="16" :stroke-width="2" class="ok" aria-hidden="true" />
                {{ t(`load.doc.${item}`) }}
              </li>
            </ul>
            <p v-else class="review__empty">{{ t("packet.contents_none") }}</p>
          </section>

          <section v-if="reviewClaim" class="review__section">
            <h3 class="review__label">{{ t("claim.title") }}</h3>
            <p class="review__figure">{{ formatMoney(reviewClaim.amount_cents) }}</p>
          </section>

          <!-- A1 req 6: from the F5 registry, and EDITABLE. The address on file is a
               default, not a verdict — paperwork often goes to a different desk than
               the one the load was booked through. -->
          <label class="review__to">
            <span class="review__label">{{ t("packet.recipient_label") }}</span>
            <input
              v-model="reviewRecipient"
              class="review__input"
              type="email"
              inputmode="email"
              :placeholder="t('packet.no_recipient')"
            />
          </label>

          <p v-if="reviewError" class="review__error" role="status">{{ reviewError }}</p>
          <button
            class="cta review__send"
            type="button"
            :disabled="sending"
            @click="onSendPacket"
          >
            {{ reviewClaim ? t("packet.send_with_claim") : t("packet.send") }}
          </button>
        </div>
      </BottomSheet>

      <BottomSheet :open="reporting" :title="t('incident.title')" @close="reporting = false">
        <IncidentSheet @filed="onIncidentFiled" />
      </BottomSheet>

      <!-- Each row carries only what that load PRODUCED. A load that captured nothing
           says so: empty money and evidence rows would read as data we lost rather
           than a quiet week. -->
      <BottomSheet :open="historyOpen" :title="t('load.history')" @close="historyOpen = false">
        <p v-if="!history.length" class="docs__empty">{{ t("load.history_empty") }}</p>
        <ul v-else class="hist">
          <li v-for="h in history" :key="h.load_id" class="hist__row">
            <button class="hist__main" type="button" @click="openRow(h)">
              <span class="hist__name">
                {{ routeLabel(h) }}
                <ChevronDown
                  v-if="h.stop_count > 1"
                  :size="16"
                  :stroke-width="2"
                  aria-hidden="true"
                />
              </span>
              <span class="hist__date">
                <!-- the load's own number, because a driver who runs the same lane
                     twice in a week gets rows identical in every other respect -->
                <template v-if="h.reference_number">{{ h.reference_number }} · </template
                >{{ h.created_at.slice(0, 10)
                }}<template v-if="h.stop_count > 1">
                  · {{ t("load.history_stops", { n: h.stop_count }) }}</template>
              </span>
            </button>
            <span v-if="h.detention_cents" class="hist__money">
              {{ formatMoney(h.detention_cents) }} · {{ t(`money.state.${h.claim_state}`) }}
            </span>
            <span v-else class="hist__quiet">{{ t("load.history_no_money") }}</span>
            <span v-if="h.evidence_count || h.documents.length" class="hist__has">
              {{ [
                h.evidence_count ? t("load.history_pack") : null,
                ...h.documents.map((d) => t(`docs.type.${d}`)),
              ].filter(Boolean).join(" · ") }}
            </span>
            <span v-else class="hist__quiet">{{ t("load.history_nothing") }}</span>

            <!-- §23-approved (entry 78): a route's row opens to its stops. Rolled-up
                 totals fixed what the row SAYS; the row still reached only stops[0],
                 so a driver who photographed both ends of a load could open half of
                 their own evidence. A one-stop load has nothing to open and goes
                 straight there instead, so the control's shape says what it does. -->
            <ul v-if="expanded.has(h.load_id)" class="hist__stops">
              <li v-for="s in h.stops" :key="s.stop_id">
                <button
                  class="hist__stop"
                  type="button"
                  @click="go(`/load/${s.stop_id}/evidence`)"
                >
                  <span class="hist__stopname">
                    {{ s.sequence + 1 }} · {{ t(`load.stop.${s.stop_type}`) }} ·
                    {{ s.facility_name }}
                  </span>
                  <span class="hist__stopmeta">
                    {{ s.detention_cents
                      ? formatMoney(s.detention_cents)
                      : t("load.history_no_money") }}
                    · {{ t("load.history_photos", { n: s.photo_count }) }}
                  </span>
                </button>
              </li>
              <li>
                <button class="hist__stop hist__export" type="button" @click="exportLoad(h)">
                  {{ t("load.history_export_load") }}
                </button>
                <p v-if="loadExportFailed === h.load_id" class="hist__quiet">
                  {{ t("evidence.export_failed") }}
                </p>
              </li>
            </ul>
          </li>
        </ul>
      </BottomSheet>

      <BottomSheet :open="more" :title="t('load.more')" @close="more = false">
        <ul class="more">
          <!-- M5-FR2: camera-first cargo-condition capture for the active stop -->
          <li><button class="more__item" type="button" @click="go('/protection/condition')">
            {{ t("cond.start") }}
          </button></li>
          <!-- M5-FR4: log an incident (damage / refusal / unsafe) -->
          <li><button class="more__item" type="button" @click="more = false; reporting = true">
            {{ t("incident.title") }}
          </button></li>
          <!-- FR4: what you just filed is one tap away while it is still on your mind -->
          <li v-if="lastIncidentId">
            <button class="more__item" type="button" @click="go(`/load/${lastIncidentId}/evidence?kind=incident`)">
              {{ t("incident.view") }}
            </button>
          </li>
          <!-- M8: pre-acceptance decision — cross-link to the calculator (NAV-5) -->
          <li><button class="more__item" type="button" @click="go('/load/calc')">
            {{ t("load.check_profit") }}
          </button></li>
          <!-- §12.2: the button says what will actually happen. On a route this leaves
               THIS dock and opens the next; only the last stop ends the load. -->
          <li><button class="more__item" type="button" @click="more = false; endLoad()">
            {{ nextStop ? t("load.leave_stop") : t("load.end") }}
          </button></li>
        </ul>
      </BottomSheet>

      <BottomSheet :open="importing" :title="t('load.rc_add')" @close="importing = false">
        <RateConImportSheet @created="onLoadCreated" />
      </BottomSheet>

      <BottomSheet
        :open="apptFixOpen && !isDriving"
        :title="t('load.appt_fix')"
        @close="apptFixOpen = false"
      >
        <p class="docs__empty">{{ t("load.appt_fix_hint") }}</p>
        <label class="appt__field">
          <span class="appt__label">{{ t("load.appointment") }}</span>
          <input v-model="apptDraft" class="appt__input" type="datetime-local" />
        </label>
        <button class="cta" type="button" :disabled="!apptDraft || apptSaving" @click="saveAppointment">
          {{ t("load.appt_save") }}
        </button>
      </BottomSheet>

      <BottomSheet
        :open="snapping"
        :title="snapType === 'bol' ? t('load.cta.bol') : t('load.capture_title')"
        @close="snapping = false"
      >
        <DocumentCaptureSheet
          :key="snapType"
          :stop-id="activeStopId"
          :fixed-type="snapType"
          @captured="onBolCaptured"
        />
      </BottomSheet>
    </template>
  </div>
</template>

<style scoped>
/* the cross-link reads as an action, not a banner: hairline card, thumb-height, and it
   is absent entirely when nothing waits (§10.2 keeps this tab dense with WORK) */
/* A1's review card. §8: title + status + ONE action, and no card scrolls internally. */
.packet-card__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-title-size);
  line-height: var(--type-body-line);
}
.packet-card__ref {
  margin: var(--s-1) 0 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
/* Forbidden #11: at speed this is a line of text, never a control. */
.packet-card__driving {
  margin: var(--s-2) 0 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.packet-card__cta {
  margin-top: var(--s-3);
}

.review {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.review__note,
.review__empty,
.review__where {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.review__section {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.review__label {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.review__ref {
  display: block;
  color: var(--text-3);
}
.review__items {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.review__item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  color: var(--text-1);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
/* §9/§6.2: money is Mono and tabular, and never truncated (Forbidden #5). */
.review__figure {
  margin: 0;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
  color: var(--ledger-500);
}
.review__to {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.review__input {
  min-height: 56px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.review__error {
  margin: 0;
  color: var(--flare-500);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}

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
/* calm, not red (§15.1's tone, applied to §15.5): the app still works, it just works
   with less. Hairline card, `marker` for the one word that matters. */
.degraded {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-bottom: var(--s-3);
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-left: 2px solid var(--marker-500);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.degraded__text {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-caption-line);
}
.degraded__fix {
  align-self: flex-start;
  min-height: 48px;
  padding: 0 var(--s-2);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.hint {
  margin: calc(var(--s-2) * -1) 0 var(--s-3);
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-caption-line);
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
/* §6.5 glove spec: this was an 18 dp tap target — the text's own line box — because
   it carried `padding: 0` and no height. It only ever renders on a LIVE load, which
   is the state the layout harness had never opened, so nothing measured it. */
.card__link {
  display: inline-flex;
  align-items: center;
  min-height: 48px;
  margin-top: var(--s-2);
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
.context__fix {
  align-self: flex-start;
  min-height: 48px;
  padding: 0 var(--s-2);
  margin-left: calc(var(--s-2) * -1);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.appt__field {
  display: block;
  margin-bottom: var(--s-3);
}
.appt__label {
  display: block;
  margin-bottom: var(--s-1);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.appt__input {
  width: 100%;
  min-height: 56px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
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
/* §6.5's glove spec: a checklist row a driver can act on is a real target, 48 dp tall.
   It inherits the row's type and colour rather than becoming a second kind of button —
   the affordance is that it is tappable, not that it looks like a CTA. */
.checklist__snap {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 48px;
  width: 100%;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-size: var(--type-body-size);
  color: var(--text-1);
  text-align: left;
  cursor: pointer;
}
.ok {
  color: var(--ledger-500);
}
/* late is a fact, not an alarm — `marker` is §9's urgency token, and §12.4 says an
   unblaming statement. The driver did not choose the traffic. */
.late {
  color: var(--marker-500);
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
.toast {
  margin: 0 0 var(--s-2);
  padding: var(--s-3);
  border-radius: var(--r-control);
  background: var(--shield-500);
  color: var(--on-accent);
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
/* §8 Tertiary: text, auto width, wrapping. Not the Primary's full-bleed silhouette
   — that shape belongs to the one action the ladder chose. Wraps rather than
   overflows, which is what xx-XL (+40%, §12.5) needs at 360 dp. */
.rungs {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--s-1) var(--s-3);
  margin-top: var(--s-2);
}
.rungs__item {
  min-height: 48px;
  padding: 0 var(--s-2);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.hist {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.hist__row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.hist__main {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  width: 100%;
  min-height: 48px;
  text-align: left;
  background: transparent;
}
.hist__name {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--type-body-size);
  color: var(--text-1);
}
/* §23 entry 78: the route, opened. Tokens only — this borrows the row's own type and
   spacing rather than introducing a scale for a nested list. */
.hist__stops {
  list-style: none;
  margin: var(--s-3) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  border-top: 1px solid var(--line-1);
  padding-top: var(--s-3);
}
.hist__stop {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-1);
  width: 100%;
  min-height: 48px;
  padding: var(--s-2) 0;
  background: none;
  border: 0;
  text-align: left;
  color: var(--text-1);
  font-size: var(--type-body-size);
  cursor: pointer;
}
.hist__stopname {
  color: var(--text-1);
}
.hist__stopmeta {
  color: var(--text-2);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
}
.hist__export {
  color: var(--shield-500);
}
.hist__date,
.hist__money {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-caption-size);
  color: var(--text-2);
}
.hist__has,
.hist__quiet {
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.more {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.more__item {
  width: 100%;
  min-height: 56px;
  text-align: left;
  background: transparent;
  color: var(--text-1);
  font-size: var(--type-body-size);
  border-bottom: 1px solid var(--line-1);
}
.next {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  margin-bottom: var(--s-3);
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.next__label {
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.next__name {
  flex: 1 1 auto;
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.next__appt {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
</style>
