<!-- AI-CONTEXT: Corridor mode (design-prd §11.4) — DRIVING replaces free-pan with a
     vertical "next facilities" card stack. 64 dp cards, Mono figures (miles,
     status), all taps deferred-safe (no flows open while moving; §11.4 / §13.4).
     Figures are tabular Mono (§6.2 T-2). -->
<script setup>
import { computed } from "vue";
import { UtensilsCrossed } from "lucide-vue-next";
import StatusPill from "./StatusPill.vue";
import { corridorVendors, untilLabel } from "../vendors.js";
import { useI18n } from "../i18n.js";

const props = defineProps({
  entries: { type: Array, default: () => [] },
  // M13-FR3: food ahead on this heading. Q-6 caps it at three per session; DRIVING
  // means this renders as a READ-ONLY line — no interactive prompt while moving
  // (§13.4 / Forbidden #11). Confirming waits for the next stop.
  vendors: { type: Array, default: () => [] },
});
const { t } = useI18n();
const foodAhead = computed(() => corridorVendors(props.vendors));

function milesAhead(distanceM) {
  return (distanceM / 1609.344).toFixed(0);
}

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
    <!-- food ahead: one line each, figure first (§12.2), no tap target (§11.4 —
         taps in corridor mode are deferred-safe, and this one has nothing to defer) -->
    <li v-for="v in foodAhead" :key="v.vendor_id" class="corridor__card corridor__card--food">
      <div class="corridor__main">
        <UtensilsCrossed :size="18" :stroke-width="2" aria-hidden="true" />
        <span class="corridor__name">{{ v.name }}</span>
      </div>
      <span class="corridor__miles">
        <template v-if="v.distance_m !== null">{{ milesAhead(v.distance_m) }} mi · </template>
        {{ t("vendor.until") }} {{ untilLabel(v.ends_at) }}
      </span>
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
/* food lines share the 64 dp card rhythm but read as secondary — the corridor's
   job is parking and fuel; a meal is a bonus, never the headline (§2 principle 1) */
.corridor__card--food {
  color: var(--text-2);
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
