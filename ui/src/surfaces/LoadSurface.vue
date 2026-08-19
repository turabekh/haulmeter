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
import {
  Check,
  Camera,
  Send,
  Clock,
  TriangleAlert,
  ChevronDown,
  ChevronRight,
} from "lucide-vue-next";
import { useRouter } from "vue-router";
import TheMeter from "../core/components/TheMeter.vue";
import Spinner from "../core/components/Spinner.vue";
import BottomSheet from "../core/components/BottomSheet.vue";
import IncidentSheet from "../core/components/IncidentSheet.vue";
import DocumentCaptureSheet from "../core/components/DocumentCaptureSheet.vue";
import RateConImportSheet from "../core/components/RateConImportSheet.vue";
import BrokerEmailField from "../core/components/BrokerEmailField.vue";
import { useDriverState, observePresence } from "../core/state.js";
import { useI18n } from "../core/i18n.js";
import {
  permission as locationPermission,
  retryLocationPermission,
  lastEvents,
  lastFix,
} from "../core/location.js";
import { computeDetentionState, meterVariant, formatClock, formatMoney } from "../core/meter.js";
import {
  activeStopId,
  setActiveStop,
  arriveAtStop,
  ArrivalTooFar,
  fetchMeter,
  fetchActiveLoad,
  fetchStopPackets,
  sendStopPacket,
  online,
  fetchLoadHistory,
  endActiveLoad,
  sendDetentionNotice,
  generateClaim,
  discardStopPacket,
  correctAppointment,
  isAuthenticated,
} from "../core/api.js";

const { isDriving, isOnSite } = useDriverState();
const { t } = useI18n();
const router = useRouter();

const live = ref(null); // live meter response, or null (no load)
const arrivalMs = ref(0); // null while a live load is pre-arrival
const endedNow = ref(null); // frozen `now` once M3 says the visit is over
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
// the confirm STEP inside the review sheet, and the write's own state. Separate from
// `sending` because the two buttons must be able to disable each other without either
// borrowing the other's spinner.
const confirmingDiscard = ref(false);
const discarding = ref(false);
const discardError = ref("");

// AI-CONTEXT: the NEWEST draft, and the difference is not cosmetic.
//
// The API orders the queue oldest-first, which is right for the ARCHIVE — a packet from
// this morning should not be buried under one from an hour ago. It is wrong for this
// card, because the card is not a queue: it says "You left <facility>. Your paperwork is
// ready", which is a claim about the stop the driver just walked away from.
//
// Found by walking it (HANDOFF-116). With two drafts waiting, the card announced the
// EXIT the driver had just made and then opened the sheet for the OLDER stop — whose
// contents line read "Nothing was captured at this stop" while the BOL they had
// photographed minutes earlier sat in the newer packet. Both stops were the same
// facility, so the headline was word-for-word identical and there was nothing on screen
// to tell them apart. A driver would have sent the wrong, empty document and had no way
// to notice.
//
// The rest of the queue is not lost: sending the newest reveals the next, and
// /protection/packets still lists them all oldest-first as history.
const nextPacket = computed(() => waitingPackets.value[waitingPackets.value.length - 1] ?? null);
const packetHeadline = computed(() => {
  const facility = nextPacket.value?.facility_name;
  return facility ? t("packet.ready", { place: facility }) : t("packet.ready_nowhere");
});
const packetReference = computed(() => nextPacket.value?.reference ?? "");
// where this paperwork goes, said BEFORE the tap rather than inside the sheet. §12.4
// asks an error to state what happened and what to do while the driver can still act,
// and a missing address is the one thing on this card they have to solve — HANDOFF-122
// §3: nothing in this product had ever written `contact_email`, so on most real loads
// the honest answer here is that there is no address yet.
const packetRecipient = computed(() => nextPacket.value?.recipient || "");
// what the pack would actually carry — an empty one is a claim with no evidence in it
const packetHasContents = computed(() => (nextPacket.value?.contents ?? []).length > 0);
// AI-CONTEXT: §8's "one Primary per screen", applied to the state that had TWO.
//
// With paperwork waiting and no load running, this tab rendered the packet card's
// Primary and the empty state's "Add a load" Primary as two identical full-bleed
// buttons ~200 dp apart, over a resting Meter reading "No load —" directly beneath a
// card saying "You left <dock>". Three defects in one screen: nothing said which
// action was the one to take, the screen contradicted itself, and the em-dash sat
// exactly where this product puts money, so "No load —" right after a drop reads as
// the detention having vanished.
//
// The two states are SEQUENCED rather than stacked. While paperwork waits it is the
// tab's single job; the Meter at rest, its hint and the second Primary stand down to
// the tertiary row below. Sending empties the queue and the ordinary §10.2 empty state
// returns with "Add a load" as the Primary. Nothing is removed — §22.2's first and
// fourth heuristics (remove rather than add · one action rather than two).
//
// NOT while DRIVING: §10.2 specifies the Meter-only glance card at speed, and the
// packet card is already a line of text with no control there (Forbidden #11).
const paperworkFirst = computed(
  () => !isDriving.value && !live.value && waitingPackets.value.length > 0,
);
const reviewContents = computed(() => reviewPacket.value?.contents ?? []);
const reviewClaim = computed(() => reviewPacket.value?.claim ?? null);

function openReview() {
  const packet = nextPacket.value;
  if (!packet) return;
  reviewPacket.value = packet;
  reviewRecipient.value = packet.recipient || "";
  reviewError.value = "";
  // a sheet that reopened on the confirm step would put a destructive button under a
  // driver who tapped Review — the step belongs to one visit, not to the packet.
  confirmingDiscard.value = false;
  discardError.value = "";
  reviewing.value = true;
}

