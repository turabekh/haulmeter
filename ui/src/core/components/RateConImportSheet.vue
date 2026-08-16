<!-- AI-CONTEXT: §10.2's empty-state action — "Add a load" by rate-con photo.

     PRD §108 calls this the PRIMARY way a load is created, and it has never existed:
     F6 stored `rate_con`, F9 parsed documents, and F5 took parsed terms, but the only
     place the three were ever joined was the Foundation e2e test. This tab offered a
     four-field manual form in its place.

     THE CONFIRM STEP IS THE FEATURE. M4-FR4 specifies it, and the reason is that a
     machine read of a photographed contract is a proposal — the driver is the only
     one who can see both the paper and the screen. Every parsed value lands in an
     editable field rather than being written straight into a load.

     Two honesty rules, both §11.7 discipline:
     · The screen NAMES WHO IS SPEAKING. A parsed value is labelled as read from the
       rate con, never presented as simply true — the same rule as "Vendor says halal"
       and "prompted: seals".
     · A term the contract is SILENT on is stated as silence, not as a zero. "Silent
       on detention" is a fact about the paper worth learning before accepting a load,
       not after four hours at a dock — and a driver who saw "$0/h" would believe the
       contract said so.

     When the parse fails — the state this stack runs in with no model key — the
     document is still filed and the manual form takes over. Inventing plausible terms
     would put a number the contract never contained behind a detention claim. -->
<script setup>
import { ref, reactive, computed } from "vue";
import { Camera, TriangleAlert, Check } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import {
  importRateCon,
  createActiveLoad,
  geocodeAddress,
  fetchPreAcceptance,
  setOnTimeConsent,
} from "../api.js";
import {
  contactEmailError,
  contactPhoneError,
  normalizeContactEmail,
  normalizeContactPhone,
} from "../contact.js";
import { lastFix } from "../location.js";
import { formatMoney } from "../meter.js";
import Spinner from "./Spinner.vue";
import DwellIntel from "./DwellIntel.vue";

const emit = defineEmits(["created"]);
const { t } = useI18n();

const file = ref(null);
const preview = ref(null);
const busy = ref(false);
// null = nothing read yet; otherwise the server's draft
const draft = ref(null);
const documentId = ref(null);
const failed = ref(false);

// the confirm form. Every field is editable — a parse is a proposal.
// load-level terms only: the per-stop fields moved onto `stops` (§23 entry 68)
const form = reactive({
  broker: "",
  // AI-CONTEXT: where this load's detention notices go, collected at the one moment the
  // driver is holding the rate con — which is the only place the address is written down.
  // Optional by design: a driver who does not have the AP address must still be able to
  // file the load and run the clock, and the claim screen's `no_email` state is what
  // catches it later. An offer, not a gate.
  brokerEmail: "",
  // AI-CONTEXT: read off the same rate con as the address, and useful for the same
  // reason — it is the number a driver calls when the dock will not answer the buzzer,
  // and until now they read it off the photograph every time.
  brokerPhone: "",
  reference: "",
  // AI-CONTEXT: M5-FR1's on-time check-in, OFF by default (J1-B1).
  //
  // The capability shipped with M5 and no screen ever offered it — endpoints reachable by
  // nothing, the entry-122 shape. This is the offer, at the one moment the driver is
  // already looking at the broker's address.
  //
  // OFF by default and never a gate: telling a broker "we arrived on time" is a
  // professionalism play some drivers want and others will not, and defaulting it on
  // would send a counterparty a message on the driver's behalf that they never chose.
  // It is also the documented answer to the blacklisting fear — it is the same geofence
  // as the detention clock, pointed at the driver's own reputation instead.
  onTimeCheckIn: false,
  freeMin: "",
  rateHr: "",
  // AI-CONTEXT: what the load PAYS (§23 entry 84). `rate_cents` has been in the parse
  // schema and the prompt since this module was written, in `Load.rate_cents` since F5
  // was written, and it reached no field and no pixel: the confirm screen showed the
  // detention rate and never the linehaul. A driver signing off a contract read every
  // term except the money. Held in DOLLARS here because that is what the paper says.
  rate: "",
});
// AI-CONTEXT: M4-FR4 is "accessorial terms extraction from rate cons (F5/F9) WITH A
// DRIVER-CONFIRM STEP", and the confirm step was the half that did not exist. The terms
// were extracted, normalised to a map, returned in the draft and rendered nowhere — so
// the screen warned about what the contract was SILENT on while never showing what it
// actually said. These are read-only: unlike a rate, a driver cannot correct contract
// wording by typing over it, and a screen that let them would be inviting a claim to be
// argued from language the contract does not contain.
const terms = ref({});
// AI-CONTEXT: WHERE the dock is, which this sheet used to invent (§23 entry 67).
//
// `receiver_address` was parsed and dropped, and every load was created at a
// hardcoded Dallas lat/lon — so a Columbus receiver armed its geofence 1,500 km from
// the dock and ENTER could never fire. No arrival, no on-time proof, no detention
// clock, no ON_SITE, for every load made the way PRD §108 calls primary.
//
// The geocoder proposes and the driver confirms: `placeLabel` is the geocoder's OWN
// wording for what it matched, shown rather than assumed (§11.7). With no coordinate
// from either the address or the driver's own position, the load cannot be filed —
// saying so is honest, and a fabricated coordinate is what this replaces.
// AI-CONTEXT: a rate con is a ROUTE, and this sheet described one dock (§23 entry 68).
// A real contract's stops table carried a pickup in Dallas on 08/03 (08:00-10:00) and
// a delivery in Columbus on 08/05; the parse kept the second and dropped the first, so
// detention at the SHIPPER could never be claimed and §10.2's next-stop preview had
// nothing to preview. Each stop now carries its own name, address, window, geocode and
// facility match — a route is two different docks, and sharing either between them
// would be the pre-ticking defect (entry 65) wearing a different hat.
const stops = ref([]);

