<!-- AI-CONTEXT: Placeholder for the Load/Money/Docs/More tabs whose content is
     built with their modules (M3/M4/M5, M9, M10/M12). Keeps the five-tab shell
     whole and navigable this session. Calm empty state (§15.3): one line of
     what this is — never scolds, never fakes content. -->
<script setup>
import { useI18n } from "../core/i18n.js";

defineProps({
  titleKey: { type: String, required: true },
});
const { t } = useI18n();
</script>

<template>
  <div class="placeholder">
    <h1 class="placeholder__title">{{ t(titleKey) }}</h1>
    <p class="placeholder__note">{{ t("surface.placeholder") }}</p>
  </div>
</template>

<style scoped>
.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: var(--s-6) var(--s-4);
  text-align: center;
}
.placeholder__title {
  margin: 0;
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
.placeholder__note {
  margin-top: var(--s-3);
  color: var(--text-2);
  font-size: var(--type-body-size);
}
</style>
