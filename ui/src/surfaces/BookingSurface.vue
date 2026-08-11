<!-- AI-CONTEXT: Booking checkout (M6, PRD §8.6). A full-screen LINEAR flow, not a
     sheet (NAV-3: booking checkout is reserved for full-screen pushes). One
     question — how many nights — then ONE final price shown big in Mono/tabular
     (§6.2 T-2, the Meter's money treatment). The take is already baked into the
     nightly rate, so the total is the whole story: no fees appear at confirm
     (§Anti-pattern 8 / line 344 "M6 shows one final price"). The confirm verb
     persists through to the confirmation ("Book spot — $X" → "Booked", §12.2).
     Reached via the map facility card's Book CTA (NAV-5). Fixture-safe: an
     unauthenticated/offline confirm still resolves locally behind api.js. -->
<script setup>
import { ref, computed } from "vue";
import { ArrowLeft, Minus, Plus, Check } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { formatMoney } from "../core/meter.js";
import { bookSpot } from "../core/api.js";
import Spinner from "../core/components/Spinner.vue";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const { isDriving } = useDriverState();

const spotId = route.params.spotId;
const propertyName = route.query.name || "";
const nightlyCents = Number(route.query.nightly || 0);

const nights = ref(1);
const totalCents = computed(() => nightlyCents * nights.value);
const booked = ref(false);
const submitting = ref(false);
const error = ref("");

function step(delta) {
  nights.value = Math.max(1, nights.value + delta);
}

function isoAtMidnight(offsetDays) {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString();
}

async function confirm() {
  submitting.value = true;
  error.value = "";
  try {
    await bookSpot({
      spotId,
      startAt: isoAtMidnight(0),
      endAt: isoAtMidnight(nights.value),
    });
    booked.value = true; // only on a real 201 — never fake a confirmation
  } catch (e) {
    // a booking is transactional (money) — show the real outcome, don't pretend
    error.value = e.status === 409 ? t("book.taken") : t("book.failed");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="book">
    <header class="book__head">
      <button class="back" type="button" aria-label="Back" @click="router.back()">
        <ArrowLeft :size="24" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="book__title">{{ booked ? t("booking.booked") : t("booking.title") }}</h1>
    </header>

    <template v-if="!booked">
      <p class="book__property">{{ propertyName }}</p>
      <p class="book__nightly">
        <span class="book__nightly-figure">{{ formatMoney(nightlyCents) }}</span>
        <span class="book__nightly-label">{{ t("booking.per_night") }}</span>
      </p>

      <section class="stepper" role="group" :aria-label="t('booking.nights')">
        <span class="stepper__label">{{ t("booking.nights") }}</span>
        <div class="stepper__controls">
          <button
            class="stepper__btn"
            type="button"
            :aria-label="`${t('booking.nights')} −`"
            :disabled="nights <= 1"
            @click="step(-1)"
          >
            <Minus :size="20" :stroke-width="2" aria-hidden="true" />
          </button>
          <span class="stepper__value" aria-live="polite">{{ nights }}</span>
          <button
            class="stepper__btn"
            type="button"
            :aria-label="`${t('booking.nights')} +`"
            @click="step(1)"
          >
            <Plus :size="20" :stroke-width="2" aria-hidden="true" />
          </button>
        </div>
      </section>

      <!-- THE one final price: baked-in take, nothing added at confirm -->
      <section class="total">
        <span class="total__label">{{ t("booking.total") }}</span>
        <span class="total__figure">{{ formatMoney(totalCents) }}</span>
      </section>

      <p v-if="error" class="book__error" role="alert">{{ error }}</p>

      <!-- SM-3: a booking moves money, and Forbidden #11 bans acting at speed. -->
      <p v-if="isDriving" class="driving-note">{{ t("driving.paused") }}</p>
      <button v-else class="cta" type="button" :disabled="submitting" @click="confirm">
        <Spinner v-if="submitting" />
        <template v-if="submitting">{{ t("busy.working") }}</template>
        <template v-else>{{ t("facility.book") }} — {{ formatMoney(totalCents) }}</template>
      </button>
    </template>

    <template v-else>
      <section class="done">
        <div class="done__mark" aria-hidden="true">
          <Check :size="40" :stroke-width="2.5" />
        </div>
        <span class="done__figure">{{ formatMoney(totalCents) }}</span>
        <span class="done__meta">{{ nights }} {{ t("booking.nights") }} · {{ propertyName }}</span>
        <p class="done__note">{{ t("booking.confirmation") }}</p>
      </section>
      <button class="cta" type="button" @click="router.push('/map')">
        {{ t("booking.done") }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.book {
  display: flex;
  flex-direction: column;
  padding: var(--s-4);
  min-height: 100%;
}
.book__head {
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
.book__title {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.book__property {
  margin: 0;
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.book__nightly {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  margin: var(--s-2) 0 var(--s-5);
}
.book__nightly-figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
}
.book__nightly-label {
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
  min-width: 2ch;
  text-align: center;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
}
.total {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-1);
  padding: var(--s-5) 0;
}
.total__label {
  font-size: var(--type-label-size);
  color: var(--text-2);
}
.total__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-meter-size);
  line-height: var(--type-meter-line);
  font-weight: var(--type-meter-weight);
  color: var(--ledger-500);
}
.done {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-5) 0;
}
.done__mark {
  width: 72px;
  height: 72px;
  border-radius: var(--r-pill);
  background: var(--ledger-500);
  color: var(--on-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--s-2);
}
.done__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-display-size);
}
.done__meta {
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.done__note {
  margin: var(--s-2) 0 0;
  text-align: center;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.book__error {
  margin: 0 0 var(--s-2);
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-control);
  background: color-mix(in srgb, var(--flare-500) 12%, transparent);
  color: var(--flare-500);
  font-size: var(--type-body-size);
  text-align: center;
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
