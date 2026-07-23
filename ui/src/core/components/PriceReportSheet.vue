<!-- AI-CONTEXT: Diesel-price contribution (M7-FR5, design-prd §10.1 / §11.7). A
     driver at the pump reports the per-gallon diesel price; 3 reports form a crowd
     consensus (F10) that displaces the EIA regional baseline on this station's pin.
     Money is Mono (§6.2 T-2), integer-cent discipline. Glove-friendly steppers +
     a big confirm (§6.5). Emits the price in CENTS/gal. Presence proof + points are
     enforced server-side (F10); this is the capture UI. -->
<script setup>
import { ref, computed } from "vue";
import { Minus, Plus } from "lucide-vue-next";
import { useI18n } from "../i18n.js";

const props = defineProps({
  // a sensible starting point (the current shown price, cents/gal) so the driver
  // nudges rather than types — defaults near a national average when unknown.
  startCents: { type: Number, default: 389 },
});
const emit = defineEmits(["submit"]);
const { t } = useI18n();

const MIN = 100; // $1.00 — floors below a plausible diesel price
const MAX = 999; // $9.99 — caps fat-finger entry
const cents = ref(Math.min(MAX, Math.max(MIN, Math.round(props.startCents))));
const dollars = computed(() => (cents.value / 100).toFixed(2));

function step(delta) {
  cents.value = Math.min(MAX, Math.max(MIN, cents.value + delta));
}
</script>

<template>
  <div class="price">
    <p class="price__q">{{ t("fuel.report.question") }}</p>
    <div class="price__row">
      <button
        type="button"
        class="price__step"
        :aria-label="t('fuel.report.decrease')"
        @click="step(-1)"
      >
        <Minus :size="24" :stroke-width="2.5" aria-hidden="true" />
      </button>
      <span class="price__figure">${{ dollars }}</span>
      <button
        type="button"
        class="price__step"
        :aria-label="t('fuel.report.increase')"
        @click="step(1)"
      >
        <Plus :size="24" :stroke-width="2.5" aria-hidden="true" />
      </button>
    </div>
    <span class="price__unit">{{ t("fuel.net") }}/gal</span>
    <button type="button" class="price__submit" @click="emit('submit', cents)">
      {{ t("fuel.report.submit") }}
    </button>
  </div>
</template>

<style scoped>
.price__q {
  margin: 0 0 var(--s-4);
  font-size: var(--type-body-size);
  color: var(--text-2);
}
.price__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-4);
}
.price__step {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: transparent;
  color: var(--text-1);
}
.price__figure {
  flex: 1;
  text-align: center;
  font-family: var(--font-mono);
  font-size: var(--type-display-size, var(--type-title-size));
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
.price__unit {
  display: block;
  margin-top: var(--s-2);
  text-align: center;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.price__submit {
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-4);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
</style>