async function onDiscardPacket() {
  const packet = reviewPacket.value;
  if (!packet || discarding.value) return;
  discarding.value = true;
  discardError.value = "";
  try {
    await discardStopPacket(packet.id);
    waitingPackets.value = waitingPackets.value.filter((p) => p.id !== packet.id);
    reviewing.value = false;
  } catch {
    // §12.4, and NOT the offline wording Send uses. A discard is not queued (see
    // api.js), so telling a driver it will go out later would be a promise nothing
    // keeps — the packet is simply still here and the tap can be repeated.
    discardError.value = t("packet.discard_failed");
  } finally {
    discarding.value = false;
  }
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
  endedNow.value = null;
}

// AI-CONTEXT: THE METER WENT BACK TO FULL FREE TIME AND FROZE THERE (§23 entry 219).
//
// Reported as "the ticker starts correctly and converts to the paid ticker correctly,
// but when I add a BOL or other photos it goes back and freezes" — and reproduced in
// this component exactly: with `phase: "ended"` carrying detention_cents 7500, the tab
// rendered **2:00:00 · Free time** where the server had just said **$75.00**.
//
// `ended` is M3's third phase and this function handled two of them. It fell through to
// `return null`, the branch written for `not_arrived`, so `arrivalMs` went null — and
// `state` reads `arrivalMs ?? now`, which makes the trigger time equal to now on EVERY
// tick. Elapsed is therefore permanently zero: the free-time clock reads its full value
// and never moves. That is both halves of the report, "goes back" and "freezes", from
// one missing case. The same shape as N-06 on the server, one layer up: a null arrival
// silently defaulting to `now` and reporting the result as a measurement.
//
// A visit that has ENDED is not a visit that never started. The money is final and the
// server has already computed it, so the clock stops rather than restarting.
function deriveArrival(m) {
  const base = Date.now();
  if (m.phase === "within_free_time") {
    return base - (m.free_time_minutes * 60 - m.free_time_remaining_seconds) * 1000;
  }
  if (m.phase === "accruing" || m.phase === "ended") {
    return base - (m.free_time_minutes * 60 + m.detention_seconds) * 1000;
  }
  return null; // not arrived
}

async function loadMeter() {
  try {
    const m = await fetchMeter(activeStopId.value);
    live.value = m;
    arrivalMs.value = deriveArrival(m);
    // the instant the visit stopped counting. Everything derived from the clock reads
    // this instead of the live `now`, so an ended stop holds its final figure rather
    // than accruing forever off a truck that has left.
    endedNow.value = m.phase === "ended" ? Date.now() : null;
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
  if (!(events || []).some((e) => e.event_type === "EXIT")) return;
  loadPackets();
  // AI-CONTEXT: AND THE METER, WHICH THIS WATCHER USED TO LEAVE RUNNING (§23 entry 225).
  //
  // Owner-reported as two separate bugs and it is one: "the Load tab showed actual money
  // accrued waiting, but after I finish the load the Money tab shows nothing", and "check
  // and send appeared even though I had not left the stop yet".
  //
  // On EXIT this reloaded the PAPERWORK and nothing else. So the packet card arrived —
  // that is the "check and send" — while the Meter went on ticking locally from the
  // `arrivalMs` it had derived at the last fetch, adding money the server had already
  // stopped counting. The two halves of the screen were describing different stops, and
  // the driver believed the half that was climbing.
  //
  // The server settles it: on EXIT the visit is `ended`, with a final
  // `detention_seconds`/`detention_cents` that may well be ZERO because the dwell never
  // passed free time. Re-reading here is what lets the Meter freeze on the real figure
  // (entry 219) at the same instant the paperwork appears, instead of inventing money
  // that no claim will ever be worth.
  loadMeter();
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
// finding F5: five states, derived server-side from the F8 message row. `notice_sent`
// above stays the boolean the CTA ladder reads — a notice that FAILED has not been sent,
// so the rung must still offer it — while this is what the checklist row says out loud.
// AI-CONTEXT: the CTA was always OFFERED in the `failed` state — `notice_sent` is false
// there, so the ladder already reached the notice rung — but it read "Send notice", as if
// nothing had been tried. The driver has tapped it once and watched it fail; inviting them
// to do the thing they already did hides that this is a RETRY the server will honour with
// a fresh send (the wedge session's resend rule). `retrying` keeps the plain wording: the
// sweep owns that row and tapping does not produce a new message.
const noticeDelivery = computed(() => live.value?.notice_delivery ?? "not_sent");
// AI-CONTEXT: "the notice is on its way", which is NOT the same question as `notice_sent`.
//
// `notice_sent` means the broker was REACHED, and the CTA ladder reads it so that a
// failed notice still offers the rung. Sending is asynchronous now, so for up to a sweep
// interval after the tap a notice is genuinely in flight while `notice_sent` is still
// false — and without this the ladder would go on offering "Notify broker" over a row the
// server correctly refuses to duplicate. A control that runs and changes nothing is the
// dead-control pattern §23 entry 72 records.
//
// ONLY `queued`. `retrying` and `failed` keep the behaviour they were given: the rung
// stays, with `failed` wording it "Send again". Widening this to `retrying` would be a
// second, unrelated decision smuggled in beside an asynchrony change.
const noticeInFlight = computed(() => noticeDelivery.value === "queued");
// the address this load's notices go to, and the load to PATCH it on
const loadId = computed(() => live.value?.load_id ?? null);
const brokerEmail = computed(() => live.value?.counterparty_email ?? null);
// F7: the warning is once-only server-side (`pre_notice_sent_at`); this retires the rung
// as soon as it has gone rather than waiting for the next meter poll.
const preNoticeSent = ref(false);
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

// `endedNow` freezes the clock without freezing the TAB: `now` goes on ticking for the
// appointment countdown and everything else that legitimately moves.
const state = computed(() =>
  computeDetentionState(
    arrivalMs.value ?? now.value,
    freeMin.value,
    rateCents.value,
    endedNow.value ?? now.value,
  ),
);
const withinFree = computed(() => state.value.phase === "within_free_time");
const accruing = computed(() => !!live.value && !preArrival.value && !withinFree.value);
// AI-CONTEXT: finding F7 — the last half hour of free time, when warning the broker can
// still change the outcome. The same 30-minute boundary the server uses
// (`PRE_DETENTION_THRESHOLD`) and the same one the driver's own P1 is measured from, so
// the three cannot disagree about when the window opens.
const PRE_DETENTION_SECONDS = 30 * 60;
// floor, not ceil, and `max(1, ...)` — the same shape the server's own P1 uses
// (`dispatch_free_time_warning`). Rounding UP would tell a driver with 29:01 left that
// they have 30 minutes, which is the one direction this figure must never err in.
const freeMinutesLeft = computed(() =>
  Math.max(1, Math.floor(state.value.freeTimeRemainingSeconds / 60)),
);
const warningWindow = computed(
  () =>
    !!live.value &&
    !preArrival.value &&
    withinFree.value &&
    state.value.freeTimeRemainingSeconds <= PRE_DETENTION_SECONDS,
);
const noticeMsg = ref("");
const claimError = ref(""); // §15.4: a failed FILING is never silent

// a claim is filed once the SERVER says so (live.filed) — persists across tab
// switches/remounts — or optimistically the moment we file it (filed ref).
const isFiled = computed(() => !!(filed.value || live.value?.filed));
// the visit is over and no claim has been filed yet — the money is settled, the act is not
const isEnded = computed(() => !isFiled.value && live.value?.phase === "ended");
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
  if (isEnded.value) return t("load.detention");
  return withinFree.value ? t("load.free_time") : t("load.detention");
});
const meterFigure = computed(() => {
  if (!live.value) return "—";
  if (isFiled.value) return formatMoney(filedAmount.value);
  // the SERVER's final figure, not one re-derived here — it is the number the claim
  // will be filed for, and two arithmetics for one amount is how they disagree
  if (isEnded.value) return formatMoney(live.value?.detention_cents ?? 0);
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
  if (isEnded.value)
    return `${formatClock(live.value?.detention_seconds ?? 0)} · ${t("load.stop_ended")}`;
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
  // AI-CONTEXT: A FINISHED STOP LEADS WITH THE MONEY (§23 entry 227, owner screenshot).
  // The ladder put "Snap BOL" in the primary slot on a stop the same screen had just
  // declared over — telling a driver to photograph paperwork at a dock they have left,
  // above the one act that still pays. Capture stays reachable as a secondary rung; it
  // simply stops outranking filing once the visit is done.
  if (isEnded.value && claimable.value) return "claim";
  if (!bolCaptured.value) return "bol";
  if (accruing.value && !noticeSent.value && !noticeInFlight.value) return "notice";
  if (claimable.value) return "claim";
  // F7: inside the last half hour, warning the broker is the act that can still change
  // what happens. It ranks BELOW the accruing notice and the claim deliberately — once
  // money is owed, recording it outranks trying to prevent it — and above photos, which
  // can be taken at any point while the truck is parked.
  if (warningWindow.value && !preNoticeSent.value) return "warn";
  // AI-CONTEXT: §23 entry 127 — the ladder's missing middle. Arrived, BOL filed and
  // free time still running produced NO primary action at all, which is most of a
  // stop: the driver's remaining job was rendered only as body-sized checklist rows
  // while §10.2 promises a state-dependent single CTA. Cargo photos are the one task
  // that can only be done while the truck is parked at that dock, and they are what a
  // damage dispute rests on later.
  //
  // It sits BELOW notice and claim deliberately. Once the clock is accruing, money is
  // the more urgent act, and a photo taken then is still takeable from the row and the
  // More sheet — this rung fills the gap, it does not outrank the wedge.
  //
  // `photosRequired > 0` is load-bearing, not defensive: `photosDone` is false when
  // NOTHING is required, so without this the Primary would demand a photo set the
  // stop's own checklist never asked for — inventing a task and then grading the
  // driver against it. A stop that wants no photos leaves the rung empty and keeps
  // capture on the secondary row, which is where voluntary photographs belong.
  if (isOnSite.value && photosRequired.value > 0 && !photosDone.value) return "photos";
  return null; // arrived, BOL filed, off the geofence, and nothing owed yet
});

