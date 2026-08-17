<!-- AI-CONTEXT: M15's front door (E3 §E3.1.6). The first surface in the module — before
     this commit every route it fronts was reachable only from a dev probe.

     WHY THERE IS NO SCENARIO LIST. `GET /roadside/scenarios` returns everything a driver
     could run, and this screen offers ONE action. The scenario's version is hidden state
     (a driver never sees it and never picks it), and difficulty is the engine's word, not
     something a driver has any basis to choose between before their first session. A list
     of two indistinguishable rows is a decision imposed rather than offered — §10.5's
     rule about More applies to the same instinct here.

     THE EMPTY STATE IS THE EXPECTED STATE TODAY, not a defect and not a placeholder.
     Nothing has been through review, so the catalogue is legitimately empty, and §15.3
     wants one sentence of purpose rather than a spinner that never resolves. It says why
     — the lines are with a reviewer — because "nothing here" with no reason reads as
     broken.

     DRIVING: `withdraws`. A spoken practice inspection is the single worst thing to put
     in front of someone at 65 mph, and Q-4 makes the engine refuse anyway; withdrawing
     the entry is how the refusal arrives as a designed state rather than a socket
     closing. -->
<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { fetchRoadsideScenarios } from "../core/api.js";
import { LoadState, Failure, failureOf } from "../core/load-state.js";
import SkeletonCard from "../core/components/SkeletonCard.vue";

const { t } = useI18n();
const router = useRouter();
const { isDriving } = useDriverState();

const state = ref(LoadState.LOADING);
const failure = ref(null);
const scenarios = ref([]);

async function load() {
  state.value = LoadState.LOADING;
  try {
    const body = await fetchRoadsideScenarios();
    scenarios.value = body.scenarios || [];
    state.value = LoadState.LOADED;
  } catch (err) {
    failure.value = failureOf(err);
    state.value = LoadState.FAILED;
  }
}

onMounted(load);

function start() {
  router.push({ name: "roadside-consent", params: { scenarioId: scenarios.value[0].id } });
}
</script>

<template>
  <div class="roadside">
    <header class="roadside__head">
      <h1 class="roadside__title">{{ t("more.roadside") }}</h1>
      <p class="roadside__sub">{{ t("roadside.subtitle") }}</p>
    </header>

    <SkeletonCard v-if="state === LoadState.LOADING" :count="1" />

    <p v-else-if="state === LoadState.FAILED" class="roadside__failed" role="alert">
      {{ failure === Failure.OFFLINE ? t("system.load_offline") : t("roadside.failed") }}
      <button class="roadside__retry" type="button" @click="load">
        {{ t("roadside.retry") }}
      </button>
    </p>

    <p v-else-if="!scenarios.length" class="roadside__empty">{{ t("roadside.empty") }}</p>

    <template v-else>
      <p v-if="isDriving" class="roadside__paused">
        {{ t("roadside.session.paused_driving") }}
        <span class="roadside__hint">{{ t("roadside.session.paused_driving_hint") }}</span>
      </p>
      <button v-else class="roadside__cta" type="button" @click="start">
        {{ t("roadside.start") }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.roadside {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding: var(--s-4);
}
.roadside__head {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.roadside__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.roadside__sub,
.roadside__empty,
.roadside__failed,
.roadside__paused {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.roadside__paused {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.roadside__hint {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.roadside__cta {
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
.roadside__retry {
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
