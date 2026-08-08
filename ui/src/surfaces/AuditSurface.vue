<!-- AI-CONTEXT: Settlement auditor (M9-FR1, PRD §8.9) — the company-driver wedge.
     A full-screen linear form (NAV-3 / §202): the driver enters what the carrier
     PAID per accessorial kind; the app reconciles it against their own GPS-backed
     receivables and flags the missed pay, evidence attached. Output is framed
     "review with your carrier," never legal advice (§8.9 note). Missed pay is the
     hero figure in Mono/flare (T-2). LIVE via api.js, on the four-state model — it
     used to answer with `sampleAudit()` when the call failed, so a driver asking what
     their carrier had underpaid could be shown an invented discrepancy (§23 entry
     131). A failure says the check did not run. -->
<script setup>
import { ref, reactive, computed } from "vue";
import { ArrowLeft } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { formatMoney } from "../core/meter.js";
import { auditSettlement } from "../core/api.js";
import SkeletonCard from "../core/components/SkeletonCard.vue";
import { LoadState, Failure, failureOf } from "../core/load-state.js";

const router = useRouter();
const { t } = useI18n();
const { isDriving } = useDriverState();

const KINDS = ["detention", "layover", "lumper", "tonu"];
const carrier = ref("");
const paid = reactive({ detention: 0, layover: 0, lumper: 0, tonu: 0 });
const result = ref(null);
const submitting = ref(false);
// AI-CONTEXT: §23 entry 131. `null` means the driver has not asked yet — which is a
// genuine FIFTH condition on this surface and not one of the four states: there is
// nothing to load until the form is submitted, so an idle screen shows the form and
// no skeleton. Once asked, the three remaining states apply.
const auditState = ref(null);
const auditFailure = ref(null);

function isoDaysAgo(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

async function run() {
  submitting.value = true;
  auditState.value = LoadState.LOADING;
  const lines = KINDS.map((kind) => ({ kind, amount_cents: Math.round(Number(paid[kind] || 0) * 100) }));
  try {
    result.value = await auditSettlement({
      carrier: carrier.value || "Carrier",
      periodStart: isoDaysAgo(7),
      periodEnd: isoDaysAgo(0),
      lines,
    });
    auditState.value = LoadState.LOADED;
    auditFailure.value = null;
  } catch (e) {
    // this returned `sampleAudit()` — an invented settlement discrepancy, with an
    // invented figure, presented as the answer to a question the driver just asked
    // about their own pay. A wrong number here is one a driver takes to their carrier.
    result.value = null;
    auditFailure.value = failureOf(e);
    auditState.value = LoadState.FAILED;
  }
  submitting.value = false;
}

const missed = computed(() => result.value?.total_missed_cents ?? 0);
</script>

<template>
  <div class="audit">
    <header class="audit__head">
      <button class="back" type="button" aria-label="Back" @click="router.back()">
        <ArrowLeft :size="24" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="audit__title">{{ t("audit.title") }}</h1>
    </header>

    <form class="fields" @submit.prevent="run">
      <label class="field">
        <span class="field__label">{{ t("audit.carrier") }}</span>
        <input v-model="carrier" class="field__input" type="text" />
      </label>
      <p class="fields__hint">{{ t("audit.paid") }}</p>
      <label v-for="kind in KINDS" :key="kind" class="field field--row">
        <span class="field__label">{{ t(`money.kind.${kind}`) }}</span>
        <input v-model="paid[kind]" class="field__input field__input--num" type="number" inputmode="decimal" min="0" />
      </label>
      <!-- SM-3: same as the calculator — typed figures wait for a stop. -->
      <p v-if="isDriving" class="driving-note">{{ t("driving.paused") }}</p>
      <button v-else class="cta" type="submit" :disabled="submitting">{{ t("audit.run") }}</button>
    </form>

    <SkeletonCard v-if="auditState === LoadState.LOADING" :count="1" />
    <!-- §15.4, and the kickoff's own note about this surface: an audit is a RESULT the
         driver asked for, not an empty state, so a failure has to say plainly that the
         check did not run. Silence here reads as "nothing was found". -->
    <p v-else-if="auditState === LoadState.FAILED" class="audit__failed">
      {{ auditFailure === Failure.OFFLINE ? t("system.load_offline") : t("audit.load_failed") }}
      <button class="audit__retry" type="button" @click="run">{{ t("system.retry") }}</button>
    </p>
    <section v-else-if="result" class="result">
      <template v-if="result.discrepancies.length">
        <div class="result__hero">
          <span class="result__label">{{ t("audit.missed") }}</span>
          <span class="result__figure">{{ formatMoney(missed) }}</span>
        </div>
        <ul class="discs">
          <li v-for="d in result.discrepancies" :key="d.kind" class="disc">
            <span class="disc__kind">{{ t(`money.kind.${d.kind}`) }}</span>
            <span class="disc__missed">{{ formatMoney(d.missed_cents) }}</span>
          </li>
        </ul>
        <p class="review">{{ t("audit.review") }}</p>
      </template>
      <p v-else class="muted">{{ t("audit.none") }}</p>
    </section>
  </div>
</template>

<style scoped>
.audit {
  padding: var(--s-4);
}
.audit__head {
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
.audit__title {
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
.fields__hint {
  margin: var(--s-2) 0 0;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.field--row {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
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
.field__input--num {
  width: 40%;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  text-align: right;
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
.audit__failed {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: var(--s-4);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.audit__retry {
  min-height: 48px;
  padding: 0 var(--s-2);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
.result {
  margin-top: var(--s-5);
}
.result__hero {
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
.result__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-meter-size);
  line-height: var(--type-meter-line);
  font-weight: var(--type-meter-weight);
  color: var(--flare-500);
}
.discs {
  list-style: none;
  margin: var(--s-2) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.disc {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: var(--s-2) 0;
  border-bottom: 1px solid var(--line-1);
}
.disc__kind {
  font-size: var(--type-body-size);
  font-weight: 500;
}
.disc__missed {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
  color: var(--flare-500);
}
.review {
  margin: var(--s-4) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.muted {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
</style>
