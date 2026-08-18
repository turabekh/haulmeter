<!-- AI-CONTEXT: the teaching loop, on screen (M15-FR5).

     FR5 names eight steps and this surface walks the five that need content: the missed
     question replayed, the explanation in the driver's language, the phrase family, a
     model answer to shadow, and a retest on a different phrasing.

     Q-9 IS THE ONE TO GET RIGHT. `explanation: null` means "not released in this language
     yet" and it is rendered as exactly that sentence. It is never filled from the English
     row — a driver promised coaching in Uzbek who is handed English has been told
     something about how much the promise was worth. The server decides this; the surface
     only refuses to paper over it.

     ONE INTENT AT A TIME, in order. A driver who missed three questions gets three passes,
     not a wall — §6's density rule and the plain fact that this is a lesson rather than a
     report.

     THE RETEST IS NOT THE SESSION. It scores comprehension only: slots come from a
     scenario's hidden state and there is no scenario here, so asking whether the driver
     produced a fact nobody gave them would fail every attempt. That is why "passed" here
     is a weaker claim than a passed turn in a real session, and why the reassessment
     (FR7) is where transfer actually gets measured.

     DRIVING: `withdraws` — practice is talking out loud with a microphone, which is the
     same thing the session refuses at speed. -->
<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Mic, Play } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { fetchRoadsideCoaching, submitCoachingAttempt, isAuthenticated, API_BASE } from "../core/api.js";
import { LoadState, Failure, failureOf } from "../core/load-state.js";
import SkeletonCard from "../core/components/SkeletonCard.vue";
import Spinner from "../core/components/Spinner.vue";

const { t, locale } = useI18n();
const route = useRoute();
const router = useRouter();
const { isDriving } = useDriverState();

const state = ref(LoadState.LOADING);
const failure = ref(null);
const plans = ref([]);
const index = ref(0);
const attempt = ref(null);
const busy = ref(false);

const plan = computed(() => plans.value[index.value] || null);
const isLast = computed(() => index.value >= plans.value.length - 1);

let recorder = null;
let chunks = [];

const audioSrc = (url) => (url ? `${API_BASE}${url}` : null);

async function load() {
  state.value = LoadState.LOADING;
  try {
    const body = await fetchRoadsideCoaching(route.params.sessionId, locale.value);
    plans.value = body.coaching || [];
    state.value = LoadState.LOADED;
  } catch (err) {
    failure.value = failureOf(err);
    state.value = LoadState.FAILED;
  }
}

onMounted(load);

function play(url) {
  const src = audioSrc(url);
  if (src) new Audio(src).play().catch(() => {});
}

async function startRetest() {
  if (isDriving.value) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      sendRetest();
    };
    recorder.start();
    attempt.value = null;
  } catch {
    failure.value = Failure.SERVER;
  }
}

function stopRetest() {
  if (recorder && recorder.state === "recording") recorder.stop();
  recorder = null;
}

async function sendRetest() {
  if (!plan.value?.retest_variant_id) return;
  busy.value = true;
  const blob = new Blob(chunks, { type: "audio/webm" });
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  try {
    attempt.value = await submitCoachingAttempt(plan.value.retest_variant_id, btoa(binary));
  } catch {
    failure.value = Failure.SERVER;
  } finally {
    busy.value = false;
  }
}

function next() {
  attempt.value = null;
  if (isLast.value) return router.replace({ name: "roadside" });
  index.value += 1;
}

onBeforeUnmount(stopRetest);
</script>