function blankStop(type = "delivery") {
  return {
    stopType: type,
    name: "",
    address: "",
    apptStart: "",
    apptEnd: "",
    parsedStart: null,
    candidates: [],
    chosen: null,
    place: null,
    placing: false,
    placeMissed: false,
    // what this dock has done to other drivers. Fetched when the driver PICKS a known
    // facility, because there is nothing to know about a dock that is not one yet.
    intel: null,
  };
}
// AI-CONTEXT: "none of these" needs a value of its OWN (§23 entry 65).
//
// `chosenFacility` starts at null to mean "not answered", and the none-of-these radio
// carried `:value="null"` — so `v-model` matched it and Vue rendered that option
// CHECKED on arrival. The comment two lines down said nothing was pre-selected and the
// screen pre-selected something, which is the worst combination of the two.
//
// And it pre-selected the harmful one: none-of-these is what tells the API not to
// reuse a dock, and a duplicated dock splits that facility's dwell history in two —
// the exact defect entry 47 was written to fix.
const NO_MATCH = "__none";

const readable = computed(() => !!draft.value?.readable);

// AI-CONTEXT: the app stating its OWN READING of the money terms, in the driver's
// language (J1-A2).
//
// The confirm step is a comparison against a piece of paper, and until now the only way
// to make it was to decode three separate input boxes labelled in trucking English. A
// driver whose locale is `uz` could confirm a contract they could not read.
//
// These are composed from the parsed slots — the app saying what it understood — and
// they are NOT the paper's words. The paper's words stay verbatim and English further
// down, under a heading that says so, because a translated clause cannot be compared
// against the original and a claim is argued from the original (§11.7, §12.3).
//
// Each figure carries its own absence. A term the parse did not find renders "the rate
// con does not say" in the driver's language rather than a fabricated line or a silent
// zero — and NEVER an English fallback, which is the Q-9 principle: a driver who meets
// English here cannot tell "we found nothing" from "we did not translate this".
const reading = computed(() => [
  {
    key: "pays",
    label: "load.terms.pays",
    value: form.rate ? formatMoney(Math.round(Number(form.rate) * 100)) : null,
    unit: null,
  },
  {
    key: "detention",
    label: "load.terms.detention",
    value: form.rateHr ? formatMoney(Math.round(Number(form.rateHr) * 100)) : null,
    unit: "load.terms.per_hour",
  },
  {
    key: "free",
    label: "load.terms.free",
    value: form.freeMin !== "" && form.freeMin != null ? String(form.freeMin) : null,
    unit: "load.terms.minutes",
  },
]);

const silentOn = computed(() => draft.value?.silent_on ?? []);

function onFile(event) {
  const f = event.target.files?.[0];
  if (!f) return;
  file.value = f;
  preview.value = URL.createObjectURL(f);
}

