<!-- AI-CONTEXT: The FIVE-tab bottom bar (design-prd §4 NAV-1; owner decision D21,
     §23 entry 228 — which supersedes decision 213 IN PART).
     Icons WITH labels, no hamburger, ever. Bottom-anchored in the thumb zone (§7.3),
     64 dp + safe-area, targets ≥48 dp (§6.5). The ONLY interactive color is shield
     (§6.1). Custom-built on tokens with zero Quasar defaults (§19 Q-4).

     THE MAP SLOT IS GONE, AND THE SWEEP THAT ALLOWED SIX STILL COVERS FIVE. D7 priced
     the sixth tab — "build a throwaway six-tab bar and run the 181-state layout sweep
     under all six locales and xx-XL; 360÷6 = 60 dp clears the 48 dp glove floor but THE
     LABELS ARE THE RISK" — and that sweep was run and passed at SIX. Five tabs at 72 dp
     is strictly easier than six at 60, so this configuration is covered a fortiori and a
     fresh full sweep is not owed. **A SEVENTH TAB, OR ANY RETURN TO SIX, OWES THE
     MEASUREMENT AGAIN**: the amendment is to the number, never to the discipline.

     WHY FIVE AND NOT "BACK TO FIVE": this is not a revert. NAV-1's original five were
     Map · Load · Money · Docs · More. These five are Load · Money · Docs · Roadside ·
     More — the map is dormant (D21) and Roadside holds the slot it opened at 207.

     THE MAP IS DORMANT, NOT DELETED. `MapSurface` and its tests are still in the tree and
     still green; the route redirects behind `MAP_DORMANT` in `router.js`, which mirrors
     the `m01_map` flag. Reactivation puts this entry back beside those two switches. -->
<script setup>
import { Truck, DollarSign, FileText, Mic, MoreHorizontal } from "lucide-vue-next";
import { useI18n } from "../i18n.js";

const { t } = useI18n();
const tabs = [
  { to: "/load", key: "nav.load", icon: Truck },
  { to: "/money", key: "nav.money", icon: DollarSign },
  { to: "/docs", key: "nav.docs", icon: FileText },
  { to: "/roadside", key: "nav.roadside", icon: Mic },
  { to: "/more", key: "nav.more", icon: MoreHorizontal },
];
</script>

<template>
  <nav class="tabbar" aria-label="Primary">
    <router-link
      v-for="tab in tabs"
      :key="tab.to"
      :to="tab.to"
      class="tab"
      active-class="tab--active"
    >
      <component :is="tab.icon" :size="24" :stroke-width="2" aria-hidden="true" />
      <span class="tab__label">{{ t(tab.key) }}</span>
    </router-link>
  </nav>
</template>

<style scoped>
.tabbar {
  display: flex;
  border-top: 1px solid var(--line-1);
  background: var(--ink-1);
  padding-bottom: env(safe-area-inset-bottom, 0);
}
.tab {
  flex: 1 1 0;
  /* AI-CONTEXT: `min-width: 0` is what makes six tabs fit, and it is not cosmetic.
     A flex item defaults to `min-width: auto`, which means it REFUSES to shrink below its
     content — so a `nowrap` label set a floor and the bar ran past 360 dp at 200% text
     scaling. Every 200% state in the sweep failed on it, in every locale. T-5 requires
     layouts to reflow to 200% rather than clip, and this one line is the difference.
     Found by D7's mandatory six-tab measurement, which is exactly what it was for. */
  min-width: 0;
  min-height: 64px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--s-1);
  text-decoration: none;
  color: var(--text-3);
  padding: var(--s-2) 0;
}
.tab__label {
  font-size: var(--type-caption-size);
  line-height: var(--type-caption-line);
  font-weight: 500;
  /* AI-CONTEXT: at 60 dp a cell has no slack. The label gets the full width minus a
     hairline and is allowed to ellipsize rather than push the bar wider — T-6 forbids
     truncating MONEY, TIME or STATUS, and a tab label is none of those; the icon above it
     carries the meaning either way (§6.6 pairs them deliberately). */
  max-width: 100%;
  padding: 0 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tab--active {
  color: var(--shield-500);
}
</style>
