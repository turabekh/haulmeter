<!-- AI-CONTEXT: One-tap parking-status contribution (M1-FR7, design-prd §10.1
     report chip). Big glove-friendly targets (§6.5), one decision per step (S2
     dock task). Geofence-presence proof + points are enforced server-side (F10);
     this is the capture UI. Emits the chosen status. -->
<script setup>
import { useI18n } from "../i18n.js";

const emit = defineEmits(["report"]);
const { t } = useI18n();
const options = [
  { status: "empty", token: "--ledger-500" },
  { status: "some", token: "--marker-500" },
  { status: "full", token: "--flare-500" },
];
</script>

<template>
  <div class="report">
    <p class="report__q">{{ t("map.report.question") }}</p>
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