// AI-CONTEXT: the CTA ladder's rung had no busy state of any kind (owner request,
// 2026-08-11) — no spinner, no label change and, worse, NO GUARD.
//
// §8 has always said "Loading state = inline spinner replacing label, width locked" and
// nothing in this product implemented it. On these four the omission was not only
// feedback: a driver at a dock with two bars taps a button that looks exactly like an
// untapped button, so they tap it again — and `onSendNotice` genuinely sends a second
// notice to the broker. `rungBusy` names which rung is working, so one ref disables the
// Primary and its twin in the secondary row without four more booleans.
const rungBusy = ref("");
// AI-CONTEXT: pre-arrival, the evidence card COLLAPSES (owner request, §23 entry 138).
//
// Everything in that card is a record of things captured AT the dock, and before the
// driver reaches one there is nothing in it — four rows of "not yet" between the Meter
// and the single action the screen exists to offer, pushing "I have arrived" off a
// 360 dp screen. It collapses to one row rather than disappearing, because the broker
// email field lives inside it and fixing that address while still driving there is
// exactly when a driver can.
const evidenceOpen = ref(false);
const docsCaptured = computed(() => docChecklist.value.filter((r) => r.captured).length);
// the too-far question. `farDistance`/`farPlace` come from the server's 409, so the
// sheet states the real number rather than one the client guessed at.
const farOpen = ref(false);
const farDistance = ref(0);
const farPlace = ref("");
const arriveError = ref("");
// §12.5: units are NEVER localised (miles everywhere). Below a tenth of a mile the
// figure is useless to a driver, so it rounds to the nearest tenth and never to zero.
const farText = computed(() => {
  const miles = farDistance.value / 1609.344;
  return `${Math.max(0.1, Math.round(miles * 10) / 10)} mi`;
});
async function onArrive(confirmed = false) {
  if (!activeStopId.value || rungBusy.value) return;
  rungBusy.value = "arrive";
  arriveError.value = "";
  try {
    await arriveAtStop(activeStopId.value, { fix: lastFix.value, confirmed });
    farOpen.value = false;
    // the server writes a real geofence ENTER for this tap (api/load.py: arrive), so
    // the driver IS on site by F3's own reckoning. Saying so here rather than waiting
    // up to a minute for the next ping is what makes the dock actions appear at the
    // moment the driver says they are at the dock — the fallback path is exactly the
    // one whose background sensor never fired, so it is the last path that should
    // have to wait for one.
    observePresence(true);
    await loadMeter();
  } catch (e) {
    if (e instanceof ArrivalTooFar) {
      // NOTHING was recorded — the server is asking, not refusing. §12.4: state the
      // fact and let the driver answer it.
      farDistance.value = e.distanceM ?? 0;
      farPlace.value = e.facilityName || stopName.value;
      farOpen.value = true;
    } else {
      arriveError.value = t("load.arrive_failed");
      setTimeout(() => (arriveError.value = ""), 6000);
    }
  } finally {
    rungBusy.value = "";
  }
}
async function onGenerateClaim() {
  // `claimable` also gates the controls; this is the same rule at the point of action,
  // so a stale render or a double tap cannot file a claim worth nothing.
  if (!activeStopId.value || filed.value || !claimable.value || rungBusy.value) return;
  rungBusy.value = "claim";
  claimError.value = "";
  try {
    filed.value = await generateClaim(activeStopId.value); // arrive->accrue->FILE (freezes Meter)
    await loadMeter();
  } catch {
    // AI-CONTEXT: THIS CATCH WAS EMPTY, ON THE ONE ACTION THIS PRODUCT EXISTS FOR
    // (§23 entry 222). Filing is what turns a running clock into money a broker owes,
    // and a 500, a 403 or a dead dock left the driver with a button that went un-busy
    // and nothing else — no message, no queued item, no claim. §15.4: "failed
    // money-moving actions are always explicit and persistent until resolved."
    //
    // The comment that stood here said "offline / queued in a later F12 pass". There is
    // no such pass: `generateClaim` is a raw fetch, not a `queuedPost`, so nothing was
    // queued then and nothing is queued now — the sentence described a mechanism that
    // does not exist, which is why the silence looked deliberate. Same shape as N-07 on
    // the Money tab, and the same fix: say which failure it was.
    claimError.value = online.value ? t("load.claim_failed") : t("load.claim_offline");
  } finally {
    rungBusy.value = "";
  }
}
async function onSendNotice() {
  // the guard that matters most on this surface: a notice is a real email to a broker,
  // and a second tap on a slow connection sent a second one.
  if (!activeStopId.value || rungBusy.value) return;
  rungBusy.value = "notice";
  try {
    const res = await sendDetentionNotice(activeStopId.value); // M3 counterparty notice
    // finding F5: "sent" was `message !== null`, which an SMTP failure also satisfies —
    // so a driver whose notice bounced was told "Broker notified — detention on record."
    // The server now says which of the five things happened; anything that is not a
    // delivery says so in its own words rather than borrowing the too-early message.
    if (res && res.phase === "warning") preNoticeSent.value = true;
    if (res && res.sent) {
      noticeMsg.value = res.phase === "warning" ? t("load.warn_ok") : t("load.notice_ok");
    }
    else if (res && res.delivery && res.delivery !== "not_sent") {
      noticeMsg.value = t(`notice.delivery.${res.delivery}`);
    } else noticeMsg.value = t("load.notice_early");
    await loadMeter();
  } catch {
    // AI-CONTEXT: THIS SAID "Detention hasn't started yet — nothing to notify" FOR EVERY
    // FAILURE (§23 entry 222), which is not a worse message but a DIFFERENT FACT: the
    // driver concludes their clock is not running when what actually happened is that
    // the broker was never told. `onSendPacket` 500 lines up already distinguishes the
    // dead dock from the server refusal, and this is that same pattern applied to the
    // notice — the one message on this screen that a detention claim later rests on.
    noticeMsg.value = online.value ? t("load.notice_failed") : t("load.notice_offline");
  } finally {
    rungBusy.value = "";
  }
}

