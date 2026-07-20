<!-- AI-CONTEXT: THE METER (design-prd §9) — the product's one memorable visual:
     the counting figure that means "your time is being measured, and it's worth
     money." The ONLY animated, ONLY Mono-set, hero element; nothing else on a
     screen competes with it. Composition: label above · type-meter Mono figure
     (fixed-width, tabular — the layout never breathes) · status pill below.
     Color by variant (§9). Built once here on tokens (Q-4). -->
<script setup>
import { computed } from "vue";
import { METER_VARIANT_TOKEN } from "../meter.js";

const props = defineProps({
  label: { type: String, required: true },
  figure: { type: String, required: true },
  variant: { type: String, default: "countdown" }, // countdown | warning | accruing | disputed
  status: { type: String, default: "" },
});

const color = computed(() => `var(${METER_VARIANT_TOKEN[props.variant] ?? "--text-1"})`);
</script>

<template>
  <div class="meter" role="group" :aria-label="label">
    <div class="meter__label">{{ label }}</div>
    <div class="meter__figure" :style="{ color }" aria-live="polite">{{ figure }}</div>
    <div v-if="status" class="meter__status" :style="{ color }">{{ status }}</div>
  </div>
</template>

<style scoped>
.meter {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-1);
  padding: var(--s-4) 0;
}
.meter__label {
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  color: var(--text-2);
}
.meter__figure {
  font-family: var(--font-mono);
  font-size: var(--type-meter-size);
  line-height: var(--type-meter-line);
  font-weight: var(--type-meter-weight);
  font-variant-numeric: tabular-nums;
}
.meter__status {
  font-size: var(--type-label-size);
  font-weight: 500;
}
</style>
