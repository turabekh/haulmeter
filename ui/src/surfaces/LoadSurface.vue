<!-- AI-CONTEXT: Load tab (design-prd §10.2) — the current stop and its money/
     evidence state. Anatomy at 360 dp: The Meter card (state-dependent) → stop
     context row → evidence checklist → state-dependent single CTA. DRIVING:
     collapses to a Meter-only glance (§10.2 / §5). Fixture-backed pending the
     active-load API. S2 dock-task session. -->
<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { Check, Camera, Send } from "lucide-vue-next";
import { useRouter } from "vue-router";
import TheMeter from "../core/components/TheMeter.vue";
import { useDriverState } from "../core/state.js";
import { useI18n } from "../core/i18n.js";
import { computeDetentionState, meterVariant, formatClock, formatMoney } from "../core/meter.js";
import { SAMPLE_STOP as stop } from "../core/fixtures.js";

const { isDriving } = useDriverState();
const { t } = useI18n();
const router = useRouter();

const arrivalMs = ref(0);
const now = ref(Date.now());
let timer = null;
onMounted(() => {
  arrivalMs.value = Date.now() - stop.arrival_offset_min * 60000;
  timer = setInterval(() => (now.value = Date.now()), 1000);
});
onUnmounted(() => timer && clearInterval(timer));

const state = computed(() =>
  computeDetentionState(arrivalMs.value, stop.free_time_minutes, stop.rate_cents_per_hour, now.value),
);
const withinFree = computed(() => state.value.phase === "within_free_time");
const meterLabel = computed(() => (withinFree.value ? t("load.free_time") : t("load.detention")));
const meterFigure = computed(() =>
  withinFree.value
    ? formatClock(state.value.freeTimeRemainingSeconds)
    : formatMoney(state.value.amountCents),
);
const meterStatus = computed(() =>
  withinFree.value ? "" : `${formatClock(state.value.detentionSeconds)} · $75/h`,
);
const variant = computed(() => meterVariant(state.value));
const primaryCta = computed(() => (withinFree.value ? t("load.cta.notice") : t("load.cta.claim")));
</script>

<template>
  <div class="load">
    <section class="card meter-card">
      <TheMeter :label="meterLabel" :figure="meterFigure" :variant="variant" :status="meterStatus" />
    </section>

    <template v-if="!isDriving">
      <div class="context">
        <span class="context__name">{{ stop.facility_name }}</span>
        <span class="context__meta">{{ stop.appointment }} · {{ stop.counterparty }}</span>
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
            {{ t("load.photos") }} {{ stop.evidence.photos_taken }}/{{ stop.evidence.photos_total }}
          </li>
          <li class="checklist__item">
            <Send :size="20" :stroke-width="2" aria-hidden="true" />
            {{ t("load.notice_sent") }}
          </li>
        </ul>
      </section>

      <button class="cta" type="button">{{ primaryCta }}</button>
      <!-- M8: pre-acceptance decision — cross-link to the true-profit calculator (NAV-5) -->
      <button class="cta cta--text" type="button" @click="router.push('/load/calc')">
        {{ t("load.check_profit") }}
      </button>
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
.cta {
  width: 100%;
  min-height: 56px;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
/* text button (§8) — the secondary cross-link verb to the profit calculator */
.cta--text {
  margin-top: var(--s-2);
  min-height: 48px;
  background: transparent;
  color: var(--shield-500);
}
</style>
