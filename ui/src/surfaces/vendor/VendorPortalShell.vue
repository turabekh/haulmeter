<!-- AI-CONTEXT: the vendor portal's chrome (design-prd §18, §23 E-D3 + the rail
     decision). Six sections as ROUTER CHILDREN under /vendor-portal/*.

     The rail is NOT invented here — it is the pattern approved for the admin console
     (§23 E-D4), reused for the same portal family: ≥900 dp it sits left, below that
     it becomes a horizontal scrolling strip shaped like the driver app's preset
     chips. §22.2 makes navigation structure a never-improvise category, and reusing
     an approved structure is how that rule is satisfied rather than sidestepped.

     Children rather than internal tabs, for the reason the console had: each section
     fetches only its own data. The old single page Promise.all'd four endpoints on
     mount and would have loaded six once the menu and reputation arrived.

     Two things live in the SHELL because a cook must not have to go looking for
     them: the impersonation banner, and a publish suspension. -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { TriangleAlert } from "lucide-vue-next";
import { useI18n } from "../../core/i18n.js";
import {
  impersonation,
  setImpersonation,
  endImpersonation,
  fetchVendorProfile,
} from "../../core/api.js";

const { t } = useI18n();
const denied = ref(false);
const profile = ref(null);

const SECTIONS = [
  { key: "overview", to: "/vendor-portal", label: "vendor.nav.overview" },
  { key: "week", to: "/vendor-portal/week", label: "vendor.nav.week" },
  { key: "menu", to: "/vendor-portal/menu", label: "vendor.nav.menu" },
  { key: "promotions", to: "/vendor-portal/promotions", label: "vendor.nav.promotions" },
  { key: "verification", to: "/vendor-portal/verification", label: "vendor.nav.verification" },
  { key: "reputation", to: "/vendor-portal/reputation", label: "vendor.nav.reputation" },
];

const suspended = computed(() => profile.value?.publish_suspended === true);
const gaps = computed(() => profile.value?.profile_gaps ?? []);
// E-D5: an impersonating admin must never forget whose screen they are on
const viewingAs = computed(() => impersonation.value);

async function exitViewAs() {
  const held = impersonation.value;
  setImpersonation(null);
  if (held?.token) await endImpersonation(held.token).catch(() => {});
  window.location.reload();
}

onMounted(async () => {
  try {
    profile.value = await fetchVendorProfile();
  } catch {
    denied.value = true; // not a vendor, module flag off, or offline
  }
});
</script>

<template>
  <div class="portal">
    <div v-if="viewingAs" class="viewas" role="status">
      <span class="viewas__text">
        {{ t("admin.imp.banner") }} <strong>{{ viewingAs.vendor_name }}</strong>.
        {{ t("admin.imp.writes") }}
      </span>
      <button class="viewas__exit" type="button" @click="exitViewAs">
        {{ t("admin.imp.exit") }}
      </button>
    </div>

    <header class="portal__head">
      <h1 class="portal__title">{{ t("portal.vendor.title") }}</h1>
      <p v-if="profile" class="portal__who">
        {{ profile.name }} · {{ t(`vendor.${profile.verify_status}`) }}
      </p>
    </header>

    <p v-if="denied" class="portal__denied">{{ t("portal.vendor.no_access") }}</p>

    <template v-else>
      <!-- said first and plainly, in the shell, so it cannot be missed by being on
           another section: a vendor should never discover a suspension by having a
           publish fail -->
      <p v-if="suspended" class="portal__alert" role="alert">
        <TriangleAlert :size="18" :stroke-width="2" aria-hidden="true" />
        {{ t("portal.vendor.suspended") }}
      </p>
      <!-- and the Q-4 floor, named, wherever they are standing -->
      <p v-else-if="gaps.length" class="portal__gaps">
        {{ t("portal.vendor.gaps") }}:
        {{ gaps.map((g) => t(`vendor.gap.${g}`)).join(", ") }}
      </p>

      <div class="portal__body">
        <nav class="rail" :aria-label="t('portal.vendor.title')">
          <router-link
            v-for="s in SECTIONS"
            :key="s.key"
            :to="s.to"
            class="rail__item"
            active-class="rail__item--on"
          >
            {{ t(s.label) }}
          </router-link>
        </nav>
        <main class="portal__main">
          <router-view />
        </main>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* §18: desktop-first, comfortable density, 1200 dp cap, tokens only */
.portal {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--s-5) var(--s-4);
}
.portal__title {
  margin: 0;
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
.portal__who {
  margin: var(--s-1) 0 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.portal__head {
  margin-bottom: var(--s-4);
}
.portal__denied {
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.portal__alert {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0 0 var(--s-4);
  padding: var(--s-3);
  border: 1px solid var(--flare-500);
  border-radius: var(--r-control);
  color: var(--flare-500);
  font-size: var(--type-body-size);
}
.portal__gaps {
  margin: 0 0 var(--s-4);
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.viewas {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  margin-bottom: var(--s-4);
  padding: var(--s-3);
  border-radius: var(--r-control);
  background: var(--marker-500);
  color: var(--ink-0);
  font-size: var(--type-label-size);
}
.viewas__text {
  flex: 1 1 auto;
}
.viewas__exit {
  min-height: 40px;
  padding: 0 var(--s-3);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-label-size);
}
.portal__body {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
/* narrow: the same horizontal strip the console uses — a pattern the codebase
   already has rather than a new one */
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
.portal__main {
  min-width: 0;
}
@media (min-width: 900px) {
  .portal__body {
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
  .portal__main {
    flex: 1 1 auto;
  }
}
</style>
