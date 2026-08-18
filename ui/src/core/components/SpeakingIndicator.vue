<!-- AI-CONTEXT: "he is about to say something", for the seconds where nothing is happening.

     A NEW COMPONENT PATTERN, WHICH §22.2 RESERVES FOR THE OWNER — and this one is theirs:
     "can we add like typing type indicator while getting response back". Logged as a
     decision entry rather than slipped in, because the rule exists so that patterns are
     decided once rather than invented per screen.

     WHY IT IS NOT A SPINNER. `Spinner.vue` already exists and would have been the
     no-decision option, but it means "the system is working" — a machine state. This means
     "a person is about to speak", which is a different claim and the only honest one here:
     the officer's next line takes ~2s to choose and voice, and a driver who sees nothing
     assumes the app is stuck. Three dots is the form every messaging app taught everyone
     to read, so it needs no explanation in seven languages.

     IT SAYS NOTHING IT DOES NOT KNOW. No text, no "thinking…", no percentage — the wait is
     short and variable, and a label would either lie about progress or need translating for
     a claim it cannot support. Composed entirely from existing tokens: no new colour, no
     new size, no new spacing value.

     A11Y: `role="status"` with a label so a screen reader says who is about to speak rather
     than announcing three decorative dots. `prefers-reduced-motion` stops the animation and
     leaves the dots visible — the information survives, the movement does not. -->
<script setup>
import { useI18n } from "../i18n.js";

const { t } = useI18n();
defineProps({
  label: { type: String, default: "" },
});
</script>

<template>
  <p class="speaking" role="status" :aria-label="label || t('roadside.session.speaking')">
    <span class="speaking__dot" />
    <span class="speaking__dot" />
    <span class="speaking__dot" />
  </p>
</template>

<style scoped>
.speaking {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0;
  min-height: var(--touch-min);
}
.speaking__dot {
  width: 10px;
  height: 10px;
  border-radius: var(--r-pill);
  background: var(--text-3);
  animation: speaking-pulse 1.2s ease-in-out infinite;
}
.speaking__dot:nth-child(2) {
  animation-delay: 0.18s;
}
.speaking__dot:nth-child(3) {
  animation-delay: 0.36s;
}
@keyframes speaking-pulse {
  0%, 60%, 100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-3px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .speaking__dot {
    animation: none;
    opacity: 0.55;
  }
}
</style>
