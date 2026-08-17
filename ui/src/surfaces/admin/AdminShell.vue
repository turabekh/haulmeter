<!-- AI-CONTEXT: Admin Console 2.0 shell (design-prd §18, §23 E-D4). The fourth
     portal's chrome: a persistent section rail plus <router-view>.

     Sections are ROUTER CHILDREN, not internal tabs, for three reasons an operator
     feels: a moderation queue can be bookmarked and shared, browser back behaves,
     and each section fetches only its own data — the old single page Promise.all'd
     five endpoints on mount and would have grown slower with every section added.

     NAV-1 (five tabs, no drawers) governs the DRIVER app; a portal rail is not a
     driver-app drawer, so there is no conflict. §18 is silent on portal navigation,
     which is why this structure is logged as E-D4 rather than improvised.

     ≥900 dp the rail sits left; below that it becomes a horizontal scrolling strip —
     the same pattern as the driver app's preset chips, so no new component pattern
     is invented for a narrow viewport. -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import { fetchAdminOverview } from "../../core/api.js";

const { t } = useI18n();
const denied = ref(false);
const pending = ref(null);

// counts ride on the rail so an operator sees where the work is before choosing a
// section. Only sections with genuine pending work carry a badge — a "0" badge on
// every item is decoration, and §21.3 has no patience for decoration.
const SECTIONS = [
  { key: "overview", to: "/admin", label: "admin.nav.overview" },
  { key: "flags", to: "/admin/flags", label: "admin.nav.flags" },
  { key: "vendors", to: "/admin/vendors", label: "admin.nav.vendors", count: "vendor_verification" },
  { key: "moderation", to: "/admin/moderation", label: "admin.nav.moderation", count: "moderation" },
  { key: "accounts", to: "/admin/accounts", label: "admin.nav.accounts" },
  { key: "data", to: "/admin/data", label: "admin.nav.data" },
  { key: "modules", to: "/admin/modules", label: "admin.nav.modules" },
  { key: "roadside", to: "/admin/roadside", label: "admin.nav.roadside" },
  { key: "audit", to: "/admin/audit", label: "admin.nav.audit" },
];

const overdue = computed(() => pending.value?.moderation_overdue ?? 0);

function badge(section) {
  const n = section.count ? (pending.value?.[section.count] ?? 0) : 0;
  return n > 0 ? n : null;
}

onMounted(async () => {
  try {
    pending.value = (await fetchAdminOverview()).pending;
  } catch {
    denied.value = true; // 403 (not a platform admin) or offline
  }
});
</script>

<template>
  <div class="console">
    <h1 class="console__title">{{ t("admin.title") }}</h1>
    <p v-if="denied" class="console__denied">{{ t("admin.no_access") }}</p>

    <div v-else class="console__body">
      <nav class="rail" :aria-label="t('admin.title')">
        <router-link
          v-for="s in SECTIONS"
          :key="s.key"
          :to="s.to"
          class="rail__item"
          active-class="rail__item--on"
          :exact="s.to === '/admin'"
        >
          <span class="rail__label">{{ t(s.label) }}</span>
          <!-- overdue is the one count that changes colour: it is the number that
               should make an operator act first (Q-8's SLA made visible) -->
          <span
            v-if="badge(s)"
            class="rail__badge"
            :class="{ 'rail__badge--late': s.key === 'moderation' && overdue > 0 }"
          >{{ badge(s) }}</span>
        </router-link>
      </nav>

      <main class="console__main">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
/* §18: desktop-first, comfortable density, 1200 dp cap, tokens only */
.console {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--s-5) var(--s-4);
}
.console__title {
  margin: 0 0 var(--s-4);
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
.console__denied {
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.console__body {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
/* narrow: a horizontal scrolling strip, the same shape as the driver app's preset
   chips — a pattern the codebase already has rather than a new one */
.rail {
  display: flex;
  gap: var(--s-2);
  overflow-x: auto;
  scrollbar-width: none;
}
.rail::-webkit-scrollbar {
  display: none;
}
.rail__item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex: 0 0 auto;
  min-height: 48px;
  padding: 0 var(--s-3);
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  color: var(--text-2);
  font-size: var(--type-label-size);
  text-decoration: none;
}
.rail__item--on {
  border-color: var(--shield-500);
  color: var(--shield-500);
}
.rail__badge {
  padding: 0 var(--s-2);
  border-radius: var(--r-pill);
  background: var(--ink-2, var(--line-1));
  color: var(--text-2);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-caption-size);
}
.rail__badge--late {
  background: var(--flare-500);
  color: var(--on-accent);
}
.console__main {
  min-width: 0;
}
/* §18 desktop: the rail moves left and stays put while a section scrolls */
@media (min-width: 900px) {
  .console__body {
    flex-direction: row;
    align-items: flex-start;
  }
  .rail {
    flex-direction: column;
    flex: 0 0 220px;
    position: sticky;
    top: var(--s-4);
    overflow-x: visible;
  }
  .rail__item {
    justify-content: space-between;
  }
  .console__main {
    flex: 1 1 auto;
  }
}
</style>
