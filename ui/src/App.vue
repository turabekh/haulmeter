<!-- AI-CONTEXT: App scaffold (design-prd §7.2). Top→bottom: status strip →
     content scroll region → persistent five-tab bar. Content never hides under
     the tab bar. Centered ≤480 dp column so wide viewports don't stretch the
     driver app (§7.1). Mobile-first 360×800 baseline. The chrome (status strip +
     tab bar) is suppressed on full-screen flows like login (route.meta.chrome). -->
<script setup>
import { computed, onMounted, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import StatusStrip from "./core/components/StatusStrip.vue";
import TabBar from "./core/components/TabBar.vue";
import { online, pendingWrites, failedWrites, flushQueue, isAuthenticated } from "./core/api.js";
import { syncLocale } from "./core/i18n.js";
import { startLocationReporting, stopLocationReporting } from "./core/location.js";

const route = useRoute();
const router = useRouter();
const chrome = computed(() => route.meta.chrome !== false);
const portal = computed(() => route.meta.portal === true);

// F12: reflect the browser's own connectivity, and drain the write-queue on reconnect
function setOnline() {
  online.value = true;
  flushQueue();
}
function setOffline() {
  online.value = false;
}
onMounted(() => {
  if (typeof window !== "undefined") {
    if (typeof navigator !== "undefined" && navigator.onLine === false) online.value = false;
    window.addEventListener("online", setOnline);
    window.addEventListener("offline", setOffline);
  }
  flushQueue(); // sync anything queued from a previous offline session
  // AI-CONTEXT: the driver's language and the SERVER's copy of it, reconciled once per
  // launch (§23 entry 232). F8 writes every notification from the server's copy, and
  // nothing had ever written it — so this is both the ongoing sync and the repair path
  // for every account that predates it. Silent, and never blocking: it is bookkeeping.
  if (isAuthenticated.value) syncLocale();
  // F3's sensor. Nothing sent the server a position before this — the geofence could
  // emit ENTER (from the arrive button, at the facility's own coordinates) and could
  // never emit EXIT. Adaptive sampling and the battery budget live in core/location.js.
  startLocationReporting();
});
onUnmounted(() => {
  stopLocationReporting();
  if (typeof window !== "undefined") {
    window.removeEventListener("online", setOnline);
    window.removeEventListener("offline", setOffline);
  }
});
</script>

<template>
  <div class="app-frame" :class="{ 'app-frame--wide': portal }">
    <StatusStrip
      v-if="chrome"
      :online="online"
      :pending="pendingWrites"
      :failed="failedWrites"
      @navigate="(to) => router.push(to)"
    />
    <main class="app-content">
      <!-- AI-CONTEXT: §23 entry 100. The MAP alone is kept alive, and the narrowness
           is the decision. Leaving the tab destroyed the Mapbox GL instance; coming
           back rebuilt it on the continental US, fetched the country, re-acquired GPS
           and flew home — two round trips and a visible jump to return to a view the
           driver never left. NAV-1 is untouched: this is a lifecycle rule, not a
           navigation structure, and the five tabs are the same five tabs.

           Only the map, because caching is not free: a kept surface shows what it
           last rendered, and the Load, Money and Docs tabs carry money, clocks and
           evidence state that must never be a cached copy of a minute ago. The map is
           the one surface whose content is ALREADY refetched from its own viewport on
           activation, so keeping it costs nothing in staleness. -->
      <router-view v-slot="{ Component }">
        <!-- AI-CONTEXT: §23 entry 100 kept the MAP alive across tab switches, because it
             is the one surface whose cost is in its FIRST paint — tiles, GL context,
             viewport fetch — and paying that again on every return was the whole defect.
             THE MAP IS DORMANT (D21, §23 entry 228) and keep-aliving a surface no tab can
             reach is pure cost, so the include is empty while it sleeps. It is left as an
             empty array rather than deleted: entry 100's argument is untouched and the
             line is where reactivation puts `MapSurface` back. -->
        <KeepAlive :include="[]">
          <component :is="Component" />
        </KeepAlive>
      </router-view>
    </main>
    <TabBar v-if="chrome" />
  </div>
</template>
