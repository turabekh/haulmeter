<!-- AI-CONTEXT: True-profit load calculator (M8-FR1, PRD §8.8). A full-screen
     LINEAR form (NAV-3 / §202: one input per line, 56 dp, numeric keypad,
     labels above fields). The driver enters the load; the result is the TRUE
     profit — rate minus route fuel (M7 net price), tolls, and the expected
     detention this receiver costs (M8 values each historical stop with the M3
     clock, then averages). The headline is a Meter-treatment figure (Mono,
     ledger-green when it clears, flare when it doesn't), with rate-per-mile
     AFTER dwell and a transparent breakdown + basis (§11.7, never fake
     precision). Live via api.js; offline it degrades honestly (fuel + dwell
     need a session, and it says so). -->
<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import { ArrowLeft } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { formatMoney } from "../core/meter.js";
import { calcTrueProfit, activeStopId, fetchMeter, searchFacilities } from "../core/api.js";
import { lastFix } from "../core/location.js";
import Spinner from "../core/components/Spinner.vue";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const { isDriving } = useDriverState();

const form = reactive({
  revenue: 2000, // dollars
  miles: 500,
  tolls: 30, // dollars
  freeMin: 120,
  rateHr: 75, // dollars/hr
});
const result = ref(null);
const submitting = ref(false);

// AI-CONTEXT: the load this calculator was opened FROM (§23 entry 85).
//
// It is reached from the Load tab's More sheet as a bare `/load/calc` — no query
// params — while reading `route.query.receiver`, `.lat` and `.lon` and falling back to
// the NIL UUID and a hardcoded Dallas. Those three parameters have never been supplied
// by anything, so every true-profit figure computed in production valued detention at a
// facility that does not exist and routed fuel from a city the driver was not in.
//
// The load knows its own Rate, its free time, its detention rate and its receiver.
// Asking a driver to retype the first while defaulting the fourth to nothing is the
// same shape as the rate con parsed into fields nobody read.
const prefilled = ref(false);
const loadFacility = ref(null);

/* AI-CONTEXT: the receiver, NAMED, because pre-acceptance is what this screen is for
 * (§23 entry 154).
 *
 * Entry 85 fixed the case where a load is already accepted — the active stop supplies the
 * facility. The case it could not fix is the one the calculator exists for: deciding
 * whether to TAKE a load, where there is no active stop and `route.query.receiver` has
 * never been set by anything. That fell through to the nil UUID, and the nil UUID has no
 * dwell samples, so `expected_detention_cost` returns `(0, 0)`.
 *
 * MEASURED against the live API with the nil receiver: `expected_detention_cents: 0`,
 * `detention_sample_size: 0`, `net_cents: 164167`. **A confident −$0.00 for detention,
 * folded into the headline**, on the screen a driver uses to accept or refuse — inside the
 * app whose entire thesis is that detention is what costs them. The sample size was on
 * screen, in caption grey, three lines below the figure it qualified.
 *
 * So the driver can name the dock. `/public/facilities` is the name search (the driver-
 * facing `/facility/search` is a semantic search over REVIEW text, which is a different
 * question). Unauthenticated is correct here and not a shortcut: it returns id, name and
 * type only, which is exactly what a picker needs.
 */
const receiverQuery = ref("");
const receiverResults = ref([]);
const receiver = ref(null); // { id, name } once chosen
const searching = ref(false);
let searchSeq = 0;

async function onSearchReceiver() {
  const q = receiverQuery.value.trim();
  receiver.value = null;
  if (q.length < 2) {
    receiverResults.value = [];
    return;
  }
  const seq = ++searchSeq;
  searching.value = true;
  try {
    const rows = await searchFacilities(q);
    // a slow earlier query must not overwrite a later one's results
    if (seq === searchSeq) receiverResults.value = rows.slice(0, 6);
  } catch {
    if (seq === searchSeq) receiverResults.value = [];
  } finally {
    if (seq === searchSeq) searching.value = false;
  }
}

function chooseReceiver(row) {
  receiver.value = { id: row.id, name: row.name };
  receiverQuery.value = row.name;
  receiverResults.value = [];
}

onMounted(async () => {
  if (!activeStopId.value) return; // pre-acceptance use: nothing to prefill from
  try {
    const meter = await fetchMeter(activeStopId.value);
    loadFacility.value = meter.facility_id ?? null;
    // §11.7: prefill only what the load actually STATES. A rate con silent on the
    // linehaul leaves the field as it was rather than gaining a confident zero.
    if (meter.rate_cents) {
      form.revenue = (meter.rate_cents / 100).toFixed(2);
      prefilled.value = true;
    }
    if (meter.free_time_minutes != null) form.freeMin = meter.free_time_minutes;
    if (meter.rate_cents_per_hour != null) {
      form.rateHr = Math.round(meter.rate_cents_per_hour / 100);
    }
  } catch {
    /* offline / no session: the form keeps its own defaults and says nothing it
       cannot support — the calculation itself already degrades honestly below */
  }
});

function toCents(dollars) {
  return Math.round(Number(dollars || 0) * 100);
}

async function calculate() {
  submitting.value = true;
  const payload = {
    revenue_cents: toCents(form.revenue),
    loaded_miles: Number(form.miles) || 0,
    // AI-CONTEXT: the 6.0 that used to sit here is GONE (§23 entry 154). Omitting the
    // field asks the server for the driver's own reported figure, and the response's
    // `basis.mpg_basis` says which of the two it used — a fuel cost is the second-largest
    // number on this screen and it was computed from a constant nobody was ever shown.
    tolls_cents: toCents(form.tolls),
    // the dock this load is actually going to: the active stop's if there is one, the
    // one the driver picked if there is not. The nil UUID stays as the last resort —
    // the server must still answer when nobody has named a receiver — but the RESULT
    // now says the detention line is not included rather than rendering it as $0.00.
    receiver_facility_id:
      loadFacility.value ||
      receiver.value?.id ||
      route.query.receiver ||
      "00000000-0000-0000-0000-000000000000",
    free_time_minutes: Number(form.freeMin) || 0,
    rate_cents_per_hour: toCents(form.rateHr),
    // where the driver IS, which is what a route-fuel estimate is measured from. The
    // Dallas constant behind it is the same invented coordinate §23 entry 67 removed
    // from the import sheet; it stays only as the last resort on a device with no fix.
    // `||` rather than `??` on the query fallback: an absent param makes `Number()`
    // return NaN, which `??` would happily pass through as an origin.
    origin_lat: lastFix.value?.lat ?? (Number(route.query.lat) || 32.7767),
    origin_lon: lastFix.value?.lon ?? (Number(route.query.lon) || -96.797),
  };
  try {
    result.value = await calcTrueProfit(payload);
  } catch {
    // offline / no session: honest local estimate — fuel + dwell need live data
    const miles = payload.loaded_miles;
    const net = payload.revenue_cents - payload.tolls_cents;
    result.value = {
      revenue_cents: payload.revenue_cents,
      fuel_cost_cents: null,
      tolls_cents: payload.tolls_cents,
      expected_detention_cents: null,
      net_cents: net,
      rpm_after_cents: miles ? Math.round(net / miles) : 0,
      fuel_net_cents_per_gal: null,
      basis: { fuel: "needs_session", detention_sample_size: 0 },
    };
  }
  submitting.value = false;
}

// `default` is the only one worth a line. `driver` means they told us and we used it,
// which needs no announcement; `request` means they typed it into this very screen.
const mpgIsOurs = computed(() => result.value?.basis?.mpg_basis === "default");

const clears = computed(() => (result.value?.net_cents ?? 0) >= 0);

/* AI-CONTEXT: a cost is rendered from its BASIS, never from the number being zero
 * (§23 entry 154, M8-FR5 / §11.7).
 *
 * The server returns 0 for a cost it could not compute — `expected_detention_cost`
 * returns `(0, 0)` with no dwell samples, `route_fuel_cost` returns `(0, None,
 * "no_network_fuel")` with no network station in range. Both then rendered as a
 * confident **−$0.00** and were folded into the headline net. The `=== null` guard the
 * template already had fires only on the OFFLINE local estimate, which is the one path
 * where the UI itself writes the nulls — so the two states that actually happen against a
 * working server were the two it did not cover.
 *
 * §11.7's rule is that a figure does not travel without what produced it, and M8-FR5
 * requires "every prediction displays its basis — no false precision". A zero that means
 * "we did not measure this" is the falsest precision available: it is indistinguishable
 * from a dock that never detains anyone.
 */
const fuelKnown = computed(() => {
  const r = result.value;
  if (!r) return false;
  return r.fuel_cost_cents !== null && r.basis?.fuel !== "no_network_fuel";
});
const detentionKnown = computed(() => {
  const r = result.value;
  if (!r) return false;
  return r.expected_detention_cents !== null && (r.basis?.detention_sample_size ?? 0) > 0;
});
// what the headline figure LEAVES OUT, named beside it rather than left to be inferred
// from two dashes further down the card
const excluded = computed(() => {
  if (!result.value) return [];
  const out = [];
  if (!fuelKnown.value) out.push(t("calc.fuel"));
  if (!detentionKnown.value) out.push(t("calc.detention"));
  return out;
});
</script>

<template>
  <div class="calc">
    <header class="calc__head">
      <button class="back" type="button" aria-label="Back" @click="router.back()">
        <ArrowLeft :size="24" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="calc__title">{{ t("calc.title") }}</h1>
    </header>

    <form class="fields" @submit.prevent="calculate">
      <label class="field">
        <span class="field__label">{{ t("calc.revenue") }}</span>
        <input v-model="form.revenue" class="field__input" type="number" inputmode="decimal" min="0" />
        <!-- §11.7: the figure NAMES WHO IS SPEAKING. A rate carried over from the load
             and a rate the driver typed carry different confidence, and only the driver
             knows whether the contract is right. Editable either way — this is a
             calculator, not a record. -->
        <span v-if="prefilled" class="field__from">{{ t("calc.from_load") }}</span>
      </label>
      <label class="field">
        <span class="field__label">{{ t("calc.miles") }}</span>
        <input v-model="form.miles" class="field__input" type="number" inputmode="numeric" min="0" />
      </label>
      <label class="field">
        <span class="field__label">{{ t("calc.tolls") }}</span>
        <input v-model="form.tolls" class="field__input" type="number" inputmode="decimal" min="0" />
      </label>
      <!-- AI-CONTEXT: only when there is no active stop. With one, the load already
           knows its receiver and asking again would invite a driver to contradict their
           own load (§23 entry 154). -->
      <div v-if="!loadFacility" class="field receiver">
        <span class="field__label">{{ t("calc.receiver") }}</span>
        <input
          v-model="receiverQuery"
          class="field__input"
          type="text"
          :placeholder="t('calc.receiver_hint')"
          @input="onSearchReceiver"
        />
        <ul v-if="receiverResults.length" class="receiver__list">
          <li v-for="row in receiverResults" :key="row.id">
            <button class="receiver__opt" type="button" @click="chooseReceiver(row)">
              {{ row.name }}
            </button>
          </li>
        </ul>
        <span v-if="receiver" class="field__from">{{ t("calc.receiver_set") }}</span>
      </div>

      <label class="field">
        <span class="field__label">{{ t("calc.free_min") }}</span>
        <input v-model="form.freeMin" class="field__input" type="number" inputmode="numeric" min="0" />
      </label>
      <label class="field">
        <span class="field__label">{{ t("calc.rate_hr") }}</span>
        <input v-model="form.rateHr" class="field__input" type="number" inputmode="decimal" min="0" />
      </label>
      <!-- SM-3: a form of number fields is the definition of an interactive
           prompt at speed (Forbidden #11). -->
      <p v-if="isDriving" class="driving-note">{{ t("driving.paused") }}</p>
      <button v-else class="cta" type="submit" :disabled="submitting">
        <Spinner v-if="submitting" />
        {{ submitting ? t("busy.working") : t("calc.calculate") }}
      </button>
    </form>

    <section v-if="result" class="result">
      <div class="result__meter">
        <span class="result__label">{{ t("calc.net") }}</span>
        <span class="result__figure" :class="clears ? 'pos' : 'neg'">{{ formatMoney(result.net_cents) }}</span>
        <span class="result__rpm">{{ formatMoney(result.rpm_after_cents) }} {{ t("calc.rpm") }}</span>
      </div>
      <!-- §11.7: what the figure above LEAVES OUT, beside the figure rather than
           inferable from a dash further down (§23 entry 154) -->
      <p v-if="excluded.length" class="result__excludes">
        {{ t("calc.excludes") }} {{ excluded.join(" · ") }}
      </p>
      <ul class="breakdown">
        <li class="breakdown__row">
          <span>{{ t("calc.revenue") }}</span>
          <span class="mono">{{ formatMoney(result.revenue_cents) }}</span>
        </li>
        <li class="breakdown__row">
          <span>{{ t("calc.fuel") }}</span>
          <span v-if="fuelKnown" class="mono neg">−{{ formatMoney(result.fuel_cost_cents) }}</span>
          <span v-else class="breakdown__unknown">{{ t("calc.not_included") }}</span>
        </li>
        <li class="breakdown__row">
          <span>{{ t("calc.tolls") }}</span>
          <span class="mono neg">−{{ formatMoney(result.tolls_cents) }}</span>
        </li>
        <li class="breakdown__row">
          <span>{{ t("calc.detention") }}</span>
          <span v-if="detentionKnown" class="mono neg">−{{ formatMoney(result.expected_detention_cents) }}</span>
          <span v-else class="breakdown__unknown">{{ t("calc.not_included") }}</span>
        </li>
      </ul>
      <!-- AI-CONTEXT: M8-FR5's basis, all of it. `detention_recovery: "assumed_none"` was
           added by entry 134 as audit F-25's disclosure — the figure models a world where
           the driver recovers NOTHING, inside the app whose thesis is recovering it — and
           it has been computed and returned by the API and rendered by nothing ever since. -->
      <ul class="basis">
        <li v-if="detentionKnown" class="basis__row">
          {{ t("calc.basis_detention") }}
          {{ result.basis.detention_sample_size }} {{ t("profile.stops_basis") }}
        </li>
        <li v-else class="basis__row">{{ t("calc.basis_no_stops") }}</li>
        <li v-if="!fuelKnown" class="basis__row">{{ t("calc.basis_no_fuel") }}</li>
        <li v-if="detentionKnown" class="basis__row">{{ t("calc.basis_recovery") }}</li>
        <!-- WHICH fuel economy this cost came from. `driver` is silent on purpose: a
             driver who reported 5.2 does not need telling that we used 5.2. What needs
             saying is when the number is OURS. -->
        <li v-if="mpgIsOurs" class="basis__row">
          {{ t("calc.basis_mpg_default", { mpg: result.basis.mpg }) }}
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.calc {
  padding: var(--s-4);
}
.calc__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-bottom: var(--s-4);
}
.back {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-1);
}
.calc__title {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.fields {
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
/* provenance, in the same quiet register the Load tab uses for the appointment's
   source — a caption under the figure, never a badge competing with it */
.field__from {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-caption-line);
}
.field__input {
  min-height: 56px;
  padding: 0 var(--s-3);
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  color: var(--text-1);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-body-size);
}
.cta {
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-2);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta:disabled {
  opacity: 0.6;
}
.result {
  margin-top: var(--s-5);
}
.result__meter {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-1);
  padding: var(--s-4) 0;
}
.result__label {
  font-size: var(--type-label-size);
  color: var(--text-2);
}
/* AI-CONTEXT: the same clamp `TheMeter` carries, and the reason it was missing here is
   that this surface copied the TOKEN and not the rule (§23 entry 154).

   T-6: money never truncates, it scales down; the ceiling only bites once the type has
   been scaled past what a 360 dp card can hold (T-5). Measured by the new
   `load-calc-result` state on its first run: `span.result__figure` reached **419 px at
   200% text** in a 360 dp viewport. Nothing had caught it because no harness state had
   ever rendered this card — both existing calc states stop at the button, so the half of
   the surface carrying the figure was unmeasured in every locale. */