async function read() {
  if (!file.value || busy.value) return;
  busy.value = true;
  try {
    // the File goes straight over as bytes; the base64 read that used to happen on the
    // main thread here is gone
    const res = await importRateCon({
      file: file.value,
      filename: file.value.name,
      contentType: file.value.type,
    });
    draft.value = res;
    documentId.value = res.document_id;
    const p = res.parsed ?? {};
    form.broker = p.broker_name ?? "";
    form.reference = p.reference_number ?? "";
    // AI-CONTEXT: the contact the paper prints, PREFILLED — never sent (J1-A1).
    //
    // It arrives already held to the server's own address rule, so what lands here is
    // either an address or nothing; a footer that ran off the edge of the photograph
    // comes back absent rather than as `dispatch@`. The field stays editable and the
    // driver still confirms, which is the whole posture: a parse is a claim about the
    // paper, and only the person holding both it and the phone can make it a recipient.
    form.brokerEmail = res.contact?.email ?? "";
    form.brokerPhone = res.contact?.phone ?? "";
    // <input type="datetime-local"> wants "YYYY-MM-DDTHH:mm" with no zone
    stops.value = (res.stops ?? []).map((row) => ({
      ...blankStop(row.stop_type || "delivery"),
      name: row.name ?? "",
      address: row.address ?? "",
      apptStart: row.appointment_start ? String(row.appointment_start).slice(0, 16) : "",
      apptEnd: row.appointment_end ? String(row.appointment_end).slice(0, 16) : "",
      parsedStart: row.appointment_start ?? null,
      candidates: row.facility_candidates ?? [],
      place: row.location ?? null,
      placeMissed: !!(row.address && !row.location),
    }));
    // an unreadable rate con still needs somewhere to type one stop into
    if (!stops.value.length) stops.value = [blankStop()];
    form.freeMin = p.free_time_minutes ?? "";
    form.rateHr = p.detention_rate_cents_per_hour
      ? Math.round(p.detention_rate_cents_per_hour / 100)
      : "";
    form.rate = p.rate_cents ? (p.rate_cents / 100).toFixed(2) : "";
    terms.value = p.accessorial_terms ?? {};
    // NOTHING is pre-selected, and that is measured rather than cautious: pg_trgm
    // scores an unrelated "Dallas Distribution Center" at 0.645 against "ACME
    // Distribution Center" and the correct "ACME Distribution Ctr" at 0.679, so no
    // threshold tells them apart. A wrong match costs one tap to notice; a wrong
    // default costs a load attached to a dock the driver never visited.
  } catch {
    // the document may or may not have been filed; either way the driver types it
    failed.value = true;
    draft.value = { readable: false };
    stops.value = [blankStop()];
  } finally {
    busy.value = false;
  }
}

// AI-CONTEXT: fetched on the CHOICE, not on the read (J1-A3).
//
// A rate con's candidate list is offered and never pre-selected (§23 entry 65), so
// until the driver picks one there is no facility to ask about — and asking about all
// three would put two docks' histories on screen beside the one they chose. Failure is
// silence: this is an extra fact about the dock, and a driver who cannot see it must
// still be able to file the load.
async function loadIntel(stop) {
  stop.intel = null;
  if (!stop.chosen || stop.chosen === NO_MATCH) return;
  try {
    stop.intel = await fetchPreAcceptance(stop.chosen, Number(form.freeMin) || 0);
  } catch {
    stop.intel = null;
  }
}

async function findPlace(stop) {
  if (!stop.address.trim() || stop.placing) return;
  stop.placing = true;
  stop.placeMissed = false;
  try {
    const res = await geocodeAddress(stop.address);
    stop.place = res.places?.[0] ?? null;
    stop.placeMissed = !stop.place;
  } catch {
    stop.placeMissed = true; // offline or the geocoder is down — say so, guess nothing
  } finally {
    stop.placing = false;
  }
}

// the driver is standing at the dock and the geocoder cannot place it: their own
// position is a true statement about somewhere, which a Dallas constant never was
function usePosition(stop) {
  if (!lastFix.value) return;
  stop.place = { lat: lastFix.value.lat, lon: lastFix.value.lon, label: t("load.rc_here") };
  stop.placeMissed = false;
}

