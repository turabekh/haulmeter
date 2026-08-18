<!-- AI-CONTEXT: The five-tab bottom bar (design-prd §4 NAV-1). Icons WITH labels,
     exactly 5 tabs, no hamburger, ever. Bottom-anchored in the thumb zone
     (§7.3), 64 dp + safe-area, targets ≥48 dp (§6.5). The ONLY interactive color
     is shield (§6.1). Custom-built on tokens with zero Quasar defaults (§19 Q-4).

     SLOT 4 IS ROADSIDE, NOT DOCS (decision 207). E3.1.6 said "no new bottom-nav tab"
     and D16 confirmed a More row; the owner reversed both. NAV-1 IS NOT REVERSED —
     staying at exactly 5 is what spared this change D7's mandatory six-tab measurement,
     and it is why Docs was displaced rather than added beside.

     THE WALLET DID NOT SIMPLY MOVE TO MORE. §10.4 requires inspection mode within 2 taps
     of a cold start, and More → Documents → Inspection is three. Inspection mode is
     therefore its own entry on Load (where a driver is when an officer arrives) and on
     More; the wallet itself is the More row. See `LoadSurface` and `MoreSurface`.

     THE LABEL IS THE CONSTRAINT HERE, not the icon. At 360 dp each tab is 72 dp, and
     `nav.roadside` has to fit beside "Документы" and "Wax dheeraad ah" — which is why it
     is its own short string rather than a reuse of `more.roadside` ("Roadside Ready"). -->
<script setup>
import { Map, Truck, DollarSign, Mic, MoreHorizontal } from "lucide-vue-next";
import { useI18n } from "../i18n.js";

const { t } = useI18n();
const tabs = [
  { to: "/map", key: "nav.map", icon: Map },
  { to: "/load", key: "nav.load", icon: Truck },
  { to: "/money", key: "nav.money", icon: DollarSign },
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
}
.tab--active {
  color: var(--shield-500);
}
</style>
