<!-- AI-CONTEXT: Money tab (design-prd §10.3 / §238) — the driver's P&L with the
     platform. Anatomy at 360 dp: month summary in The Meter treatment — the
     North Star DRIVER DOLLARS DELIVERED (recovered + fuel saved + audit-flagged,
     M9-FR4) → its breakdown → receivables list (status pills + aging in Mono).
     S3 comfortable density (§7.4). Money is ALWAYS Mono + tabular, never
     truncated (T-2/T-6). Fixture-backed until the live APIs answer. -->
<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import TheMeter from "../core/components/TheMeter.vue";
import BottomSheet from "../core/components/BottomSheet.vue";
import GhostwriterSheet from "../core/components/GhostwriterSheet.vue";
import { useI18n } from "../core/i18n.js";
import { formatMoney } from "../core/meter.js";
import { receivableStatusToken } from "../core/presentation.js";
import { fetchOwed, fetchEarnings } from "../core/api.js";
import { SAMPLE_OWED, SAMPLE_EARNINGS } from "../core/fixtures.js";

const { t } = useI18n();
const router = useRouter();
const rows = ref(SAMPLE_OWED);
const earnings = ref(SAMPLE_EARNINGS);
const drafting = ref(false);

onMounted(async () => {
  try {
    rows.value = await fetchOwed();
  } catch {
    rows.value = SAMPLE_OWED; // unauthenticated / offline
  }
  try {
    earnings.value = await fetchEarnings();
  } catch {
    earnings.value = SAMPLE_EARNINGS; // unauthenticated / offline
  }
});

function kindLabel(kind) {
  return t(`money.kind.${kind}`);
}
function stateLabel(state) {
  return t(`money.state.${state}`);
}
</script>

<template>
  <div class="money">
    <!-- North Star: Driver Dollars Delivered (§238 month summary, Meter) -->
    <section class="card meter-card">
      <TheMeter
        :label="t('money.delivered')"
        :figure="formatMoney(earnings.ddd_cents)"
        variant="accruing"
      />
    </section>

    <ul class="breakdown">
      <li class="breakdown__row">
        <span>{{ t("money.recovered") }}</span>
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

    <h1 class="money__title">{{ t("money.title") }}</h1>
    <ul class="rows">
      <li v-for="r in rows" :key="r.receivable_id" class="row">
        <div class="row__main">
          <span class="row__kind">{{ kindLabel(r.kind) }}</span>
          <span
            class="pill"
            :style="{ '--pill-color': `var(${receivableStatusToken(r.state)})` }"
          >
            {{ stateLabel(r.state) }}
          </span>
        </div>
        <div class="row__right">
          <span class="row__amount">{{ formatMoney(r.amount_cents) }}</span>
          <span class="row__aging">{{ r.aging_days }}d</span>
        </div>
      </li>
    </ul>

    <!-- M9-FR1: the settlement auditor — the company-driver wedge (NAV-5) -->
    <button class="audit-cta" type="button" @click="router.push('/money/audit')">
      {{ t("audit.title") }}
    </button>
    <!-- M11-FR3: the comms ghostwriter — draft the firm message that unsticks pay -->
    <button class="audit-cta" type="button" @click="drafting = true">
      {{ t("ghost.title") }}
    </button>

    <BottomSheet :open="drafting" :title="t('ghost.title')" @close="drafting = false">
      <GhostwriterSheet />
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
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  padding: var(--s-3) var(--s-4);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
}
.row__main {
  display: flex;
  align-items: center;
  gap: var(--s-2);
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
.row__right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
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
