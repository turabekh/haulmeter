<!-- AI-CONTEXT: the iOS install path, which is the only one that cannot be a button.
     Safari never fires `beforeinstallprompt` and exposes no install API at all, so on
     iPhone "install" is a gesture in the browser's own chrome and the app's only
     available move is to name the three steps. That is why this sheet exists and why
     there is no Android equivalent: Android gets `prompt()`, which is one tap.

     It matters more here than anywhere else. index.html has said since entry 111 that
     "iOS requires an INSTALLED PWA for push at all", so on this platform these three
     lines are the difference between Web Push being reachable and being a comment.

     Composed from the existing sheet (§8, NAV-3) and the ordered-list shape — no new
     pattern (§22.2). The steps are NUMBERED rather than bulleted because they are a
     sequence performed in order, and a driver who does step 2 first sees nothing. -->
<script setup>
import { Share } from "lucide-vue-next";
import { useI18n } from "../i18n.js";

const { t } = useI18n();
</script>

<template>
  <div class="ios-install">
    <p class="ios-install__why">{{ t("install.why") }}</p>
    <ol class="ios-install__steps">
      <li class="ios-install__step">
        <span class="ios-install__n">1</span>
        <span class="ios-install__text">
          {{ t("install.ios_step1") }}
          <Share :size="16" :stroke-width="2" class="ios-install__glyph" aria-hidden="true" />
        </span>
      </li>
      <li class="ios-install__step">
        <span class="ios-install__n">2</span>
        <span class="ios-install__text">{{ t("install.ios_step2") }}</span>
      </li>
      <li class="ios-install__step">
        <span class="ios-install__n">3</span>
        <span class="ios-install__text">{{ t("install.ios_step3") }}</span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.ios-install__why {
  margin: 0 0 var(--s-4);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.ios-install__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.ios-install__step {
  display: flex;
  align-items: flex-start;
  gap: var(--s-3);
}
/* the numeral is the only fixed-width thing here, so a two-line step keeps its text
   aligned under itself rather than wrapping back under the number */
.ios-install__n {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-pill);
  background: var(--line-1);
  color: var(--text-2);
  font-size: var(--type-caption-size);
  font-variant-numeric: tabular-nums;
}
.ios-install__text {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--text-1);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
/* the Share glyph inline, because "tap Share" is a shape a driver looks for in a
   toolbar rather than a word they read */
.ios-install__glyph {
  display: inline-block;
  vertical-align: text-bottom;
  color: var(--text-2);
}
</style>