// AI-CONTEXT: leaving is a SECONDARY on the anchored zone, not the last row of a sheet
// (owner report, §23 entry 141). It was the fourth item inside "More for this stop" —
// two taps and the bottom of a list — while being the second-most-frequent thing a
// driver does on this screen after the ladder's own step.
//
// It gets a confirm because promoting it raises the cost of a mis-tap and the act is not
// reversible: departing ends the stop server-side, STOPS THE DETENTION CLOCK and drafts
// the packet. A clock stopped by accident is money, which is why Forbidden #6's ban on
// blocking modals for non-destructive actions does not reach this one.
const leaveOpen = ref(false);
async function endLoad() {
  if (rungBusy.value) return;
  leaveOpen.value = false;
  rungBusy.value = "end";
  history.value = []; // re-read on next open: this load just joined it
  const stopId = activeStopId.value;
  filed.value = null;
  preNoticeSent.value = false; // a new stop has its own warning to give
  if (!stopId) {
    setActiveStop(null);
    clearLoad();
    rungBusy.value = "";
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
  rungBusy.value = "";
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
      <!-- the reference is LABELLED. A bare "BRL-78426" under a headline is a code with
           no noun attached: a driver cannot tell their own load number from a tracking
           number the app invented. §12.5 forbids concatenated fragments, so it is one
           ICU message rather than a label glued to a value. -->
      <p v-if="packetReference" class="packet-card__ref">
        {{ t("packet.ref", { ref: packetReference }) }}
      </p>
      <p v-if="isDriving" class="packet-card__driving">{{ t("packet.ready_driving") }}</p>
      <template v-else>
        <!-- AI-CONTEXT: AN EMPTY PACK IS NOT WORTH SENDING (§23 entry 227, owner
             screenshot). The card led with "check and send" over a packet holding no BOL,
             no seal, no damage note and 0/4 photos — a claim with no evidence behind it,
             which is worse in front of a broker than sending nothing.
             STATED, NOT BLOCKED, and deliberately INSIDE this block rather than chained
             to the `v-if` above it: the first draft of this line joined that chain and
             took the whole send control away with it, which is a product deciding it
             knows better than the driver holding paper copies. Eighteen tests said so. -->
        <p v-if="!packetHasContents" class="packet-card__driving">
          {{ t("packet.nothing_captured") }}
        </p>
        <!-- §16: colour AND icon AND label. The missing case takes `marker` — the same
             token `.late` already uses for a fact that needs attention without being an
             alarm — because the driver did not cause it and can fix it in the sheet. -->
        <p
          class="packet-card__to"
          :class="{ 'packet-card__to--missing': !packetRecipient }"
        >
          <TriangleAlert
            v-if="!packetRecipient"
            :size="16"
            :stroke-width="2"
            aria-hidden="true"
          />
          {{ packetRecipient ? t("packet.goes_to", { email: packetRecipient }) : t("packet.needs_email") }}
        </p>
        <button class="cta packet-card__cta" type="button" @click="openReview">
          {{ t("packet.review") }}
        </button>
      </template>
    </section>

    <!-- the Meter at rest is §23 entry 52's own fix and it stays everywhere except the
         one state where it contradicts the card above it: "No load —" directly under
         "You left <dock>". Entry 52 was about never showing money the driver had not
         earned; a zero-looking figure under a just-left-the-dock headline is the same
         family of misread from the other side. It returns the moment the packet goes. -->
    <section v-if="!paperworkFirst" class="card meter-card">
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

    <!-- §15.3: one sentence of what this is, then one action to start. It explains the
         Meter, so it stands down with the Meter — a sentence about a card that is not
         on screen is the noise §10.2 keeps this tab clear of. -->
    <p v-if="!live && !isDriving && !paperworkFirst" class="hint">{{ t("load.empty_hint") }}</p>
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

      <!-- AI-CONTEXT: pre-arrival this card is ONE ROW (owner request, §23 entry 138).
           Everything inside it records what was captured AT the dock, and before the
           driver reaches one it is four lines of "not yet" sitting between the Meter and
           the only action the screen exists to offer — which pushed "I have arrived"
           off a 360 dp screen. Collapsed, not removed: the broker email field lives in
           here, and the drive there is exactly when a driver can fix that address.
           Once arrived it is always open, because then it is the driver's job list. -->
      <button
        v-if="live && preArrival && !evidenceOpen"
        class="collapsed"
        type="button"
        :aria-expanded="false"
        @click="evidenceOpen = true"
      >
        <span class="collapsed__label">{{ t("load.paperwork_for_stop") }}</span>
        <span class="collapsed__count">{{ docsCaptured }}/{{ docChecklist.length }}</span>
        <ChevronRight :size="18" :stroke-width="2" class="collapsed__go" aria-hidden="true" />
      </button>

      <section v-if="live && (!preArrival || evidenceOpen)" class="card">
        <!-- AI-CONTEXT: pre-arrival the header is the SAME control that opened it.
             `evidenceOpen` was one-way — a driver who tapped the collapsed row to check
             the broker address could not put it back, so the screen they were given a
             way out of quietly became the screen they were stuck on. It carries the
             collapsed row's own label and count so the object reads as one thing
             opening and closing rather than two rows that happen to swap.

             Only pre-arrival: once the truck is at the dock this card is the driver's
             job list and §10.2 wants it open. -->
        <button
          v-if="preArrival"
          class="card__toggle"
          type="button"
          :aria-expanded="true"
          @click="evidenceOpen = false"
        >
          <span class="card__togglelabel">{{ t("load.paperwork_for_stop") }}</span>
          <span class="collapsed__count">{{ docsCaptured }}/{{ docChecklist.length }}</span>
          <ChevronDown :size="18" :stroke-width="2" class="collapsed__go" aria-hidden="true" />
        </button>
        <h2 v-else class="card__title">{{ t("load.evidence") }}</h2>
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
              <ChevronRight :size="18" :stroke-width="2" class="checklist__go" aria-hidden="true" />
            </button>
          </li>
          <!-- AI-CONTEXT: this row was a plain <li> with no handler while every row
               above it was a button — so "Photos 0/4", the line that reads most like a
               job to do, was the one line on the card that did nothing when tapped.
               Reported by the owner as "tapping on photos not working"; there was
               nothing to break, because nothing was ever wired. The destination is the
               same one the More sheet and the on-site shortcut already use. -->
          <li class="checklist__item">
            <template v-if="photosDone">
              <Check :size="20" :stroke-width="2" class="ok" aria-hidden="true" />
              {{ t("load.photos") }}
              <span class="checklist__count">{{ photosCaptured }}/{{ photosRequired }}</span>
            </template>
            <button
              v-else
              class="checklist__snap"
              type="button"
              @click="router.push('/protection/condition')"
            >
              <Camera :size="20" :stroke-width="2" aria-hidden="true" />
              {{ t("load.photos") }}
              <span v-if="photosRequired" class="checklist__count">
                {{ photosCaptured }}/{{ photosRequired }}
              </span>
              <ChevronRight :size="18" :stroke-width="2" class="checklist__go" aria-hidden="true" />
            </button>
          </li>
          <li class="checklist__item">
            <Send :size="20" :stroke-width="2" :class="{ ok: noticeSent }" aria-hidden="true" />
            {{ t(`notice.delivery.${noticeDelivery}`) }}
          </li>
        </ul>
        <!-- where those notices go. Directly under the notice row because that is the row
             it explains — "Broker notified" and "No broker email" are one fact from two
             sides — but OUTSIDE the list: a checklist item is a piece of evidence the
             driver captured, and this is a property of the load. -->
        <BrokerEmailField
          class="checklist__email"
          :load-id="loadId"
          :email="brokerEmail"
          @saved="loadMeter"
        />
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

      <!-- AI-CONTEXT: §7.2's BOTTOM-ANCHORED ACTION ZONE, built for the first time
           (owner request, §23 entry 140).

           §7.2's screen anatomy has read "content (scroll region) -> bottom-anchored
           primary action (when present, 56 dp + 16 gutter) -> tab bar" since it was
           written, and §7.3 puts primary and frequent actions in the bottom third.
           NOTHING in this product implemented it: the only `position: fixed` in the
           codebase is BottomSheet, and every surface's CTA was simply the last thing in
           the scroll region. On the arrived Load tab — the densest screen here, a Meter
           plus a stop context plus a five-row checklist — that put "Snap BOL" and the
           row holding "Leave this stop" below the fold at a dock.

           `position: sticky` rather than `fixed`: the zone keeps its place in the flow,
           so it needs no knowledge of the tab bar's height or the 480 dp column, and on
           a short screen it simply sits where it always did. It is opaque and hairlined
           because a sticky element paints OVER the content it has not reached yet.

           Not rendered at speed at all — the whole block is inside `!isDriving`. -->
      <div v-if="live" class="actions">
        <p v-if="noticeMsg" class="notice-msg">{{ noticeMsg }}</p>
        <p v-if="arriveError" class="notice-msg">{{ arriveError }}</p>
        <p v-if="claimError" class="notice-msg">{{ claimError }}</p>
        <!-- §10.2: ONE state-dependent CTA. The ladder picks the rung; the rungs it
             passes over stay reachable below as secondary text controls. -->
        <button
          v-if="rung === 'arrive'"
          class="cta"
          type="button"
          :disabled="!!rungBusy"
          @click="onArrive()"
        >
          <Spinner v-if="rungBusy === 'arrive'" />
          {{ rungBusy === "arrive" ? t("busy.saving") : t("load.arrive") }}
        </button>
        <button v-else-if="rung === 'bol'" class="cta" type="button" @click="openCapture({ item: 'bol' })">
          {{ t("load.cta.bol") }}
        </button>
        <button
          v-else-if="rung === 'notice'"
          class="cta"
          type="button"
          :disabled="!!rungBusy"
          @click="onSendNotice"
        >
          <Spinner v-if="rungBusy === 'notice'" />
          {{ rungBusy === "notice"
            ? t("busy.sending")
            : noticeDelivery === "failed"
              ? t("load.cta.notice_again")
              : t("load.cta.notice") }}
        </button>
        <button
          v-else-if="rung === 'claim'"
          class="cta"
          type="button"
          :disabled="!!rungBusy"
          @click="onGenerateClaim"
        >
          <Spinner v-if="rungBusy === 'claim'" />
          {{ rungBusy === "claim" ? t("busy.filing") : t("load.cta.claim") }}
        </button>
        <button
          v-else-if="rung === 'warn'"
          class="cta"
          type="button"
          :disabled="!!rungBusy"
          @click="onSendNotice"
        >
          <Spinner v-if="rungBusy === 'notice'" />
          {{ rungBusy === "notice" ? t("busy.sending") : t("load.cta.warn", { minutes: freeMinutesLeft }) }}
        </button>
        <button
          v-else-if="rung === 'photos'"
          class="cta"
          type="button"
          @click="router.push('/protection/condition')"
        >
          {{ t("load.cta.photos") }}
          <!-- the denominator travels with the CTA for the same reason §10.2 puts it on
               the row: "photos" is a task with no end, "0/4" is a task with an end. -->
          <span v-if="photosRequired" class="cta__count">{{ photosCaptured }}/{{ photosRequired }}</span>
        </button>
  
          <!-- §8's Secondary, used for exactly what §8 describes: the other thing a
             driver might do here. Only once ARRIVED — there is no stop to leave before
             you reach one — and it names which act it is, because on a route this leaves
             a dock and on the last stop it ends the load (§12.2). -->
        <button
          v-if="live && !preArrival"
          class="cta cta--outline"
          type="button"
          :disabled="!!rungBusy"
          @click="leaveOpen = true"
        >
          <Spinner v-if="rungBusy === 'end'" />
          {{ rungBusy === "end" ? t("busy.working") : nextStop ? t("load.leave_stop") : t("load.end") }}
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
            v-if="accruing && !noticeSent && !noticeInFlight && !isFiled && rung !== 'notice'"
            class="rungs__item"
            type="button"
            :disabled="!!rungBusy"
            @click="onSendNotice"
          >
            <Spinner v-if="rungBusy === 'notice'" />
            {{ rungBusy === "notice" ? t("busy.sending") : t("load.cta.notice") }}
          </button>
          <button
            v-if="claimable && !isFiled && rung !== 'claim'"
            class="rungs__item"
            type="button"
            :disabled="!!rungBusy"
            @click="onGenerateClaim"
          >
            <Spinner v-if="rungBusy === 'claim'" />
            {{ rungBusy === "claim" ? t("busy.filing") : t("load.cta.claim") }}
          </button>
          <!-- AI-CONTEXT: §5's ON_SITE, narrowed to this tab by the owner (§23 entry 64).
               §5 asks for capture actions "one tap from anywhere via a persistent action
               chip"; an app-wide chip is a new component pattern AND navigation
               structure, both §22 never-improvise, so the decision was to deliver the
               benefit inside a surface that already exists. Cargo condition is two taps
               the rest of the time (More -> Capture) and one while the truck is parked
               at the dock, which is the only place those photographs can be taken. It
               stays in the More sheet as well: this is a shortcut, not a move. -->
          <!-- `rung !== 'photos'` for the same reason every other rung carries that
               guard: when the ladder has already promoted this action to the Primary,
               repeating it here gives one job two controls. -->
          <button
            v-if="isOnSite && rung !== 'photos'"
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
      </div>

      <!-- AI-CONTEXT: the too-far QUESTION (§23 entry 138). Not a gate.
           Detention frequently starts in a gate queue that is most of a kilometre from
           the dock a pin sits on, so a driver waiting in one is legitimately arriving —
           refusing would strand exactly the person this button exists for. The sheet
           states the distance, says plainly that a queue is normal, and records where
           they are either way. Withdrawn at speed like every other acting control. -->
      <BottomSheet
        :open="farOpen && !isDriving"
        :title="t('load.far_title')"
        @close="farOpen = false"
      >
        <p class="docs__empty">
          {{ t("load.far_body", { mi: farText, at: farPlace }) }}
        </p>
        <button class="cta" type="button" :disabled="!!rungBusy" @click="onArrive(true)">
          <Spinner v-if="rungBusy === 'arrive'" />
          {{ rungBusy === "arrive" ? t("busy.saving") : t("load.far_go") }}
        </button>
        <button class="cta cta--text" type="button" @click="farOpen = false">
          {{ t("load.far_back") }}
        </button>
      </BottomSheet>

      <!-- §10.2's empty state, in its two shapes. Same two destinations either way —
           this grades them, it does not remove one.

           PAPERWORK FIRST: both step down to the tertiary row the ladder already uses
           (§8 Tertiary: text, auto width, wrapping, 48 dp), so the packet card holds
           the screen's only Primary. Reusing `.rungs` rather than declaring a second
           row is the point — it is the same pattern doing the same job, and a new one
           would be a §22.2 invention where an existing rule already answers.

           OTHERWISE: exactly what shipped — "Add a load" as the one loud action (PRD
           §108: the parsed rate con is the primary way a load is created; the manual
           form is the fallback INSIDE that sheet), with history tertiary beneath it. -->
      <div v-if="paperworkFirst" class="rungs rungs--empty">
        <button class="rungs__item" type="button" @click="importing = true">
          {{ t("load.rc_add") }}
        </button>
        <button class="rungs__item" type="button" @click="openHistory">
          {{ t("load.history") }}
        </button>
      </div>
      <template v-else-if="!live">
        <button class="cta" type="button" @click="importing = true">
          {{ t("load.rc_add") }}
        </button>
        <!-- §23-approved: history lives on the Load tab, because a load is what this
             tab is about — tertiary, so §10.2's one empty-state action stays the loud
             thing. §10.2 is silent on history and navigation is a never-improvise
             category (§22), so the shape was the owner's decision rather than a
             reading. -->
        <button class="cta cta--text" type="button" @click="openHistory">
          {{ t("load.history") }}
        </button>
      </template>

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
        :title="confirmingDiscard ? t('packet.discard_title') : t('packet.review_title')"
        @close="reviewing = false"
      >
        <!-- AI-CONTEXT: the confirm STEP, inside this sheet rather than over it.
             §8 requires a destructive action to have "its own confirm sheet" AND caps
             sheets at "max 1 deep" — and the review sheet is already that one, so a
             second sheet on top would break the cap to satisfy the confirm. §22.1
             resolves it at the Component Rules step: the sheet's own body becomes the
             confirm, which is a confirm the driver cannot miss, at 1 deep, having
             already seen what they are declining. Keep it returns to the review. -->
        <div v-if="reviewPacket && confirmingDiscard" class="review">
          <p class="review__note">{{ t("packet.discard_body") }}</p>
          <p v-if="discardError" class="review__error" role="status">{{ discardError }}</p>
          <!-- §8: destructive is `flare` filled and says exactly what it does (§12.2) -->
          <button
            class="cta cta--destructive"
            type="button"
            :disabled="discarding"
            @click="onDiscardPacket"
          >
            <Spinner v-if="discarding" />
            {{ discarding ? t("busy.discarding") : t("packet.discard_confirm") }}
          </button>
          <button
            class="cta cta--text"
            type="button"
            :disabled="discarding"
            @click="confirmingDiscard = false"
          >
            {{ t("packet.discard_keep") }}
          </button>
        </div>

        <div v-else-if="reviewPacket" class="review">
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
            <Spinner v-if="sending" />
            {{ sending ? t("busy.sending") : reviewClaim ? t("packet.send_with_claim") : t("packet.send") }}
          </button>
          <!-- the review's SECOND exit (owner request). Tertiary, because declining is
               not the expected outcome of opening a review — but it is a real one, and
               until now the only way to clear a packet a driver did not want was to
               send it. -->
          <button
            class="cta cta--text"
            type="button"
            :disabled="sending"
            @click="confirmingDiscard = true"
          >
            {{ t("packet.discard") }}
          </button>
        </div>
      </BottomSheet>

      <!-- §8: the confirm for the one act on this screen that cannot be undone. The body
           says what actually happens — the clock stops and the paperwork is drafted —
           rather than asking "are you sure" about a consequence it declines to name. -->
      <BottomSheet
        :open="leaveOpen && !isDriving"
        :title="nextStop ? t('load.leave_title') : t('load.end_title')"
        @close="leaveOpen = false"
      >
        <p class="docs__empty">{{ t("load.leave_body") }}</p>
        <button class="cta cta--destructive" type="button" :disabled="!!rungBusy" @click="endLoad">
          <Spinner v-if="rungBusy === 'end'" />
          {{ rungBusy === "end" ? t("busy.working") : nextStop ? t("load.leave_stop") : t("load.end") }}
        </button>
        <button class="cta cta--text" type="button" @click="leaveOpen = false">
          {{ t("load.leave_back") }}
        </button>
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
            <!-- AI-CONTEXT: ONE tap, ONE destination (owner request, §23 entry 137).
                 This row used to do three different things depending on the load: a
                 one-stop load navigated, a multi-stop load EXPANDED in place, and
                 inside that expansion sat a per-stop list plus an "Export whole load"
                 control that downloaded a PDF the driver had never seen. Three
                 behaviours behind one row, and the loudest of them put a document on
                 the phone sight-unseen. Every row now opens the record screen, where
                 the stops, the photographs, the download and the send all live and
                 where the driver can read what they are about to send first. -->
            <button class="hist__main" type="button" @click="go(`/load/${h.load_id}/record`)">
              <span class="hist__name">
                {{ routeLabel(h) }}
              </span>
              <span class="hist__date">
                <!-- the load's own number, because a driver who runs the same lane
                     twice in a week gets rows identical in every other respect -->
                <template v-if="h.reference_number">{{ h.reference_number }} · </template
                >{{ h.created_at.slice(0, 10)
                }}<template v-if="h.stop_count > 1">
                  · {{ t("load.history_stops", { n: h.stop_count }) }}</template>
              </span>
              <!-- §23 entry 128: a row that DOES something ends in a chevron -->
              <ChevronRight :size="18" :stroke-width="2" class="hist__go" aria-hidden="true" />
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
          <!-- leaving used to live HERE, fourth in this list. It is a Secondary on the
               anchored zone now (§23 entry 141); repeating it would give one act two
               controls, and the one inside a sheet is the one a driver would not find. -->
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
          <Spinner v-if="apptSaving" />
          {{ apptSaving ? t("busy.saving") : t("load.appt_save") }}
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
/* where it goes, before the tap. `overflow-wrap: anywhere` because an AP address has
   no spaces to break at and Forbidden #5 rules out truncating it — at 360 dp under
   xx-XL (+40%) a long one has to wrap rather than push the card sideways. */
.packet-card__to {
  display: flex;
  align-items: center;
  gap: var(--s-1);
  margin: var(--s-2) 0 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
  overflow-wrap: anywhere;
}
/* `marker`, the same token `.late` uses: a fact that needs attention and is not an
   alarm. The icon carries it too — §16, colour is never the sole signal. */
.packet-card__to--missing {
  color: var(--marker-500);
}
.packet-card__to--missing svg {
  flex-shrink: 0;
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
.checklist__email {
  margin-top: var(--s-3);
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
/* the collapsed evidence card: the CARD's own shape and the checklist row's target
   height, so it reads as the same object shut rather than as a new kind of control. */
.collapsed {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 56px;
  margin-bottom: var(--s-3);
  padding: var(--s-3) var(--s-4);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  text-align: left;
}
/* the same row, inside the card it opened. It keeps the closed row's target height and
   figure treatment so collapsing and expanding read as one object, not two controls. */
.card__toggle {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 48px;
  margin: 0 0 var(--s-3);
  padding: 0;
  background: transparent;
  text-align: left;
}
.card__togglelabel {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--text-2);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.collapsed__label {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--text-1);
  font-size: var(--type-body-size);
}
/* a figure, so Mono and tabular like every other figure (T-2) */
.collapsed__count {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.collapsed__go {
  flex-shrink: 0;
  color: var(--text-3);
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
/* §23 entry 129: three accent controls of identical weight competed on this screen —
   "Correct the appointment", "View all evidence" and "More for this stop" all rendered
   in shield-500 at label size and weight 500, so nothing said which one a driver at a
   dock actually wants. Accent is reserved for the forward path; correcting an
   appointment is a rare repair, so it steps down to `--text-2` and keeps an underline
   (the affordance AuthSurface already uses) rather than becoming unreadable-as-a-
   control. Still 48 dp, still first in the tab order it always had. */
.context__fix {
  align-self: flex-start;
  min-height: 48px;
  padding: 0 var(--s-2);
  margin-left: calc(var(--s-2) * -1);
  background: transparent;
  color: var(--text-2);
  text-decoration: underline;
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
/* §23 entry 128: a row that DOES something ends in a chevron; a row that states a
   fact does not. The card mixed both kinds at identical weight — "Late 15:40" and
   "Photos 0/4" were the same size, colour and alignment — so the only way to find out
   which lines were controls was to tap them and see. The chevron is `--text-3`, the
   quietest text step: this has to be findable without competing with the status icon
   that carries the row's meaning. */
.checklist__go {
  margin-left: auto;
  flex-shrink: 0;
  color: var(--text-3);
}
/* when the row already ends in a figure, the figure keeps the auto margin and the
   chevron rides the flex gap behind it */
.checklist__count + .checklist__go {
  margin-left: 0;
}
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
/* §7.2's action zone. Sticky rather than fixed: it keeps its place in the flow, so it
   needs no knowledge of the tab bar or the 480 dp column, and on a screen with nothing
   to scroll it renders exactly where it always did.

   OPAQUE and hairlined on purpose — a sticky element paints over the content it has not
   scrolled to yet, so a transparent one would put the checklist through the button.

   The negative inline margin lets it span the surface's own gutter, which is what makes
   it read as a bar rather than as a card that happens to be last. */
.actions {
  position: sticky;
  /* NEGATIVE, and it is not a fudge: `.app-content` carries §7.2's 16 dp end-padding, and
     a sticky element aligns to the scrollport's PADDING box — so `bottom: 0` left a 16 dp
     strip of scrolled content visible beneath the bar. This pulls it flush to the tab bar
     and the zone's own bottom padding gives the button its gutter back. */
  bottom: calc(var(--s-4) * -1);
  z-index: 1;
  margin: var(--s-3) calc(var(--s-4) * -1) calc(var(--s-4) * -1);
  padding: var(--s-3) var(--s-4) var(--s-4);
  background: var(--ink-0);
  border-top: 1px solid var(--line-1);
}
/* inside the zone the ladder's own spacing already applies; this only stops the status
   line from sitting flush against the button that produced it. */
.actions .notice-msg {
  margin: 0 0 var(--s-2);
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
/* the CTA's own figure — Mono and tabular like every other figure in the product
   (T-2), and one type step quieter than the label it follows so the button still
   reads as one action rather than two things competing inside a box. */
.cta__count {
  margin-left: var(--s-2);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  opacity: 0.85;
}
.cta--outline {
  margin-top: var(--s-2);
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
}
/* §8: "Destructive = flare filled, requires its own confirm sheet." This IS the
   confirm, so it carries the fill — the same treatment DocsSurface's remove confirm
   already uses. Deliberately NOT named `cta--danger`: MoreSurface scopes that name to
   an OUTLINE logout button, and one class name meaning two opposite treatments in two
   scoped stylesheets is a trap for whoever reads them next. */
.cta--destructive {
  background: var(--flare-500);
  color: var(--ink-0);
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
/* the same row, under a card rather than under the Primary it usually follows, so it
   takes the card gap instead of the button gap. No second pattern, just the spacing
   step that belongs where it sits. */
.rungs--empty {
  margin-top: var(--s-3);
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
.hist__go {
  flex-shrink: 0;
  color: var(--text-3);
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
