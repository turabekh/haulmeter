<!-- AI-CONTEXT: the result (M15-FR4, Q-8). What a driver is told they are.

     THE BAND COMES FROM THE SERVER AS A KEY, NOT AS A SENTENCE. `label_key` is
     `roadside.band.green` or `roadside.band.green_provisional`, and the provisional half
     is computed from the calibration state in the database rather than passed by a caller
     — so a client cannot drop the word by accident, and this surface cannot decide it is
     confident. Rendering `t(label_key)` is deliberate: the honest label and the confident
     one are different STRINGS, so there is no branch here to get wrong.

     NO PERCENTAGE, and that is E3 §E3.1.4 rather than a design preference. A naked number
     invites comparison on a scale nobody has calibrated, which is the same reason
     `provisional` exists at all. The cutoffs behind the band (80 / 55) are owner-signed —
     decision entry 179 — because until they were, this screen was telling a driver they
     were "green" against a threshold a session had invented.

     FAILURE TAGS ARE RENDERED AS SKILLS, not faults: "Understanding the question", not
     "misunderstood the intent". E3 is explicit that there is no eleventh tag about accent,
     and the wording follows the same instinct — a driver reading this has just been told
     something about their English by a machine, and the list is what to practise.

     REVIEW-NEEDED TURNS ARE STATED, not hidden. Q-2 puts a turn below the ASR floor into
     review rather than scoring it, so some answers legitimately have no verdict yet;
     saying so is the difference between a partial result and a wrong one.

     DRIVING: `withdraws`. The actions go; the reading stays, because a band already
     earned is information rather than a prompt. -->
<script setup>
import { ref, onMounted, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { fetchRoadsideResult, isAuthenticated } from "../core/api.js";
import { LoadState, Failure, failureOf } from "../core/load-state.js";
import SkeletonCard from "../core/components/SkeletonCard.vue";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const { isDriving } = useDriverState();

const state = ref(LoadState.LOADING);
const failure = ref(null);
const result = ref(null);

const reviewNeeded = computed(() => result.value?.review_needed_turns || 0);

async function load() {
  state.value = LoadState.LOADING;
  try {
    result.value = await fetchRoadsideResult(route.params.sessionId);
    state.value = LoadState.LOADED;
  } catch (err) {
    failure.value = failureOf(err);
    state.value = LoadState.FAILED;
  }
}

onMounted(load);
</script>

<template>
  <div class="result">
    <h1 class="result__title">{{ t("roadside.result.title") }}</h1>

    <SkeletonCard v-if="state === LoadState.LOADING" :count="2" />

    <p v-else-if="state === LoadState.FAILED" class="result__failed" role="alert">
      {{ failure === Failure.OFFLINE ? t("system.load_offline") : t("roadside.failed") }}
      <button class="result__retry" type="button" @click="load">{{ t("roadside.retry") }}</button>
    </p>

    <template v-else-if="result">
      <p class="result__band" :data-band="result.band">{{ t(result.label_key) }}</p>
      <p v-if="result.provisional" class="result__provisional">
        {{ t("roadside.result.provisional") }}
      </p>

      <p v-if="reviewNeeded" class="result__review">
        {{ t("roadside.result.review_needed", { n: reviewNeeded }) }}
      </p>

      <section v-if="result.failure_tags.length" class="result__section">
        <h2 class="result__heading">{{ t("roadside.result.practice") }}</h2>
        <ul class="result__tags">
          <li v-for="tag in result.failure_tags" :key="tag" class="result__tag">
            {{ t(`roadside.tag.${tag}`) }}
          </li>
        </ul>
      </section>

      <p v-if="!isAuthenticated" class="result__claim">{{ t("roadside.result.claim") }}</p>

      <button
        v-if="!isDriving"
        class="result__again"
        type="button"
        @click="router.replace({ name: 'roadside' })"
      >
        {{ t("roadside.result.again") }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.result {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding: var(--s-4);
}
.result__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
/* the band is the figure on this screen — §11.1's Meter treatment, applied to the one
   thing the driver came back for */
.result__band {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-meter-size);
  line-height: var(--type-meter-line);
  font-weight: var(--type-meter-weight);
}
.result__band[data-band="green"] {
  color: var(--ledger-500);
}
.result__band[data-band="yellow"] {
  color: var(--marker-500);
}
.result__band[data-band="red"] {
  color: var(--flare-500);
}
.result__provisional,
.result__review,
.result__claim,
.result__failed {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.result__section {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.result__heading {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  font-weight: var(--type-label-weight);
}
.result__tags {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.result__tag {
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.result__again {
  min-height: var(--touch-primary);
  padding: var(--s-3) var(--s-4);
  border: 0;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-family: var(--font-sans);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  font-weight: var(--type-label-weight);
}
.result__retry {
  min-height: var(--touch-min);
  margin-top: var(--s-3);
  padding: var(--s-2) var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-2);
  color: var(--text-1);
  font-family: var(--font-sans);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
}
</style>
