<!-- AI-CONTEXT: Spot-handoff relay (M10-FR2, PRD §8.10) — the structural move
     incumbents can't copy. A driver leaving a FULL free lot broadcasts "leaving
     in X"; a nearby driver claims the spot instead of circling. This sheet is
     the claimable feed: open handoffs in range with how soon each opens; tap
     Claim and you're headed there (both earn points on your confirmed arrival).
     Live via api.js -> /community/handoff/nearby|claim; offline shows a sample.
     Minutes are computed client-side; time never localized (F15). -->
<script setup>
import { ref } from "vue";
import { Clock } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { claimHandoff } from "../api.js";

const props = defineProps({
  handoffs: { type: Array, default: () => [] },
});
const { t } = useI18n();
const claimed = ref({}); // handoff_id -> true once claimed

function minutesUntil(iso) {
  return Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 60000));
}

async function claim(h) {
  if (h.mine || claimed.value[h.handoff_id]) return;
  try {
    await claimHandoff(h.handoff_id);
  } catch {
    /* taken / offline — reflect claimed locally either way */
  }
  claimed.value = { ...claimed.value, [h.handoff_id]: true };
}
</script>

<template>
  <div class="relay">
    <ul v-if="handoffs.length" class="list">
      <li v-for="h in handoffs" :key="h.handoff_id" class="item">
        <div class="item__main">
          <span class="item__name">{{ h.facility_name }}</span>
          <span class="item__when">
            <Clock :size="14" :stroke-width="2" aria-hidden="true" />
            {{ t("handoff.leaving_in") }} {{ minutesUntil(h.leaving_at) }} min
          </span>
        </div>
        <span v-if="h.mine" class="tag">{{ t("handoff.mine") }}</span>
        <button
          v-else-if="claimed[h.handoff_id]"
          class="claim claim--done"
          type="button"
          disabled
        >
          {{ t("handoff.claimed") }}
        </button>
        <button v-else class="claim" type="button" @click="claim(h)">
          {{ t("handoff.claim") }}
        </button>
      </li>
    </ul>
    <p v-else class="muted">{{ t("handoff.empty") }}</p>
  </div>
</template>

<style scoped>
.relay {
  display: flex;
  flex-direction: column;
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  padding: var(--s-3) 0;
  border-bottom: 1px solid var(--line-1);
}
.item__main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.item__name {
  font-size: var(--type-body-size);
  color: var(--text-1);
  font-weight: 500;
}
.item__when {
  display: flex;
  align-items: center;
  gap: var(--s-1);
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
/* §6.5 glove spec — 44 is §11.2's map-pin number and has no standing in a sheet */
.claim {
  flex: none;
  min-height: 48px;
  padding: 0 var(--s-4);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.claim--done {
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--ledger-500);
}
.tag {
  flex: none;
  padding: 2px var(--s-2);
  border-radius: var(--r-pill);
  background: var(--ink-2, var(--line-1));
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.muted {
  margin: 0;
  padding: var(--s-3) 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
</style>
