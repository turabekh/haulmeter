<!-- AI-CONTEXT: App scaffold (design-prd §7.2). Top→bottom: status strip →
     content scroll region → persistent five-tab bar. Content never hides under
     the tab bar. Centered ≤480 dp column so wide viewports don't stretch the
     driver app (§7.1). Mobile-first 360×800 baseline. -->
<script setup>
import StatusStrip from "./core/components/StatusStrip.vue";
import TabBar from "./core/components/TabBar.vue";
</script>

<template>
  <div class="app-frame">
    <StatusStrip :online="true" />
    <main class="app-content">
      <router-view />
    </main>
    <TabBar />
  </div>
</template>
