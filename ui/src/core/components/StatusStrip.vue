<!-- AI-CONTEXT: Top context strip (design-prd §7.2) — read-only state + connectivity
     plus the persistent voice mic (§14.2, 48 dp). Nothing else interactive in the
     top zone (§7.3). Offline is a calm banner, never red (§15.1). -->
<script setup>
import { computed } from "vue";
import { Mic, WifiOff, CloudOff } from "lucide-vue-next";
import { useDriverState } from "../state.js";
import { useI18n } from "../i18n.js";

const props = defineProps({
  online: { type: Boolean, default: true },
  pending: { type: Number, default: 0 },
});
const { state } = useDriverState();
const { t } = useI18n();
const stateLabel = computed(() => state.value);
</script>

<template>
  <header class="strip">
    <span class="strip__state">{{ stateLabel }}</span>
    <span v-if="!online" class="strip__offline">
      <WifiOff :size="16" :stroke-width="2" aria-hidden="true" />
      {{ t("system.offline") }}
    </span>
    <!-- F12: queued captures show a subtle pending glyph (§15.1) -->
    <span v-if="pending > 0" class="strip__pending" :aria-label="t('system.pending')">
      <CloudOff :size="14" :stroke-width="2" aria-hidden="true" />
      {{ pending }}
    </span>
    <button class="strip__mic" type="button" aria-label="Voice">
      <Mic :size="20" :stroke-width="2" aria-hidden="true" />
    </button>
  </header>
</template>

<style scoped>
.strip {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 32px;
  padding: var(--s-1) var(--s-4);
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.strip__state {
  text-transform: capitalize;
}
.strip__offline {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  color: var(--text-2);
}
.strip__pending {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
}
.strip__mic {
  margin-left: auto;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--shield-500);
}
</style>
