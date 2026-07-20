<!-- AI-CONTEXT: App scaffold (design-prd §7.2). Top→bottom: status strip →
     content scroll region → persistent five-tab bar. Content never hides under
     the tab bar. Centered ≤480 dp column so wide viewports don't stretch the
     driver app (§7.1). Mobile-first 360×800 baseline. The chrome (status strip +
     tab bar) is suppressed on full-screen flows like login (route.meta.chrome). -->
<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import StatusStrip from "./core/components/StatusStrip.vue";
import TabBar from "./core/components/TabBar.vue";

const route = useRoute();
const chrome = computed(() => route.meta.chrome !== false);
</script>

<template>
  <div class="app-frame">
    <StatusStrip v-if="chrome" :online="true" />
    <main class="app-content">
      <router-view />
    </main>
    <TabBar v-if="chrome" />
  </div>
</template>