<template>
  <div class="coach">
    <h1 class="coach__title">{{ t("roadside.coach.title") }}</h1>

    <SkeletonCard v-if="state === LoadState.LOADING" :count="2" />

    <p v-else-if="state === LoadState.FAILED" class="coach__note" role="alert">
      {{ failure === Failure.OFFLINE ? t("system.load_offline") : t("roadside.failed") }}
    </p>

    <p v-else-if="!plans.length" class="coach__note">{{ t("roadside.coach.empty") }}</p>

    <template v-else-if="plan">
      <section class="coach__block">
        <h2 class="coach__label">{{ t("roadside.coach.missed") }}</h2>
        <p class="coach__line">{{ plan.missed_question }}</p>
        <button
          v-if="plan.missed_question_audio"
          class="coach__play"
          type="button"
          @click="play(plan.missed_question_audio)"
        >
          <Play :size="18" aria-hidden="true" />
          <span>{{ t("roadside.coach.play") }}</span>
        </button>
      </section>

      <!-- Q-9: an honest absence, never the English row -->
      <p v-if="!plan.explanation" class="coach__note">{{ t("roadside.coach.no_explanation") }}</p>
      <template v-else>
        <p class="coach__explanation">{{ plan.explanation }}</p>
        <!-- AI-CONTEXT: THE EXPLANATION SPOKEN, in the driver's own language. This module
             teaches English to people whose READING — in any language, including their
             own — may be weaker than their listening, so an Uzbek paragraph they cannot
             comfortably read leaves the whole Q-9 apparatus protecting something still
             unusable. E3 §E3.4.2 budgets for an Uzbek coach voice by name.

             Its absence is NOT the same absence as `explanation` being null. That one
             means "not yet in your language"; this one means "here, but only in writing",
             which is what a language we can print and cannot speak looks like. The surface
             says nothing about the second — a missing button is not a claim — because
             there is no action a driver could take about it. -->
        <button
          v-if="plan.explanation_audio"
          class="coach__play"
          type="button"
          @click="play(plan.explanation_audio)"
        >
          <Play :size="18" aria-hidden="true" />
          <span>{{ t("roadside.coach.play_explanation") }}</span>
        </button>
      </template>

      <section v-if="plan.phrase_family.length" class="coach__block">
        <h2 class="coach__label">{{ t("roadside.coach.family") }}</h2>
        <ul class="coach__family">
          <li v-for="p in plan.phrase_family" :key="p.text" class="coach__family-row">
            <span class="coach__family-text">{{ p.text }}</span>
            <button
              v-if="p.audio_url"
              class="coach__play"
              type="button"
              :aria-label="t('roadside.coach.play')"
              @click="play(p.audio_url)"
            >
              <Play :size="18" aria-hidden="true" />
            </button>
          </li>
        </ul>
      </section>

      <section v-if="plan.model_answer" class="coach__block">
        <h2 class="coach__label">{{ t("roadside.coach.model") }}</h2>
        <p class="coach__line">{{ plan.model_answer }}</p>
        <p class="coach__note">{{ t("roadside.coach.shadow") }}</p>
        <button
          v-if="plan.model_answer_audio"
          class="coach__play"
          type="button"
          @click="play(plan.model_answer_audio)"
        >
          <Play :size="18" aria-hidden="true" />
          <span>{{ t("roadside.coach.play") }}</span>
        </button>
      </section>

      <section v-if="plan.retest_question" class="coach__block">
        <h2 class="coach__label">{{ t("roadside.coach.retest") }}</h2>
        <p class="coach__line">{{ plan.retest_question }}</p>

        <p v-if="isDriving" class="coach__note">
          {{ t("roadside.session.paused_driving") }}
        </p>
        <button
          v-else
          class="coach__mic"
          type="button"
          :aria-label="t('roadside.session.answer')"
          :disabled="busy"
          @pointerdown="startRetest"
          @pointerup="stopRetest"
          @pointercancel="stopRetest"
        >
          <Spinner v-if="busy" />
          <Mic v-else :size="28" aria-hidden="true" />
        </button>

        <template v-if="attempt">
          <p class="coach__heard">{{ attempt.transcript }}</p>
          <p class="coach__verdict" :data-passed="attempt.passed">
            {{ attempt.passed ? t("roadside.coach.passed") : t("roadside.coach.not_yet") }}
          </p>
          <p v-if="!isAuthenticated" class="coach__note">{{ t("roadside.coach.guest_note") }}</p>
        </template>
      </section>

      <button class="coach__next" type="button" @click="next">
        {{ isLast ? t("roadside.coach.done") : t("roadside.coach.next") }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.coach {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding: var(--s-4);
}
.coach__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.coach__block {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.coach__label {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  font-weight: var(--type-label-weight);
  text-transform: uppercase;
}
.coach__line {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
}
.coach__explanation,
.coach__note,
.coach__heard {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.coach__family {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
.coach__family-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
}
.coach__family-text {
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.coach__play {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  min-height: var(--touch-min);
  min-width: var(--touch-min);
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-2);
  color: var(--text-1);
  font-family: var(--font-sans);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
}
.coach__mic {
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: flex-start;
  width: 56px;
  height: 56px;
  border: 0;
  border-radius: var(--r-pill);
  background: var(--accent-fill);
  color: var(--on-accent);
}
.coach__verdict {
  margin: 0;
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
  color: var(--marker-500);
}
.coach__verdict[data-passed="true"] {
  color: var(--ledger-500);
}
.coach__next {
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
</style>
