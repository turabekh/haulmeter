<!-- AI-CONTEXT: Corridor mode (design-prd §11.4) — DRIVING replaces free-pan with a
     vertical "next facilities" card stack. 64 dp cards, Mono figures (miles,
     status), all taps deferred-safe (no flows open while moving; §11.4 / §13.4).
     Figures are tabular Mono (§6.2 T-2). -->
<script setup>
import StatusPill from "./StatusPill.vue";

const props = defineProps({
  entries: { type: Array, default: () => [] },
});

function miles(distanceM) {
  return (distanceM / 1609.344).toFixed(1);
}
</script>

<template>
  <ol class="corridor" aria-label="Facilities ahead">
    <li v-for="e in entries" :key="e.facility_id" class="corridor__card">
      <div class="corridor__main">
        <span class="corridor__name">{{ e.name }}</span>
        <StatusPill v-if="e.status" :status="e.status" />
      </div>
      <span class="corridor__miles">{{ miles(e.distance_m) }} mi</span>
    </li>
  </ol>
</template>

<style scoped>
.corridor {
  list-style: none;
  margin: 0;
  padding: var(--s-4);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.corridor__card {
  min-height: 64px;
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-3) var(--s-4);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
}
.corridor__main {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  flex: 1 1 auto;
  min-width: 0;
}
.corridor__name {
  font-size: var(--type-body-size);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.corridor__miles {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
  color: var(--text-1);
}
</style>
