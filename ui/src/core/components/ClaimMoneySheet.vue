<!-- AI-CONTEXT: one claim's story and its next step (§23 entry 142, §10.3's
     "per-receivable Next action" — specified since §10.3 was written, never built).

     THE ROWS DID NOTHING. The Money tab listed "Detention · Invoiced · $187.50 · 12d"
     with no tap target anywhere on it, and the only way to record a payment was a
     button at the bottom of the tab that asked "which claim did the broker pay?" — so a
     driver looking straight at the claim had to go and find it again in a list.

     WHAT A DRIVER ACTUALLY ASKS, in order, and what this answers:
       who has my money        -> the counterparty, named
       what was it for         -> the kind, and the dock it came from
       how long                -> days, spelled out, not "63d"
       has anyone chased them  -> the real dunning history, or "Nothing sent yet"
       what do I do now        -> ONE action, with the other two below it

     CHASING IS THE GHOSTWRITER, not a new send. M11-FR3 already drafts "the firm
     message that unsticks pay" and sat on this tab as an unnamed button called
     "Ghostwriter". Routing the chase through it means the driver reads and sends the
     message themselves — no second automatic mail beside the dunning job's own cadence,
     which is the double-notify the wedge session spent a day removing. -->
<script setup>
import { computed } from "vue";
import { Check, Send } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { formatMoney } from "../meter.js";

const props = defineProps({
  row: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  // AI-CONTEXT: F7's ALLOWED_TRANSITIONS at the point of OFFER. `recovered` and
  // `written_off` are terminal, so a "They paid me" on one would promise something the
  // ledger refuses — the rule the picker sheet used to carry, moved to where the offer
  // now lives rather than lost with it.
  payable: { type: Boolean, default: true },
  // AI-CONTEXT: §15.4 — "failed money-moving actions are always explicit and persistent
  // until resolved" (N-07). Recording a payment is the ONLY money-moving act a driver
  // has, and its failure was swallowed into an empty catch: the sheet closed, the row
  // was unchanged, and nothing on the screen said it had not happened. Measured, not
  // argued. The message lands HERE rather than on the tab because the act belongs to
  // this claim (entry 142) — and the sheet stays open holding it, so the button that
  // failed is the button that retries.
  failure: { type: String, default: null },
});
const emit = defineEmits(["chase", "paid", "evidence"]);
const { t, has } = useI18n();

const kindLabel = computed(() => t(`money.kind.${props.row.kind}`));
const stateLabel = computed(() => t(`money.state.${props.row.state}`));
const history = computed(() => props.row.history ?? []);
// the chasers only — the invoice is not a chase, and counting it would tell a driver
// their claim had been followed up when nothing had been sent.
const chases = computed(() => history.value.filter((e) => e.event !== "invoiced").length);
const chasedLabel = computed(() => {
  if (chases.value === 0) return t("money.chased_none");
  if (chases.value === 1) return t("money.chased_one");
  return t("money.chased_many", { n: chases.value });
});
const daysLabel = computed(() =>
  props.row.aging_days === 1 ? t("money.days_one") : t("money.days", { n: props.row.aging_days }),
);
function evLabel(event) {
  const key = `money.ev.${event}`;
  return has(key) ? t(key) : event;
}
function day(iso) {
  return iso ? String(iso).slice(0, 10) : "";
}
</script>

<template>
  <div class="cm">
    <p class="cm__figure">{{ formatMoney(row.amount_cents) }}</p>
    <p class="cm__who">
      {{ row.counterparty_name || t("money.no_broker") }}
    </p>
    <p class="cm__meta">
      {{ kindLabel }}<template v-if="row.facility_name"> · {{ row.facility_name }}</template>
    </p>
    <p class="cm__meta">{{ daysLabel }} · {{ stateLabel }}</p>

    <!-- §11.7: the history is what actually happened, and an empty one says so rather
         than implying the claim is being worked. -->
    <h3 class="cm__label">{{ t("money.detail_what") }}</h3>
    <ul v-if="history.length" class="cm__hist">
      <li v-for="(e, i) in history" :key="i" class="cm__ev">
        <Check :size="16" :stroke-width="2" class="ok" aria-hidden="true" />
        <span class="cm__evname">{{ evLabel(e.event) }}</span>
        <span class="cm__evday">{{ day(e.at) }}</span>
      </li>
    </ul>
    <p class="cm__quiet">{{ chasedLabel }}</p>

    <!-- §8: ONE Primary. Chasing is the act that can still change the outcome, so it
         leads; recording a payment and reading the evidence sit below it. -->
    <button class="cta" type="button" :disabled="busy" @click="emit('chase')">
      <Send :size="18" :stroke-width="2" aria-hidden="true" />
      {{ t("money.act_chase") }}
    </button>
    <p v-if="failure" class="cm__failed" role="alert">{{ failure }}</p>
    <button
      v-if="payable"
      class="cta cta--text"
      type="button"
      :disabled="busy"
      @click="emit('paid')"
    >
      {{ t("money.act_paid") }}
    </button>
    <button
      v-if="row.stop_id"
      class="cta cta--text"
      type="button"
      @click="emit('evidence')"
    >
      {{ t("money.act_evidence") }}
    </button>
  </div>
</template>

<style scoped>
.cm {
  display: flex;
  flex-direction: column;
}
/* §6.2/§9: money is Mono and tabular, and never truncated (Forbidden #5) */
.cm__figure {
  margin: 0;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-meter-size, var(--type-title-size));
  line-height: 1.1;
  color: var(--ledger-500);
}
.cm__who {
  margin: var(--s-2) 0 0;
  font-size: var(--type-title-size);
  font-weight: var(--type-title-weight);
  color: var(--text-1);
}
.cm__meta {
  margin: var(--s-1) 0 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.cm__label {
  margin: var(--s-4) 0 var(--s-2);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  font-weight: 500;
}
.cm__hist {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.cm__ev {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.cm__evname {
  flex: 1 1 auto;
  min-width: 0;
}
.cm__evday {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.cm__failed {
  margin: var(--s-3) 0 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.cm__quiet {
  margin: var(--s-2) 0 var(--s-4);
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.ok {
  color: var(--ledger-500);
}
.cta {
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
.cta--text {
  margin-top: var(--s-2);
  min-height: 48px;
  background: transparent;
  color: var(--shield-500);
}
</style>
