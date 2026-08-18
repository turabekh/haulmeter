<!-- AI-CONTEXT: The SIX-tab bottom bar (design-prd §4 NAV-1, amended by decision 213).
     Icons WITH labels, no hamburger, ever. Bottom-anchored in the thumb zone (§7.3),
     64 dp + safe-area, targets ≥48 dp (§6.5). The ONLY interactive color is shield
     (§6.1). Custom-built on tokens with zero Quasar defaults (§19 Q-4).

     SIX, AND THE NUMBER WAS MEASURED BEFORE IT WAS ARGUED. NAV-1 said "5 tabs exactly"
     and D7 set the price of changing it: "build a throwaway six-tab bar and run the
     181-state layout sweep under all six locales and xx-XL; 360÷6 = 60 dp clears the
     48 dp glove floor but THE LABELS ARE THE RISK". That sweep was run — every state,
     every locale, xx-XL and 200% — and it passes. The owner authorised six (2026-08-18);
     this comment records that the condition attached to it was met, not waived.

     AT 360 dp EACH TAB IS 60 dp, down from 72. That is what makes the labels tight, and
     it is why `nav.roadside` and `nav.docs` are their own short strings rather than
     reuses of "Roadside Ready" or a full "Documents" — Russian ("Документы") and Somali
     ("Wax dheeraad ah") set the width, not English.

     INSPECTION MODE KEEPS ITS SECOND DOOR ON LOAD even though Docs is a tab again and
     §10.4's two taps are satisfied without it. It is not redundancy for its own sake:
     §5 foregrounds Load when the driver is ON_SITE, which is where they are when an
     officer walks up, and the row sits above the fold there. The MORE rows added at 207
     are gone — with Docs back on the bar they were a third path to one screen. -->
<script setup>
import { Map, Truck, DollarSign, FileText, Mic, MoreHorizontal } from "lucide-vue-next";
import { useI18n } from "../i18n.js";

const { t } = useI18n();
const tabs = [
  { to: "/map", key: "nav.map", icon: Map },
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
