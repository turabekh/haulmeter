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
import { ChevronRight } from "lucide-vue-next";
import TheMeter from "../core/components/TheMeter.vue";
import BottomSheet from "../core/components/BottomSheet.vue";
import GhostwriterSheet from "../core/components/GhostwriterSheet.vue";
import ClaimMoneySheet from "../core/components/ClaimMoneySheet.vue";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { formatMoney } from "../core/meter.js";
import { online } from "../core/api.js";
import { receivableStatusToken } from "../core/presentation.js";
import { fetchOwed, fetchEarnings, fetchMe, markReceivablePaid, fetchUnfiled, generateClaim } from "../core/api.js";
import Spinner from "../core/components/Spinner.vue";
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
// AI-CONTEXT: THE HALF OF THE PIPELINE THIS TAB NEVER SHOWED (§23 entry 226, owner).
//
// "Load tab showed actual money accrued waiting, but after I finish the load the Money
// tab is not showing any money." Nothing was wrong with the arithmetic: this tab lists
// FILED claims, filing is what opens a receivable, and everything before filing was
// invisible — including the only money on the screen the driver can still act on.
//
// A filed claim is waiting on somebody else. An unfiled one is waiting on the DRIVER.
// That is why this list sits above "Waiting on brokers" and carries the action.
const unfiled = ref([]);
const unfiledState = ref(LoadState.LOADING);
const unfiledFailure = ref(null);
const filingId = ref("");
const fileError = ref("");
const earnings = ref(EMPTY_EARNINGS);
const owedState = ref(LoadState.LOADING);
const owedFailure = ref(null);
const earningsState = ref(LoadState.LOADING);
const earningsFailure = ref(null);
const drafting = ref(false);
// N-08: the sheet has declared a `busy` prop since it shipped and no parent ever bound
// it, so both money CTAs stayed live through the in-flight POST — a double-tap guard
// wired to nothing. It is bound now, by the same state that holds the failure.
const paidBusy = ref(false);
const paidFailure = ref(null);
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

async function loadUnfiled() {
  try {
    unfiled.value = await fetchUnfiled();
    unfiledState.value = LoadState.LOADED;
    unfiledFailure.value = null;
  } catch (e) {
    unfiled.value = [];
    unfiledFailure.value = failureOf(e);
    unfiledState.value = LoadState.FAILED;
  }
}