// every stop has to be somewhere: the geofence is armed on it, so a stop we cannot
// place is a stop whose arrival can never be detected
const routeReady = computed(() => stops.value.length > 0 && stops.value.every((s) => s.place));
// the same rule the server applies, so a typo is caught while the driver is still looking
// at the paper rather than as a 422 three taps later
const brokerEmailError = computed(() => contactEmailError(form.brokerEmail));
const brokerPhoneError = computed(() => contactPhoneError(form.brokerPhone));
// no recipient, no offer — a question whose answer cannot be acted on is not a question
const canOfferCheckIn = computed(
  () => !!normalizeContactEmail(form.brokerEmail) && !brokerEmailError.value,
);

function stopSource(stop) {
  return stop.parsedStart && stop.apptStart === String(stop.parsedStart).slice(0, 16)
    ? "rate_con_parse"
    : "manual";
}

async function create() {
  busy.value = true;
  try {
    const created = await createActiveLoad({
      facility_name: stops.value[0].name || "Receiver",
      lat: stops.value[0].place.lat,
      lon: stops.value[0].place.lon,
      // the address the driver confirmed, kept rather than discarded once geocoded
      address: stops.value[0].address || null,
      counterparty: form.broker || "Broker",
      counterparty_email: normalizeContactEmail(form.brokerEmail),
      counterparty_phone: normalizeContactPhone(form.brokerPhone),
      reference_number: form.reference || null,
      free_time_minutes: Number(form.freeMin) || null,
      rate_cents_per_hour: form.rateHr ? Math.round(Number(form.rateHr) * 100) : null,
      // the two that were parsed and dropped (§23 entry 84)
      rate_cents: form.rate ? Math.round(Number(form.rate) * 100) : null,
      accessorial_terms: terms.value,
      rate_con_document_id: documentId.value,
      // the whole route, in the order the driver runs it
      stops: stops.value.map((stop) => ({
        facility_name: stop.name || "Receiver",
        lat: stop.place.lat,
        lon: stop.place.lon,
        address: stop.address || null,
        stop_type: stop.stopType,
        appointment: stop.apptStart ? new Date(stop.apptStart).toISOString() : null,
        appointment_end: stop.apptEnd ? new Date(stop.apptEnd).toISOString() : null,
        appointment_source: stop.apptStart ? stopSource(stop) : null,
        facility_id: stop.chosen === NO_MATCH ? null : stop.chosen,
        create_new_facility: stop.chosen === NO_MATCH,
      })),
    });
    // AI-CONTEXT: recorded AFTER the load exists, because consent is stored per load —
    // and it must never be able to cost the driver the load. A failed consent write
    // leaves a filed load with the check-in off, which is the honest degradation: the
    // proof artifact is filed on arrival either way, so what is lost is the notice to
    // the broker, not the evidence.
    if (form.onTimeCheckIn && created?.load_id) {
      await setOnTimeConsent({
        loadId: created.load_id,
        enabled: true,
        counterpartyEmail: normalizeContactEmail(form.brokerEmail),
      }).catch(() => {});
    }
    emit("created");
  } catch {
    /* leave the form as typed — losing a confirmed rate con to a failed request
       would make the driver photograph it again */
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="rc">
    <!-- step 1: the photo -->
    <template v-if="!draft">
      <p class="rc__lead">{{ t("load.rc_lead") }}</p>
      <label class="rc__field">
        <span class="rc__label">{{ t("load.rc_photo") }}</span>
        <input class="rc__input" type="file" accept="image/*,application/pdf" @change="onFile" />
      </label>
      <img v-if="preview" :src="preview" class="rc__preview" :alt="t('load.rc_photo')" />
      <button class="rc__cta" type="button" :disabled="!file || busy" @click="read">
        <Spinner v-if="busy" />
        <Camera v-else :size="18" :stroke-width="2" aria-hidden="true" />
        {{ busy ? t("load.rc_reading") : t("load.rc_read") }}
      </button>
    </template>

    <!-- step 2: confirm. Parsed or typed, the driver signs off before anything exists -->
    <template v-else>
      <p v-if="readable" class="rc__from">
        <Check :size="16" :stroke-width="2" aria-hidden="true" />
        {{ t("load.rc_from") }}
      </p>
      <p v-else class="rc__unread">
        <TriangleAlert :size="16" :stroke-width="2" aria-hidden="true" />
        {{ t("load.rc_unreadable") }}
      </p>

      <!-- AI-CONTEXT: what the app UNDERSTOOD, in the driver's language (J1-A2).
           Composed from the parsed slots, not translated from the paper — the paper's
           own words are further down under a heading that says so. Label and figure are
           separate elements because the pseudo-locale generator cannot inflate
           `{placeholders}` and a two-placeholder sentence never clears +40% (entry 138). -->
      <section v-if="readable" class="rc__reading">
        <h3 class="rc__label">{{ t("load.terms.title") }}</h3>
        <p v-for="row in reading" :key="row.key" class="rc__readline">
          <span class="rc__readlabel">{{ t(row.label) }}</span>
          <template v-if="row.value">
            <span class="rc__readfigure mono">{{ row.value }}</span>
            <span v-if="row.unit" class="rc__readunit">{{ t(row.unit) }}</span>
          </template>
          <span v-else class="rc__readabsent">{{ t("load.terms.absent") }}</span>
        </p>
      </section>

      <!-- a term the contract does not state, said as silence rather than as a zero -->
      <p v-if="silentOn.length" class="rc__silent">
        <TriangleAlert :size="16" :stroke-width="2" aria-hidden="true" />
        {{ t("load.rc_silent") }}
        <span class="rc__terms">{{ silentOn.map((s) => t(`load.rc_term.${s}`)).join(" · ") }}</span>
      </p>

      <!-- AI-CONTEXT: the ROUTE, one block per stop (§23 entry 68). Each carries its
           own name, address, window and facility match, because a pickup and a
           delivery are two different docks — and detention accrues at both. -->
      <section v-for="(stop, i) in stops" :key="i" class="rc__stop">
        <p class="rc__stophead">
          <span class="rc__stopkind">{{ t(`load.stop.${stop.stopType}`) }}</span>
          <span class="rc__stopn">{{ i + 1 }} / {{ stops.length }}</span>
        </p>

        <label class="rc__field">
          <span class="rc__label">{{ t("load.facility") }}</span>
          <input v-model="stop.name" class="rc__input" type="text" />
        </label>

        <!-- offered, never assumed: a wrong match is one tap to undo, a duplicate dock
             quietly splits that facility's dwell history in two -->
        <div v-if="stop.candidates.length" class="rc__match">
          <span class="rc__label">{{ t("load.rc_matched") }}</span>
          <label v-for="c in stop.candidates" :key="c.facility_id" class="rc__opt">
            <input
              v-model="stop.chosen"
              type="radio"
              :value="c.facility_id"
              @change="loadIntel(stop)"
            />
            <span class="rc__optname">
              {{ c.name }}
              <!-- two facilities may legitimately carry the same name, and this list
                   rendered them identically — an unanswerable question (§23 entry 76) -->
              <small v-if="c.locality" class="rc__where">{{ c.locality }}</small>
            </span>
          </label>
          <label class="rc__opt">
            <input
              v-model="stop.chosen"
              type="radio"
              :value="NO_MATCH"
              @change="loadIntel(stop)"
            />
            <span>{{ t("load.rc_no_match") }}</span>
          </label>
          <!-- AI-CONTEXT: what this dock has done to other drivers, at the moment this
               driver decides (J1-A3, M8-FR6 + M8-FR2). Rendered by the SHARED component
               so this surface and the facility page cannot answer the same question in
               two formats (§23 R3) — that divergence is exactly what B3 removed. -->
          <DwellIntel :intel="stop.intel" />
        </div>

        <label class="rc__field">
          <span class="rc__label">{{ t("load.rc_address") }}</span>
          <input v-model="stop.address" class="rc__input" type="text" @change="findPlace(stop)" />
        </label>
        <div class="rc__place">
          <p v-if="stop.place" class="rc__placed">
            <Check :size="16" :stroke-width="2.5" aria-hidden="true" />
            <span>{{ t("load.rc_placed") }} <span class="rc__placelabel">{{ stop.place.label }}</span></span>
          </p>
          <p v-else-if="stop.placeMissed" class="rc__unplaced">{{ t("load.rc_unplaced") }}</p>
          <p v-else class="rc__unplaced">{{ t("load.rc_place_needed") }}</p>
          <div class="rc__placeacts">
            <button class="rc__mini" type="button" :disabled="!stop.address || stop.placing" @click="findPlace(stop)">
              <Spinner v-if="stop.placing" />
              {{ stop.placing ? t("load.rc_placing") : t("load.rc_find") }}
            </button>
            <button v-if="lastFix" class="rc__mini" type="button" @click="usePosition(stop)">
              {{ t("load.rc_use_here") }}
            </button>
          </div>
        </div>

        <label class="rc__field">
          <span class="rc__label">{{ t("load.appointment") }}</span>
          <input v-model="stop.apptStart" class="rc__input" type="datetime-local" />
        </label>
        <!-- a window is two times; the pickup row read "08:00 - 10:00" and collapsing
             that to one loses the half a driver is judged on -->
        <label v-if="stop.apptEnd || stop.apptStart" class="rc__field">
          <span class="rc__label">{{ t("load.rc_appt_end") }}</span>
          <input v-model="stop.apptEnd" class="rc__input" type="datetime-local" />
        </label>
      </section>

      <label class="rc__field">
        <span class="rc__label">{{ t("load.broker") }}</span>
        <input v-model="form.broker" class="rc__input" type="text" />
      </label>
      <!-- labelled for its PURPOSE, not its type: "Email" on a load form could be
           anyone's, and the one thing a driver needs to know is that this is the address
           a detention notice is sent to. -->
      <label class="rc__field">
        <span class="rc__label">{{ t("load.broker_email") }}</span>
        <input
          v-model="form.brokerEmail"
          class="rc__input"
          type="email"
          inputmode="email"
          autocomplete="off"
          autocapitalize="none"
          spellcheck="false"
        />
        <span v-if="brokerEmailError" class="rc__error" role="alert">
          {{ t(brokerEmailError) }}
        </span>
      </label>
      <!-- labelled for its purpose for the same reason the address above is: this is the
           number to call about THIS load, not a contact record. -->
      <label class="rc__field">
        <span class="rc__label">{{ t("load.broker_phone") }}</span>
        <input
          v-model="form.brokerPhone"
          class="rc__input"
          type="tel"
          inputmode="tel"
          autocomplete="off"
        />
        <span v-if="brokerPhoneError" class="rc__error" role="alert">
          {{ t(brokerPhoneError) }}
        </span>
      </label>
      <!-- AI-CONTEXT: M5-FR1's on-time check-in (J1-B1), offered where the driver is
           already looking at the broker's address.
           Rendered ONLY when there is an address to send to: "Send arrival check-in to
           {broker}?" over an empty recipient is a question with no answer, and a toggle
           that silently does nothing is worse than no toggle. Off by default — this
           sends a counterparty a message on the driver's behalf, and §21.8's rule about
           not helping ourselves to a driver's labour applies to their reputation too. -->
      <label v-if="canOfferCheckIn" class="rc__check">
        <input v-model="form.onTimeCheckIn" type="checkbox" />
        <span>{{ t("load.on_time_offer", { broker: form.broker || t("load.broker") }) }}</span>
      </label>
      <!-- the money the load pays. Editable like every other parsed value, because a
           parse is a proposal and the driver is the one holding the paper. -->
      <label class="rc__field">
        <span class="rc__label">{{ t("load.rc_rate") }}</span>
        <input v-model="form.rate" class="rc__input" type="number" inputmode="decimal" />
      </label>
      <label class="rc__field">
        <span class="rc__label">{{ t("calc.free_min") }}</span>
        <input v-model="form.freeMin" class="rc__input" type="number" inputmode="numeric" />
      </label>
      <label class="rc__field">
        <span class="rc__label">{{ t("calc.rate_hr") }}</span>
        <input v-model="form.rateHr" class="rc__input" type="number" inputmode="decimal" />
      </label>

      <!-- AI-CONTEXT: M4-FR4's driver-confirm step for the accessorial terms, which had
           never existed. The screen has warned about what the contract is SILENT on
           since the sheet shipped and never showed what it SAYS — so a driver was asked
           to accept a load on the strength of terms they could not read. Quoted
           verbatim and not editable: contract wording is the thing a claim is argued
           from, and a field that let a driver retype it would invite an argument from
           language the paper does not contain. -->
      <section v-if="Object.keys(terms).length" class="rc__terms-block">
        <!-- AI-CONTEXT: BESIDE the reading above, never behind a tap (J1-A2).
             Collapsing this was tried and reverted: M4-FR4's terms block exists because
             "a driver was asked to accept a load on the strength of terms they could not
             read", and putting the wording one tap away reverses that recorded decision
             rather than implementing this one. The kickoff allows behind OR beside; the
             existing decision settles which. The reading above leads by ORDER instead.
             (Caught by the test that asserts the clause text is on screen — it went red
             the moment the wording moved behind a button.) -->
        <h3 class="rc__label">{{ t("load.rc_states") }}</h3>
        <!-- WHY this block is English wherever you are: a claim is argued from the
             contract's own words, and a translated clause cannot be compared against the
             paper in the driver's hand (§12.3). Said out loud rather than left to look
             like a translation somebody forgot. -->
        <p class="rc__original-note">{{ t("load.rc_original_note") }}</p>
        <dl class="rc__termlist">
          <div v-for="(wording, term) in terms" :key="term" class="rc__term">
            <dt class="rc__termname">{{ t(`load.rc_term.${term}`) === `load.rc_term.${term}` ? term : t(`load.rc_term.${term}`) }}</dt>
            <dd class="rc__termtext" lang="en">{{ wording }}</dd>
          </div>
        </dl>
      </section>

      <button
        class="rc__cta"
        type="button"
        :disabled="busy || !routeReady || !!brokerEmailError"
        @click="create"
      >
        <Spinner v-if="busy" />
        {{ busy ? t("busy.working") : t("load.create") }}
      </button>
      <p class="rc__hint">{{ t("load.rc_confirm_hint") }}</p>
    </template>
  </div>
</template>

<style scoped>
.rc {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.rc__lead {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.rc__label {
  display: block;
  margin-bottom: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.rc__check {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 48px;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.rc__field {
  display: block;
}
.rc__input {
  width: 100%;
  min-height: 56px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.rc__preview {
  display: block;
  width: 100%;
  max-height: 240px;
  object-fit: contain;
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
}
.rc__cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 56px;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.rc__cta:disabled {
  opacity: 0.5;
}
.rc__from {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0;
  color: var(--ledger-500);
  font-size: var(--type-caption-size);
}
/* marker, not flare: an unreadable rate con costs the driver typing, not money */
.rc__unread,
.rc__silent {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: 0;
  padding: var(--s-3);
  border: 1px solid var(--marker-500);
  border-radius: var(--r-control);
  color: var(--marker-500);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.rc__terms {
  font-weight: 500;
}
/* the contract's own words, quoted. Hairline card like the stop blocks above it — no
   new pattern, and deliberately not `marker`: this is what the paper DOES say, which is
   reassurance, while the silence warning above it is the caution. */
.rc__reading {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.rc__readline {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-1) var(--s-2);
  margin: 0;
}
.rc__readlabel {
  color: var(--text-2);
}
.rc__readfigure {
  color: var(--text-1);
}
.rc__readunit {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.rc__readabsent {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.rc__original-note {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.rc__terms-block {
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.rc__termlist {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.rc__term {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.rc__termname {
  color: var(--text-2);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  font-weight: 500;
}
.rc__termtext {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.rc__match {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.rc__stop {
  display: flex;
  flex-direction: column;
  padding: var(--s-3);
  margin-bottom: var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.rc__stophead {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin: 0 0 var(--s-3);
}
.rc__stopkind {
  font-size: var(--type-label-size);
  font-weight: 600;
  color: var(--text-1);
}
.rc__stopn {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.rc__place {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-bottom: var(--s-4);
}
.rc__placed,
.rc__unplaced {
  display: flex;
  align-items: flex-start;
  gap: var(--s-2);
  margin: 0;
  font-size: var(--type-caption-size);
  line-height: var(--type-caption-line);
  color: var(--text-3);
}
.rc__placed { color: var(--ledger-500); }
.rc__placelabel { color: var(--text-2); }
.rc__unplaced { color: var(--marker-500); }
/* the same warning colour this card already uses for an unplaced stop — composed, not
   invented (design-prd §22.2 never-improvise) */
.rc__error {
  display: block;
  margin-top: var(--s-2);
  color: var(--marker-500);
  font-size: var(--type-label-size);
}
.rc__placeacts { display: flex; flex-wrap: wrap; gap: var(--s-3); }
.rc__mini {
  min-height: 48px;
  padding: 0 var(--s-2);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.rc__mini:disabled { color: var(--text-3); }
.rc__opt {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 48px;
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.rc__optname {
  display: flex;
  flex-direction: column;
}
.rc__where {
  color: var(--text-2);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
}
.rc__hint {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
</style>