.result__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: min(var(--type-meter-size), var(--type-meter-fluid-max));
  line-height: var(--type-meter-line);
  font-weight: var(--type-meter-weight);
}
.result__figure.pos {
  color: var(--ledger-500);
}
.result__figure.neg {
  color: var(--flare-500);
}
.result__rpm {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.breakdown {
  list-style: none;
  margin: var(--s-3) 0 0;
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
  color: var(--text-1);
}
.mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.mono.neg {
  color: var(--text-2);
}
.basis {
  list-style: none;
  margin: var(--s-3) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-caption-line);
}
.basis__row {
  margin: 0;
}
/* §11.7: "not included" is a WORD, not a dash and not a zero. A dash reads as nothing to
   pay; a zero reads as a dock that never detains anyone. Same weight as the figures it
   replaces so it is read rather than skipped, in --text-2 because it is a fact about the
   estimate rather than a warning about the load. */
.breakdown__unknown {
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.result__excludes {
  margin: var(--s-2) 0 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-caption-line);
}
.receiver {
  position: relative;
}
.receiver__list {
  list-style: none;
  margin: var(--s-2) 0 0;
  padding: 0;
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  overflow: hidden;
}
/* §6.5: a picker row is a target a gloved thumb has to hit on the first try */
.receiver__opt {
  display: block;
  width: 100%;
  min-height: 48px;
  padding: 0 var(--s-3);
  text-align: left;
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
</style>