// AI-CONTEXT: filing IN PLACE rather than sending the driver to the Load tab to find the
// stop again — the whole defect is that filing was invisible, and a row that only points
// at another screen leaves it invisible with an extra tap. `generateClaim` is the same
// call the Load tab's ladder makes, 409 included: already filed is a success arriving
// twice, so it refreshes rather than complaining.
async function onFile(row) {
  if (filingId.value) return;
  filingId.value = row.claim_id;
  fileError.value = "";
  try {
    await generateClaim(row.stop_id);
  } catch (e) {
    // §15.4 — this is a money-moving action and its failure is never silent
    fileError.value = online.value ? t("money.file_failed") : t("money.file_offline");
    filingId.value = "";
    return;
  }
  filingId.value = "";
  // the row moves from one list to the other, so BOTH have to be re-read
  await Promise.all([loadUnfiled(), refreshMoney()]);
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
  await loadUnfiled();
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

// AI-CONTEXT: "Money owed" listed money that was NOT owed (§23 entry 142).
//
// `money_owed` returns EVERY receivable — `recovered` and `written_off` included, newest
// first — and this tab rendered all of them under a heading that says they are owed. So a
// driver's paid claims piled up above the ones a broker was sitting on, and the list a
// driver is meant to act on was padded with claims that need nothing.
//
// Two lists now, and the ORDER is the point: outstanding first, OLDEST first, because the
// claim nobody has paid for 63 days is the one that needs a person and the one a
// newest-first list buries.
const SETTLED_STATES = ["recovered", "written_off"];
const outstanding = computed(() =>
  rows.value
    .filter((r) => !SETTLED_STATES.includes(r.state))
    .slice()
    .sort((a, b) => (b.aging_days ?? 0) - (a.aging_days ?? 0)),
);
const settled = computed(() => rows.value.filter((r) => SETTLED_STATES.includes(r.state)));
const settledOpen = ref(false);
// the figure a driver opens this tab to learn, and it is a SUM OF THE LIST BELOW IT —
// which is the property the old hero did not have.
const owedCents = computed(() => outstanding.value.reduce((n, r) => n + r.amount_cents, 0));
// AI-CONTEXT: DELIBERATELY NOT ADDED TO THE HERO (§23 entry 226).
//
// Entry 142 made "Owed to you" a strict SUM OF THE LIST BENEATH IT, and that
// reconciliation property is the only reason a figure that large is allowed on this
// screen. Unfiled money is owed by NOBODY: no invoice exists and no broker has been
// told. Folding it in would rebuild the exact defect 142 removed — a driver could carry
// the number to a broker who has never heard of it. Its own subtotal, its own section.
const unfiledCents = computed(() => unfiled.value.reduce((n, r) => n + r.amount_cents, 0));
const owedBrokers = computed(
  () => new Set(outstanding.value.map((r) => r.counterparty_name).filter(Boolean)).size,
);
// NET, and read from the server rather than recomputed here — the figure and the rows it
// reconciles against must come from one place, or the screen can disagree with itself.
const yearNetCents = computed(() => earnings.value?.recovered_year_net_cents ?? 0);
const owedFrom = computed(() =>
  owedBrokers.value === 1 ? t("money.owed_from_one") : t("money.owed_from", { n: owedBrokers.value }),
);

// AI-CONTEXT: THE EMPTY STATE NAMED ONE CAUSE AND THERE ARE FOUR (§23 entry 215).
//
// §15.3 specifies the sentence "Recovered and saved money shows up here. Add your first
// load to start the meter." — and the owner read it while holding SEVEN loads and
// FOURTEEN detention claims. Every claim was `open` with $0 accrued, because every stop
// had ended inside its free time, so no receivable was ever opened and the list was
// correctly empty. An empty state that can only describe a driver who has done nothing
// tells every other driver the screen is broken, which is exactly how it was reported.
//
// The cases are ordered MOST ACTIONABLE FIRST, and the first one is the only one with
// money in it: detention already accrued on a stop that was never filed. `number rather
// than sentence` (§22.2) is why the figure leads that message.
//
// The fallback when the summary has not loaded is §15.3's original sentence, unchanged:
// a screen that cannot prove which case it is in says the least specific true thing.
const emptyMessage = computed(() => {
  if (earningsState.value !== LoadState.LOADED) return t("money.empty");
  const e = earnings.value ?? {};
  if ((e.accrued_unfiled_cents ?? 0) > 0)
    return t("money.empty_unfiled", { money: formatMoney(e.accrued_unfiled_cents) });
  if ((e.open_claims ?? 0) > 0) return t("money.empty_free_time");
  if (e.has_loads) return t("money.empty_no_claims");
  return t("money.empty");
});

// the row a driver tapped, and the acts it offers
const openRow = ref(null);
function closeRow() {
  openRow.value = null;
  // the failure belongs to one attempt on one claim; carrying it to the next claim the
  // driver opens would report a failure that never happened there
  paidFailure.value = null;
  paidBusy.value = false;
}
function daysLabel(r) {
  return r.aging_days === 1 ? t("money.days_one") : t("money.days", { n: r.aging_days });
}
function chasedLabel(r) {
  const n = (r.history ?? []).filter((e) => e.event !== "invoiced").length;
  if (n === 0) return t("money.chased_none");
  if (n === 1) return t("money.chased_one");
  return t("money.chased_many", { n });
}
// AI-CONTEXT: A FAILED "THEY PAID ME" USED TO SAY NOTHING AT ALL (N-07, §23 entry 218).
//
// This closed the sheet FIRST and then called a helper whose entire error path was an
// empty `catch` with a comment explaining why that was acceptable. Measured in the real
// component: the POST was attempted, it was rejected, the sheet closed, the row was
// unchanged, and no wording anywhere on the screen said it had not happened. §15.4 is
// explicit — "failed money-moving actions are always explicit and persistent until
// resolved" — and this is the ONLY money-moving act a driver has in this product.
//
// So the sheet is closed by SUCCESS, not by the tap. On failure it stays open holding a
// specific sentence, and the button that failed is the button that retries.
//
// 409 IS NOT A FAILURE: F7's ledger refuses a transition out of `recovered`/`written_off`,
// which means somebody already recorded this — the work succeeded, it just was not ours.
// `generateClaim` sets that precedent for a double-tap on the claim rail; the same read
// applies here, and treating it as an error would teach a driver to re-tap a row that is
// already settled.
async function onSheetPaid() {
  const row = openRow.value;
  if (!row || paidBusy.value) return;
  paidBusy.value = true;
  paidFailure.value = null;
  try {
    await markReceivablePaid(row.receivable_id);
  } catch (e) {
    if (e?.status !== 409) {
      // no status at all means `fetch` itself threw — a dead zone, not a refusal, and
      // the two need different sentences because only one of them is worth retrying now
      paidFailure.value = e?.status ? t("money.paid_failed") : t("money.paid_failed_offline");
      paidBusy.value = false;
      return;
    }
  }
  paidBusy.value = false;
  openRow.value = null;
  await refreshMoney();
}
// the claim being chased, held while the ghostwriter is open
const chasing = ref(null);
function onSheetChase() {
  // M11-FR3's ghostwriter, reached from the claim it is about rather than from an
  // unnamed button at the bottom of the tab. The driver reads and sends it themselves,
  // so this never becomes a second automatic mail beside the dunning cadence.
  //
  // AI-CONTEXT: THE CLAIM TRAVELS WITH IT NOW (§23 entry 235). `closeRow()` cleared
  // `openRow` and the sheet mounted with no props, so the one thing this flow knows —
  // which claim it is chasing — was discarded one line before it was needed. The row is
  // captured FIRST and held for the sheet.
  chasing.value = openRow.value;
  closeRow();
  drafting.value = true;
}
function onSheetEvidence() {
  const row = openRow.value;
  closeRow();
  if (row?.stop_id) router.push(`/load/${row.stop_id}/evidence`);
}

async function refreshMoney() {
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
    <!-- AI-CONTEXT: the hero is WHAT YOU ARE OWED (owner decision, §23 entry 142).
         It replaced "Delivered to you", which was wrong three ways at once:

           · it summed `recovered + fuel_saved + flagged`, and §10.3 asks for
             "recovered + saved" — `flagged` is money an AUDIT SUSPECTS is owed and
             nobody has paid, sitting inside a figure captioned as delivered;
           · it was a LIFETIME total (`money_owed` has no date filter) presented where
             §10.3 specifies a month summary;
           · so the biggest, greenest number on the screen told a driver they had
             received $1,432.50 when they had received $987.

         This one is a sum of the list directly beneath it, which is the property that
         makes it checkable — and it is the question a driver opens this tab to ask.
         `ledger` variant: it is money, and it is real. -->
    <section v-else class="card meter-card">
      <TheMeter
        :label="t('money.owed_label')"
        :figure="formatMoney(owedCents)"
        :status="owedBrokers ? owedFrom : ''"
        variant="accruing"
      />
      <!-- AI-CONTEXT: the year figure is a SECONDARY line, not a second Meter (J1 part
           4, owner decision).
           §23 entry 142 made this screen's one hero "what you are owed" after the
           previous hero was wrong three ways, and a rival figure of similar weight would
           undo that hierarchy — two large numbers and no answer to which one the tab is
           about. It sits under the hero, NET of fees, and reconciles against the settled
           rows below: a driver can add it up on their own screen. -->
      <p v-if="yearNetCents > 0" class="year">
        <span class="year__label">{{ t("money.year_recovered", { year: earnings.year }) }}</span>
        <span class="year__figure mono">{{ formatMoney(yearNetCents) }}</span>
      </p>
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
        <span>{{ t("money.paid_so_far") }}</span>
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

    <!-- AI-CONTEXT: what the DRIVER still has to do, above what a broker has to do.
         §8's one-primary rule is satisfied per row: each carries a single act, "Send it
         to the broker". The subtotal is a plain line rather than a second Meter — two
         large figures and no answer to which one the tab is about is what entry 142
         removed, and this money is the more provisional of the two. -->
    <template v-if="unfiledState === LoadState.LOADED && unfiled.length">
      <h1 class="money__title">{{ t("money.unfiled_title") }}</h1>
      <p class="money__sub">
        {{ t("money.unfiled_hint") }}
        <span class="mono">{{ formatMoney(unfiledCents) }}</span>
      </p>
      <p v-if="fileError" class="money__failed" role="alert">{{ fileError }}</p>
      <ul class="rows">
        <li v-for="r in unfiled" :key="r.claim_id">
          <div class="row row--unfiled">
            <span class="row__main">
              <span class="row__kind">{{ r.facility_name || t("money.no_dock") }}</span>
              <span class="row__who">{{ r.counterparty_name || t("money.no_broker") }}</span>
            </span>
            <span class="row__right">
              <span class="row__amount">{{ formatMoney(r.amount_cents) }}</span>
              <span class="row__aging">{{ daysLabel(r) }}</span>
            </span>
            <button
              class="row__file"
              type="button"
              :disabled="!!filingId || isDriving"
              @click="onFile(r)"
            >
              <Spinner v-if="filingId === r.claim_id" />
              {{ t("money.file_it") }}
            </button>
          </div>
        </li>
      </ul>
    </template>
    <p v-else-if="unfiledState === LoadState.FAILED" class="money__failed">
      {{ unfiledFailure === Failure.OFFLINE ? t("system.load_offline") : t("money.unfiled_failed") }}
      <button class="money__retry" type="button" @click="loadUnfiled">{{ t("system.retry") }}</button>
    </p>

    <h1 class="money__title">{{ t("money.waiting") }}</h1>
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
    <p v-else-if="!rows.length" class="money__empty">{{ emptyMessage }}</p>
    <!-- everything filed has been paid: a different sentence from "nothing here yet",
         and the one a driver has earned the right to read. -->
    <p v-else-if="!outstanding.length" class="money__empty">{{ t("money.all_paid") }}</p>
    <ul v-else class="rows">
      <!-- AI-CONTEXT: the row is a CONTROL now (§10.3's per-receivable next action,
           specified since §10.3 was written and never built). It said
           "Detention · Invoiced · $187.50 · 12d" and did nothing when tapped, while the
           only way to record a payment was a button at the bottom of the tab asking
           "which claim did the broker pay?" — so a driver looking straight at the claim
           had to go and find it again in a list. -->
      <li v-for="r in outstanding" :key="r.receivable_id">
        <button class="row" type="button" @click="openRow = r">
          <span class="row__main">
            <span class="row__kind">{{ kindLabel(r.kind) }}</span>
            <span class="row__who">{{ r.counterparty_name || t("money.no_broker") }}</span>
          </span>
          <span class="row__right">
            <span class="row__amount">{{ formatMoney(r.amount_cents) }}</span>
            <span class="row__aging">{{ daysLabel(r) }}</span>
          </span>
          <!-- what has been TRIED, in words. "Invoiced · 63d" told a driver the state of
               a database row; this tells them whether anyone has chased it. -->
          <span class="row__foot">
            <span class="row__chased">{{ chasedLabel(r) }}</span>
            <ChevronRight :size="18" :stroke-width="2" class="row__go" aria-hidden="true" />
          </span>
        </button>
      </li>
    </ul>

    <!-- settled claims, out of the way but not gone: the wins are worth seeing, and a
         driver checking what a broker actually paid should not have to leave this tab. -->
    <template v-if="settled.length">
      <button class="settled-toggle" type="button" :aria-expanded="settledOpen" @click="settledOpen = !settledOpen">
        {{ settledOpen ? t("money.settled_hide") : t("money.settled_show") }}
        <span class="settled-toggle__count">{{ settled.length }}</span>
      </button>
      <ul v-if="settledOpen" class="rows">
        <li v-for="r in settled" :key="r.receivable_id" class="row row--settled">
          <span class="row__main">
            <span class="row__kind">{{ kindLabel(r.kind) }}</span>
            <span class="row__who">{{ r.counterparty_name || t("money.no_broker") }}</span>
          </span>
          <span class="row__right">
            <span class="row__amount">{{ formatMoney(r.amount_cents) }}</span>
            <span
              class="pill"
              :style="{ '--pill-color': `var(${receivableStatusToken(r.state)})` }"
            >{{ stateLabel(r.state) }}</span>
          </span>
          <!-- AI-CONTEXT: what we took, as its own VISIBLE line (J1 part 3).
               The deduction is shown rather than implied by a smaller total, so the
               driver can reconcile the year figure above against these rows — entry
               142's property, which is the only reason a big number is allowed here.
               And it says plainly that we have not collected it: a fee shown without
               that sentence reads as money already gone. -->
          <span v-if="r.fee_cents > 0" class="row__fee">
            <span class="row__feeline">
              {{ t("money.fee_taken") }}
              <span class="mono">−{{ formatMoney(r.fee_cents) }}</span>
              <span class="row__feenet">{{ t("money.fee_yours") }} <span class="mono">{{ formatMoney(r.net_cents) }}</span></span>
            </span>
            <span class="row__feenote">{{ t("money.fee_uncollected") }}</span>
          </span>
        </li>
      </ul>
    </template>

    <!-- AI-CONTEXT: §10.3 SPECIFIES this tab's DRIVING behaviour — "read-only;
         actions deferred" — and it was never implemented, so both flows opened at
         speed. The figures above stay readable, which is the whole of what §10.3
         allows; the two things that ACT withdraw and say when they return.

         The ghostwriter sheet closes with them: the control that opens a flow and
         the flow itself are two different things to guard, which is exactly how the
         Docs capture sheet stayed open at speed. -->
    <template v-if="!isDriving">
      <!-- AI-CONTEXT: THREE identical blue text links used to sit here — "Audit a
           settlement", "Ghostwriter" and "Mark a claim paid" — at equal weight, two of
           them named after internal machinery rather than after anything a driver wants.
           The last two belong to a CLAIM and live in its sheet now (§23 entry 142), so
           what remains is the one act that is about a settlement rather than a claim,
           said in the driver's words. -->
      <button class="audit-cta" type="button" @click="router.push('/money/audit')">
        {{ t("money.audit_cta") }}
      </button>
    </template>
    <p v-else class="driving-note">{{ t("driving.paused") }}</p>

    <!-- the claim a driver tapped. Withdrawn at speed like every other acting surface
         on this tab (§10.3: read-only while DRIVING). -->
    <BottomSheet
      :open="!!openRow && !isDriving"
      :title="openRow ? kindLabel(openRow.kind) : ''"
      @close="closeRow"
    >
      <ClaimMoneySheet
        v-if="openRow"
        :row="openRow"
        :busy="paidBusy"
        :failure="paidFailure"
        :payable="PAYABLE_STATES.includes(openRow.state)"
        @chase="onSheetChase"
        @paid="onSheetPaid"
        @evidence="onSheetEvidence"
      />
    </BottomSheet>

    <BottomSheet
      :open="drafting && !isDriving"
      :title="t('ghost.title')"
      @close="((drafting = false), (chasing = null))"
    >
      <GhostwriterSheet
        :stop-id="chasing?.stop_id || null"
        :counterparty="chasing?.counterparty_name || null"
        :facility="chasing?.facility_name || null"
        :amount="chasing ? formatMoney(chasing.amount_cents) : null"
      />
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
/* the row is a control: full width, its own target height, and it ends in a chevron
   because §23 entry 128 says a row that DOES something does. */
.row__who {
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
/* its own line under the figure: `.row` wraps, so a full basis is what puts it there
   without a second layout system inside one card. */
.row__chased {
  min-width: 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.row__go {
  flex-shrink: 0;
  color: var(--text-3);
}
.year {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-2);
  margin: var(--s-3) 0 0;
}
.year__label {
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.year__figure {
  color: var(--text-1);
  font-size: var(--type-title-size);
}
.row__fee {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  width: 100%;
  margin-top: var(--s-2);
}
.row__feeline {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1) var(--s-2);
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.row__feenet {
  color: var(--text-1);
}
.row__feenote {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.row--settled {
  opacity: 0.75;
}
.settled-toggle {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 48px;
  margin-top: var(--s-2);
  padding: 0 var(--s-4);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.settled-toggle__count {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-3);
}
.money__empty {
  margin: 0 var(--s-4);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.row--unfiled {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--s-2);
  width: 100%;
  text-align: left;
}
.money__sub {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: 0 var(--s-4) var(--s-2);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.row__file {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  min-height: 48px;
  margin-top: var(--s-2);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-body-size);
  font-weight: 600;
}
.row__file:disabled {
  opacity: 0.6;
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
  /* §6.5's list-row height, and it is a real target now: the row became a control when
     §10.3's per-receivable action finally existed (§23 entry 142). */
  min-height: 64px;
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-1) var(--s-3);
  padding: var(--s-3) var(--s-4);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  text-align: left;
}
.row__main {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  /* `flex: 1 1 auto` with `min-width: 0` is what keeps the amount on the SAME line as
     the kind: without it a long broker name pushes the figure onto its own row, which
     is what "Blue Road Logistics LLC" did. The NAME wraps; the money never does. */
  flex: 1 1 auto;
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
  flex: 0 0 auto;
}
/* the row's second line: what has been tried, and the affordance that says it opens */
.row__foot {
  flex: 1 0 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-2);
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
