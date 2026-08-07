<!-- AI-CONTEXT: Bottom sheet (design-prd §8, NAV-3) — the workhorse for secondary
     tasks. ink-2 surface, top radius, grab handle (≥32 dp hit), dim scrim 40%.
     Sheets stack max 1 deep. Android back closes it (handled by the host).
     Gestures have a visible close button (§6.5). -->
<script setup>
import { X } from "lucide-vue-next";

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: "" },
  // keep `title` as the dialog's accessible name but don't render it visibly —
  // for sheets whose content already shows the heading (e.g. FacilityCard)
  hideTitle: { type: Boolean, default: false },
});
const emit = defineEmits(["close"]);
</script>

<template>
  <div v-if="open" class="sheet-root">
    <div class="scrim" @click="emit('close')" />
    <section class="sheet" role="dialog" aria-modal="true" :aria-label="title">
      <div class="grab" />
      <div class="sheet__head">
        <h2 v-if="title && !hideTitle" class="sheet__title">{{ title }}</h2>
        <button class="sheet__close" type="button" aria-label="Close" @click="emit('close')">
          <X :size="24" :stroke-width="2" aria-hidden="true" />
        </button>
      </div>
      <div class="sheet__body">
        <slot />
      </div>
    </section>
  </div>
</template>

<style scoped>
.sheet-root {
  position: fixed;
  inset: 0;
  z-index: 20;
}
.scrim {
  position: absolute;
  inset: 0;
  background: var(--scrim);
}
.sheet {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  max-width: 480px;
  margin: 0 auto;
  background: var(--ink-2);
  border-top-left-radius: var(--r-sheet);
  border-top-right-radius: var(--r-sheet);
  padding: var(--s-2) var(--s-4) calc(var(--s-4) + env(safe-area-inset-bottom, 0));
  max-height: 90%;
  overflow-y: auto;
}
.grab {
  width: 40px;
  height: 4px;
  border-radius: var(--r-pill);
  background: var(--line-1);
  margin: var(--s-2) auto var(--s-3);
}
.sheet__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}
.sheet__title {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.sheet__close {
  margin-left: auto;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-2);
}
.sheet__body {
  margin-top: var(--s-3);
}
</style>
