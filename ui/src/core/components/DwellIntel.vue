<!-- AI-CONTEXT: what a dock has done to other drivers — ONE component, so two surfaces
     cannot drift (§23 R3).

     The confirm step and the facility page were answering the same question in two
     different formats from two different endpoints with two different floors: the confirm
     step rendered a raw pair from `/intel/pre-acceptance` where the server applies the
     floor, and the facility page rendered `Math.round(exceed_rate * 100)%` from
     `/intel/detention-risk` with its own `MIN_RATE_SAMPLE` in JS. A driver comparing a
     dock's page against the load they were about to accept read two different numbers
     about the same dock.

     A RAW PAIR, NEVER A PERCENTAGE (§23 entry 153). A fraction carries its own sample
     size; "67%" over three stops overstates what we know, and it renders in the alarm
     token while doing it. The pair also travels with the free time it was counted
     against, because "ran past the 120 minutes your contract gives you" and "ran past the
     two hours we assumed" are different sentences.

     NO FLOOR LIVES HERE. The server withholds a figure below the sample floor, so there
     is deliberately nothing to hedge on this side — an absent half is absent, not weak.
     A floor enforced in two clients is a floor that will one day be enforced in one. -->
<script setup>
import { useI18n } from "../i18n.js";

const { t } = useI18n();

defineProps({
  // the `/intel/pre-acceptance` shape: { risk, best_hour, min_sample }. Each half is
  // independently absent — a dock with a solid pair and no hour that clears the floor is
  // a real dock, and withholding both because one is thin throws away what we do know.
  intel: { type: Object, default: null },
});

function hourLabel(h) {
  return `${String(h).padStart(2, "0")}:00`;
}
</script>

<template>
  <p v-if="intel?.risk" class="intel">
    <span>{{ t("load.rc_risk", { free: intel.risk.free_time_minutes }) }}</span>
    <span class="intel__figure mono">
      {{ intel.risk.exceeded }} / {{ intel.risk.sample_size }}
    </span>
    <span class="intel__meta">{{ t("profile.stops_basis") }}</span>
  </p>
  <p v-if="intel?.best_hour" class="intel">
    <span>{{ t("load.rc_best_hour") }}</span>
    <span class="intel__figure mono">{{ hourLabel(intel.best_hour.hour) }}</span>
    <span class="intel__meta">
      {{ intel.best_hour.sample_size }} {{ t("profile.stops_basis") }}
    </span>
  </p>
</template>

<style scoped>
.intel {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-1) var(--s-2);
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.intel__figure {
  color: var(--text-1);
}
.intel__meta {
  color: var(--text-3);
}
</style>
