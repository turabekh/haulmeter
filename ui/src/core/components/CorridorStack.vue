<!-- AI-CONTEXT: Corridor mode (design-prd §11.4) — DRIVING replaces free-pan with a
     vertical "next facilities" card stack. 64 dp cards, Mono figures (miles,
     status), all taps deferred-safe (no flows open while moving; §11.4 / §13.4).
     Figures are tabular Mono (§6.2 T-2). -->
<script setup>
import { computed } from "vue";
import { UtensilsCrossed, Scale, Bookmark } from "lucide-vue-next";
import StatusPill from "./StatusPill.vue";
import { corridorVendors, untilLabel } from "../vendors.js";
import { formatMiles } from "../presentation.js";
import { formatMoney } from "../meter.js";
import { useI18n } from "../i18n.js";

const props = defineProps({
  entries: { type: Array, default: () => [] },
  // M13-FR3: food ahead on this heading. Q-6 caps it at three per session; DRIVING
  // means this renders as a READ-ONLY line — no interactive prompt while moving
  // (§13.4 / Forbidden #11). Confirming waits for the next stop.
  vendors: { type: Array, default: () => [] },
  // E3.1: weigh stations on this heading, server-capped at two. This is the one thing
  // in the stack a driver must decide about BEFORE arriving, so it leads — but like
  // every corridor line it is READ-ONLY while moving (§13.4 / Forbidden #11); the
  // report affordance waits for the next stop.
  scales: { type: Array, default: () => [] },
  // §11.4's saved set, passed in rather than read from the store so the component
  // stays a pure render of what it is handed (and testable without localStorage)
  savedIds: { type: Array, default: () => [] },
});
const emit = defineEmits(["save"]);
const { t } = useI18n();
const isSaved = (id) => props.savedIds.some((x) => String(x) === String(id));
const foodAhead = computed(() => corridorVendors(props.vendors));

// both precisions come from the shared formatter — see presentation.js for why a
// corridor distance carries a decimal and a direct map distance does not
const milesAhead = (distanceM) => formatMiles(distanceM);
const miles = (distanceM) => formatMiles(distanceM, { precise: true });

// §11.4's third figure. The badge is the SAME one the pin behind this card carries —
// one price for one pump, whichever screen the driver happens to be reading. An
// indicative figure keeps its tilde here exactly as it does on the facility card:
// a regional estimate must not harden into a quote just because it is in Mono.
function price(entry) {
  const badge = entry.badges?.find((b) => b.kind === "fuel_net");
  if (!badge) return null;
  return `${badge.indicative ? "~" : ""}${formatMoney(badge.net)}`;
}
</script>

<template>
  <ol class="corridor" aria-label="Facilities ahead">
    <!-- scales lead: a scale is the only line here with a deadline attached to it -->
    <li v-for="s in scales" :key="s.facility_id" class="corridor__card corridor__card--scale">
      <div class="corridor__main">
        <div class="corridor__head">
          <Scale :size="18" :stroke-width="2" aria-hidden="true" />
          <span class="corridor__name">{{ s.name }}</span>
        </div>
        <!-- §11.7: an unreported scale says so rather than implying it is shut -->
        <StatusPill v-if="s.status" :status="s.status" />
        <span v-else class="corridor__unknown">{{ t("facility.no_report") }}</span>
      </div>
      <span class="corridor__miles">{{ miles(s.distance_m) }} mi</span>
    </li>
    <!-- AI-CONTEXT: these were a FIXTURE until §23 entry 81 — three invented
         facilities carrying invented statuses, rendered in the one state a driver
         cannot check anything. They now come from `GET /map/corridor`, which means
         the two rows below can finally be true: a status nobody has reported says so
         (§11.7) instead of being silently absent, and §11.4's third figure — the
         price — renders for a station that has one. -->
    <!-- AI-CONTEXT: §11.4's DEFERRED-SAFE TAP, which had nothing behind it — these
         were `<li>` elements, so the clause was vacuously satisfied by there being no
         taps at all. A tap here opens NOTHING: it saves the facility and marks itself,
         which is precisely "queue 'save for stop' instead of opening flows".
         · One tap, no confirm, no sheet, no toast — Forbidden #11 bans interactive
           prompts at speed, and a prompt is exactly what a confirmation would be.
         · `saveForStop` is idempotent, so a gloved double-tap is one intention and
           cannot toggle the row back off unnoticed.
         · The whole 64 dp card is the target (§5 grows primary cards to 64 dp while
           DRIVING), because aiming at anything smaller in a moving truck is a fiction.
         The list stays an `<ol>`: it is still an ordered set of things ahead, and
         nesting a button in each `<li>` keeps that meaning while adding the action. -->
    <li v-for="e in entries" :key="e.facility_id" class="corridor__card">
      <button
        class="corridor__tap"
        type="button"
        :aria-pressed="isSaved(e.facility_id)"
        :aria-label="`${e.name} — ${t('saved.mark')}`"
        @click="emit('save', e)"
      >
        <div class="corridor__main">
          <span class="corridor__name">{{ e.name }}</span>
          <StatusPill v-if="e.status" :status="e.status" />
          <span v-else class="corridor__unknown">{{ t("facility.no_report") }}</span>
        </div>
        <span class="corridor__figures">
          <span class="corridor__miles">{{ miles(e.distance_m) }} mi</span>
          <span v-if="price(e)" class="corridor__price">{{ price(e) }}</span>
        </span>
        <!-- icon AND the token, never colour alone (C-1) -->
        <Bookmark
          v-if="isSaved(e.facility_id)"
          :size="18"
          :stroke-width="2.5"
          class="corridor__saved"
          aria-hidden="true"
        />
      </button>
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
/* the whole card is the target. §5 grows primary cards to 64 dp while DRIVING and the
   card is already 64; this makes that height mean something by putting the action on
   all of it. Transparent and borderless — the `li` carries the card surface, so the
   button adds a target without adding a second visual box (§8). */
.corridor__tap {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  width: 100%;
  min-height: 64px;
  padding: 0;
  background: none;
  border: 0;
  text-align: left;
  color: inherit;
  cursor: pointer;
}
.corridor__saved {
  flex: none;
  color: var(--shield-500);
}
.corridor__main {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  flex: 1 1 auto;
  min-width: 0;
}
/* scoped to the scale line: the existing entries' pill stretch is left as it is
   rather than restyled in passing */
.corridor__card--scale .corridor__main {
  align-items: flex-start;
}
.corridor__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  max-width: 100%;
}
.corridor__unknown {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.corridor__name {
  font-size: var(--type-body-size);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* miles lead and the price sits under them: distance is what decides whether a
   facility is reachable at all, and §12.2 puts the deciding figure first. Both are
   tabular Mono (T-2), right-aligned so a stack of three scans as a column. */
.corridor__figures {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--s-1);
  flex: none;
}
.corridor__miles {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
  color: var(--text-1);
}
.corridor__price {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  color: var(--text-2);
}
</style>
