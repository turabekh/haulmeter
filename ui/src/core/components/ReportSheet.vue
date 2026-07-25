<!-- AI-CONTEXT: One-tap crowd-status contribution (M1-FR7, design-prd §10.1
     report chip). Big glove-friendly targets (§6.5), one decision per step (S2
     dock task). Geofence-presence proof + points are enforced server-side (F10);
     this is the capture UI. Emits the chosen status.

     The vocabulary is a PROP, not a constant: E3.1 asks a weigh station whether it
     is open, and asking it how full its parking is would collect a reading that
     means nothing about it. Callers get their option set from
     `presentation.statusReportFor(facilityType)` so the question, the buttons and
     the signal posted to F10 can never drift apart. -->
<script setup>
import { computed } from "vue";
import { useI18n } from "../i18n.js";
import { statusReportFor } from "../presentation.js";

const props = defineProps({
  facilityType: { type: String, default: null },
});
const emit = defineEmits(["report"]);
const { t } = useI18n();
// computed, not read once: the sheet outlives a single target, so a driver who
// reports a scale and then a truck stop must not be shown the scale's question
const spec = computed(() => statusReportFor(props.facilityType));
const options = computed(() => spec.value.options);
</script>

<template>
  <div class="report">
    <p class="report__q">{{ t(spec.questionKey) }}</p>
    <button
      v-for="o in options"
      :key="o.status"
      type="button"
      class="report__opt"
      :style="{ '--opt-color': `var(${o.token})` }"
      @click="emit('report', o.status)"
    >
      {{ t(`map.status.${o.status}`) }}
    </button>
  </div>
</template>

<style scoped>
.report__q {
  margin: 0 0 var(--s-3);
  font-size: var(--type-body-size);
  color: var(--text-2);
}
.report__opt {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 64px;
  margin-bottom: var(--s-2);
  padding: 0 var(--s-4);
  border-radius: var(--r-control);
  border: 1px solid var(--opt-color);
  color: var(--opt-color);
  background: transparent;
  font-size: var(--type-title-size);
  font-weight: 500;
}
</style>
