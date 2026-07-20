<!-- AI-CONTEXT: Map presets (design-prd §11.3) — presets ARE the interface, not
     filters. Scrollable chip row at the top of the Map surface. One "More
     filters" sheet exists elsewhere; these four are the interface. -->
<script setup>
import { useI18n } from "../i18n.js";

const props = defineProps({
  modelValue: { type: String, default: "drive" },
});
const emit = defineEmits(["update:modelValue"]);
const { t } = useI18n();
const presets = [
  { key: "drive", label: "map.preset.drive" },
  { key: "tonight", label: "map.preset.tonight" },
  { key: "work", label: "map.preset.work" },
  { key: "fuel", label: "map.preset.fuel" },
];
</script>

<template>
  <div class="chips" role="tablist" aria-label="Map presets">
    <button
      v-for="p in presets"
      :key="p.key"
      type="button"
      class="chip"
      :class="{ 'chip--active': modelValue === p.key }"
      role="tab"
      :aria-selected="modelValue === p.key"
      @click="emit('update:modelValue', p.key)"
    >
      {{ t(p.label) }}
    </button>
  </div>
</template>

<style scoped>
.chips {
  display: flex;
  gap: var(--s-2);
  overflow-x: auto;
  padding: var(--s-2) var(--s-4);
  scrollbar-width: none;
}
.chips::-webkit-scrollbar {
  display: none;
}
.chip {
  flex: 0 0 auto;
  min-height: 40px;
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  color: var(--text-2);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.chip--active {
  border-color: var(--shield-500);
  color: var(--shield-500);
}
</style>
