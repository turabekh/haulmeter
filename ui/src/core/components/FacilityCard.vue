<!-- AI-CONTEXT: Facility card content (design-prd §10.1) shown inside the pin
     bottom sheet. Glanceable: name + status pill + freshness (§11.7) + fuel
     figure (Mono, §6.2 T-2) + ONE primary action (§Principle 4) — Navigate,
     the external-nav deep-link handoff (M1-FR8, no in-house routing). -->
<script setup>
import { computed } from "vue";
import { Navigation } from "lucide-vue-next";
import StatusPill from "./StatusPill.vue";
import { freshnessLabel, isStale } from "../presentation.js";
import { useI18n } from "../i18n.js";

const props = defineProps({
  pin: { type: Object, required: true },
});
const emit = defineEmits(["navigate", "report"]);
const { t } = useI18n();

const now = Date.now();
const fresh = computed(() => freshnessLabel(props.pin.freshness, now));
const stale = computed(() => isStale(props.pin.freshness, now));
const fuel = computed(() => props.pin.badges?.find((b) => b.kind === "fuel_price")?.value ?? null);
</script>

<template>
  <div class="fac">
    <h3 class="fac__name">{{ pin.name }}</h3>
    <div class="fac__row">
      <StatusPill v-if="pin.status" :status="pin.status" :hollow="stale" />
      <span v-if="fresh" class="fac__fresh">{{ fresh }}</span>
    </div>
    <div v-if="fuel !== null" class="fac__fuel">
      <span class="fac__fuel-figure">${{ fuel.toFixed(2) }}</span>
      <span class="fac__fuel-label">{{ t("facility.fuel") }}</span>
    </div>
    <button class="cta" type="button" @click="emit('navigate', pin)">
      <Navigation :size="20" :stroke-width="2" aria-hidden="true" />
      {{ t("facility.navigate") }}
    </button>
    <button class="cta cta--secondary" type="button" @click="emit('report', pin)">
      {{ t("map.report") }}
    </button>
  </div>
</template>

<style scoped>
.fac__name {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.fac__row {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-2);
}
.fac__fresh {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.fac__fuel {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  margin-top: var(--s-3);
}
.fac__fuel-figure {
  font-family: var(--font-mono);
  font-size: var(--type-title-size);
  font-variant-numeric: tabular-nums;
}
.fac__fuel-label {
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-4);
  border-radius: var(--r-control);
  background: var(--shield-500);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta--secondary {
  margin-top: var(--s-2);
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
}
</style>
