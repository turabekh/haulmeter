<!-- AI-CONTEXT: App scaffold (design-prd §7.2). Top→bottom: status strip →
     content scroll region → persistent five-tab bar. Content never hides under
     the tab bar. Centered ≤480 dp column so wide viewports don't stretch the
     driver app (§7.1). Mobile-first 360×800 baseline. The chrome (status strip +
     tab bar) is suppressed on full-screen flows like login (route.meta.chrome). -->
<script setup>
import { computed, onMounted, onUnmounted } from "vue";
import { useRoute } from "vue-router";
import StatusStrip from "./core/components/StatusStrip.vue";
import TabBar from "./core/components/TabBar.vue";
import { online } from "./core/api.js";

const route = useRoute();
const chrome = computed(() => route.meta.chrome !== false);
const portal = computed(() => route.meta.portal === true);

// F12: reflect the browser's own connectivity too, not just fetch outcomes
function setOnline() {
  online.value = true;
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
});
onUnmounted(() => {
  if (typeof window !== "undefined") {
    window.removeEventListener("online", setOnline);
    window.removeEventListener("offline", setOffline);
  }
});
</script>

<template>
  <div class="app-frame" :class="{ 'app-frame--wide': portal }">
    <StatusStrip v-if="chrome" :online="online" />
    <main class="app-content">
      <router-view />
    </main>
    <TabBar v-if="chrome" />
  </div>
</template>
