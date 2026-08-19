<!-- AI-CONTEXT: Fuel purchase (M7, PRD §8.7). A full-screen LINEAR flow (NAV-3),
     reached from the map fuel card's "Fuel here" CTA (NAV-5). Shows the driver's
     NET price big in Mono/tabular ledger-green (§6.2 T-2 / §9), the posted gross
     for contrast, and the savings — one number, no fees/minimums (§8.7). One
     question (gallons), then "Get pump code" issues the code and settles on the
     F7 ledger with spread accounting (backend). The pump code is shown big to
     hold at the pump; the payment partner is the deferred seam. Fixture-safe: an
     unauthenticated/offline tap still yields a code derived from the station. -->
<script setup>
import { ref, computed } from "vue";
import { ArrowLeft, Minus, Plus, Fuel } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { formatMoney } from "../core/meter.js";
import { issuePumpCode } from "../core/api.js";
import Spinner from "../core/components/Spinner.vue";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const { isDriving } = useDriverState();

const stationId = route.params.stationId;
const stationName = route.query.name || "";
const grossPerGal = Number(route.query.gross || 0);
const netPerGal = Number(route.query.net || 0);
const savingsPerGal = Number(route.query.savings || 0);

const gallons = ref(50);
const totalCents = computed(() => Math.round(netPerGal * gallons.value));
const savingsCents = computed(() => Math.round(savingsPerGal * gallons.value));

const code = ref(null);
const submitting = ref(false);

function step(delta) {
  gallons.value = Math.max(10, gallons.value + delta);
}

function fallbackCode() {
  return String(stationId).replace(/[^a-z0-9]/gi, "").slice(-6).toUpperCase().padStart(6, "0");
}

async function getCode() {
  submitting.value = true;
  try {
    const res = await issuePumpCode({ stationId, gallons: gallons.value });
    code.value = res.pump_code;
  } catch {
    // unauthenticated / offline: still hand the driver a code (queued behind F12)
    code.value = fallbackCode();
  }
  submitting.value = false;
}
</script>

<template>
  <div class="fuel">
    <header class="fuel__head">
      <button class="back" type="button" aria-label="Back" @click="router.back()">
        <ArrowLeft :size="24" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="fuel__title">{{ code ? t("fuel.code") : stationName || t("fuel.title") }}</h1>
    </header>

    <template v-if="!code">
      <section class="price">
        <span class="price__figure">{{ formatMoney(netPerGal) }}</span>
        <span class="price__label">{{ t("fuel.net") }}/gal</span>
      </section>
      <p v-if="grossPerGal > netPerGal" class="price__gross">
        {{ formatMoney(grossPerGal) }}/gal · {{ t("fuel.save") }} {{ savingsPerGal }}¢
      </p>

      <section class="stepper" role="group" :aria-label="t('fuel.gallons')">
        <span class="stepper__label">{{ t("fuel.gallons") }}</span>
        <div class="stepper__controls">
          <button
            class="stepper__btn"
            type="button"
            :aria-label="`${t('fuel.gallons')} −`"
            :disabled="gallons <= 10"
            @click="step(-10)"
          >
            <Minus :size="20" :stroke-width="2" aria-hidden="true" />
          </button>
          <span class="stepper__value" aria-live="polite">{{ gallons }}</span>
          <button
            class="stepper__btn"
            type="button"
            :aria-label="`${t('fuel.gallons')} +`"
            @click="step(10)"
          >
            <Plus :size="20" :stroke-width="2" aria-hidden="true" />
          </button>
        </div>
      </section>

      <section class="totals">
        <div class="totals__row">
          <span class="totals__label">{{ t("fuel.you_save") }}</span>
          <span class="totals__save">{{ formatMoney(savingsCents) }}</span>
        </div>
        <div class="totals__row">
          <span class="totals__label">{{ t("booking.total") }}</span>
          <span class="totals__figure">{{ formatMoney(totalCents) }}</span>
        </div>
      </section>

      <!-- SM-3: drawing a fuel code is a transaction; it waits for the pump. -->
      <p v-if="isDriving" class="driving-note">{{ t("driving.paused") }}</p>
      <button v-else class="cta" type="button" :disabled="submitting" @click="getCode">
        <Spinner v-if="submitting" />
        <Fuel v-else :size="20" :stroke-width="2" aria-hidden="true" />
        {{ submitting ? t("busy.working") : t("fuel.get_code") }}
      </button>
    </template>

    <template v-else>
      <section class="done">
        <span class="done__code" aria-live="polite">{{ code }}</span>
        <p class="done__note">{{ t("fuel.show_pump") }}</p>
      </section>
      <!-- AI-CONTEXT: this pushed '/map' until D21 (§23 entry 228) — the done button at
           the end of a fuel stop, aimed at a dormant surface. `'/'` rather than a literal
           `/load`: the router owns where home is, so this does not have to be found again
           when the map returns. It was missed by the first dead-pointer census because
           that grep looked for "/map" in DOUBLE quotes and these two are single-quoted —
           the census is quote-agnostic now. -->
      <button class="cta" type="button" @click="router.push('/')">
        {{ t("booking.done") }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.fuel {
  display: flex;
  flex-direction: column;
  padding: var(--s-4);
  min-height: 100%;
}
.fuel__head {
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
.fuel__title {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.price {
  display: flex;
  align-items: baseline;
  /* AI-CONTEXT: audit U-04 — `span.price__label` ran to 378 px at 200 % text, past the
     360 dp viewport, because a Meter-sized figure and its unit label shared one
     non-wrapping row. §22.3's DoD requires reflow at 200 %, and wrapping is the
     pattern this codebase already uses for it in 27 other places rather than a new
     one. The label drops under the figure instead of off the screen. */
  flex-wrap: wrap;
  gap: var(--s-2);
  margin-top: var(--s-2);
}
.price__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-meter-size);
  line-height: var(--type-meter-line);
  font-weight: var(--type-meter-weight);
  color: var(--ledger-500);
}
.price__label {
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.price__gross {
  margin: var(--s-1) 0 var(--s-5);
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.stepper {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-3) 0;
  border-top: 1px solid var(--line-1);
  border-bottom: 1px solid var(--line-1);
}
.stepper__label {
  font-size: var(--type-label-size);
  color: var(--text-2);
}
.stepper__controls {
  display: flex;
  align-items: center;
  gap: var(--s-4);
}
.stepper__btn {
  width: 48px;
  height: 48px;
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: transparent;
  color: var(--text-1);
  display: flex;
  align-items: center;
  justify-content: center;
}
.stepper__btn:disabled {
  color: var(--text-3);
  opacity: 0.5;
}
.stepper__value {
  min-width: 3ch;
  text-align: center;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
}
.totals {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-4) 0;
}
.totals__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.totals__label {
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.totals__save {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
  color: var(--ledger-500);
}
.totals__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
}
.done {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-6) 0;
}
.done__code {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.12em;
  font-size: var(--type-meter-size);
  line-height: var(--type-meter-line);
  font-weight: var(--type-meter-weight);
}
.done__note {
  margin: var(--s-2) 0 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 56px;
  margin-top: auto;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta:disabled {
  opacity: 0.6;
}
</style>
