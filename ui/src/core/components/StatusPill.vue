<!-- AI-CONTEXT: Status pill (design-prd §8) — the ONLY colored-background chip in
     the system. Color NEVER carries meaning alone: always paired with a label,
     and an icon where supplied (C-1, colorblind-safe). Semantic token via prop. -->
<script setup>
import { computed } from "vue";
import { statusPresentation } from "../presentation.js";
import { useI18n } from "../i18n.js";

const props = defineProps({
  status: { type: String, default: null },
  hollow: { type: Boolean, default: false },
});
const { t } = useI18n();
const p = computed(() => statusPresentation(props.status));
// the label is what makes the color legible to a colorblind driver (C-1), so it has
// to survive translation — a pill that reads "Closed" to a Punjabi speaker is a pill
// that only carries color. `label` stays as the fallback for a missing key.
const label = computed(() => (p.value.labelKey ? t(p.value.labelKey) : p.value.label));
</script>

<template>
  <span
    class="pill"
    :class="{ 'pill--hollow': hollow }"
    :style="{ '--pill-color': `var(${p.token})` }"
  >
    {{ label }}
  </span>
</template>

<style scoped>
.pill {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  padding: 2px var(--s-2);
  border-radius: var(--r-pill);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  font-weight: 500;
  color: var(--ink-0);
  background: var(--pill-color);
}
/* §11.7: stale statuses hollow their fill — never fake confidence */
.pill--hollow {
  color: var(--pill-color);
  background: transparent;
  border: 1px solid var(--pill-color);
}
</style>
