<!-- AI-CONTEXT: the daily drill (M15-FR6), the half that needs no notification.

     One item at a time, and the count is the only progress indicator — E3 asks for a
     "per-skill progress strip (heard ✓ / understood ✓ / answered ✓)", and that shape needs
     per-skill state this surface does not have yet. A count is the honest subset: it says
     how much is left without claiming to know which of three things a driver has achieved.
     The fuller strip is a named remainder rather than a fake.

     NOTHING REMINDS A DRIVER THIS EXISTS. P-1 `readiness_reminder` is an unsigned owner
     fork (entry 177) and no class is registered, so this is a screen you find rather than
     one that finds you. That is the honest state and the surface does not pretend
     otherwise — there is no "we'll remind you tomorrow", because §13.3's rule is that no
     surface may promise something will arrive later.

     DRIVING: `withdraws`. Practice is talking out loud into a microphone. -->
<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { Mic, Play } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import {
  fetchTodaysDrill,
  completeDrill,
  submitCoachingAttempt,
  API_BASE,
} from "../core/api.js";
import { LoadState, Failure, failureOf } from "../core/load-state.js";
import { listenForSpeech } from "../core/listen.js";
import SkeletonCard from "../core/components/SkeletonCard.vue";
import SpeakingIndicator from "../core/components/SpeakingIndicator.vue";

const { t } = useI18n();
const router = useRouter();
const { isDriving } = useDriverState();

const state = ref(LoadState.LOADING);
const failure = ref(null);
const plan = ref(null);
const index = ref(0);
const attempt = ref(null);
const busy = ref(false);

const item = computed(() => plan.value?.items[index.value] || null);
const remaining = computed(() => (plan.value ? plan.value.items.length - index.value : 0));

// AI-CONTEXT: THE PRACTICE SCREEN NEVER GOT THE TREATMENT THE STOP DID. It was still
// hold-to-talk — the interaction entry 187 called "the robot" and removed from the session
// because nobody holds a button while answering a police officer. The same argument applies
// harder here: this is the screen a driver opens every day, and a daily habit that needs a
// thumb held down for every answer is a habit that stops.
//
// So it now behaves like the stop: the question plays itself, the microphone opens when the
// officer stops speaking, and about a second of silence ends the turn. The button remains
// as the fallback for a cab too loud to hear over, exactly as it does there.
const handsFree = ref(true);
const listening = ref(false);
const micDenied = ref(false);

let recorder = null;
let chunks = [];
let micStream = null;
let listener = null;

async function load() {
  state.value = LoadState.LOADING;
  try {
    const body = await fetchTodaysDrill();
    plan.value = body.plan;
    state.value = LoadState.LOADED;
    ask();
  } catch (err) {
    failure.value = failureOf(err);
    state.value = LoadState.FAILED;
  }
}

// AI-CONTEXT: the question ASKS ITSELF and the microphone follows it, which is the whole
// difference between practice and a worksheet. A driver who has to tap play, then hold a
// button, is reading questions off a screen; a driver who hears one and answers it is
// practising the thing a roadside stop actually tests.
function ask() {
  if (!item.value || isDriving.value) return;
  play(item.value.audio_url, { thenListen: true });
}

onMounted(load);

let questionAudio = null;

function play(url, { thenListen = false } = {}) {
  if (!url) {
    if (thenListen) openMic();
    return;
  }
  questionAudio = new Audio(`${API_BASE}${url}`);
  if (thenListen) {
    questionAudio.onended = () => openMic();
    // a clip that fails to play must not leave the driver waiting for a mic that never
    // opens — the question is on screen, so let them answer it
    questionAudio.onerror = () => openMic();
  }
  questionAudio.play().catch(() => {
    if (thenListen) openMic();
  });
}

function stopQuestionAudio() {
  if (questionAudio) {
    questionAudio.onended = null;
    questionAudio.onerror = null;
    questionAudio.pause();
    questionAudio = null;
  }
}

function releaseMic() {
  if (listener) {
    listener.stop();
    listener = null;
  }
  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
  }
}

async function openMic() {
  if (isDriving.value || !handsFree.value || attempt.value) return;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    micDenied.value = true;
    handsFree.value = false;
    return;
  }
  recorder = new MediaRecorder(micStream);
  chunks = [];
  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.onstop = () => {
    releaseMic();
    listening.value = false;
    send();
  };
  recorder.start();
  listening.value = true;

  listener = listenForSpeech(micStream, {
    onSpeechEnd: () => stop(),
    // AI-CONTEXT: heard nothing at all. Says so and hands back the button rather than
    // sitting with an open microphone (§12.4: state what happened AND what to do).
    onTimeout: () => {
      handsFree.value = false;
      listener = null;
      stop();
      releaseMic();
      listening.value = false;
    },
  });
}

// the fallback, for a cab too loud for the detector — press and hold, as before
async function start() {
  if (isDriving.value) return;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(micStream);
    chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = () => {
      releaseMic();
      listening.value = false;
      send();
    };
    recorder.start();
    listening.value = true;
    attempt.value = null;
  } catch {
    micDenied.value = true;
  }
}

function stop() {
  if (recorder && recorder.state === "recording") recorder.stop();
  recorder = null;
}

async function send() {
  busy.value = true;
  const blob = new Blob(chunks, { type: "audio/webm" });
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  try {
    attempt.value = await submitCoachingAttempt(item.value.variant_id, btoa(binary));
  } catch {
    failure.value = Failure.SERVER;
  } finally {
    busy.value = false;
  }
}

async function next() {
  attempt.value = null;
  micDenied.value = false;
  if (index.value < plan.value.items.length - 1) {
    index.value += 1;
    ask();
    return;
  }
  try {
    await completeDrill(plan.value.id);
  } catch {
    // the day's practice happened whether or not the stamp landed; `record_practice`
    // already wrote each item. Failing loudly here would tell a driver they wasted it.
  }
  router.replace({ name: "roadside" });
}

onBeforeUnmount(() => {
  stop();
  stopQuestionAudio();
  releaseMic();
});
</script>

<template>
  <div class="drill">
    <h1 class="drill__title">{{ t("roadside.drill.title") }}</h1>

    <SkeletonCard v-if="state === LoadState.LOADING" :count="1" />

    <p v-else-if="state === LoadState.FAILED" class="drill__note" role="alert">
      {{ failure === Failure.OFFLINE ? t("system.load_offline") : t("roadside.failed") }}
    </p>

    <p v-else-if="!plan" class="drill__note">{{ t("roadside.drill.none") }}</p>

    <p v-else-if="plan.completed" class="drill__note">{{ t("roadside.drill.done") }}</p>

    <template v-else-if="item">
      <p class="drill__meta">
        {{ t("roadside.drill.day", { n: plan.day }) }} ·
        {{ t("roadside.drill.left", { n: remaining }) }}
      </p>

      <p class="drill__line">{{ item.text }}</p>

      <p v-if="isDriving" class="drill__note">{{ t("roadside.session.paused_driving") }}</p>

      <template v-else-if="busy">
        <!-- AI-CONTEXT: the verdict takes seconds. Nothing stood here, so the screen
             looked frozen at the one moment a driver most wants to know something is
             happening.

             THE COPY SAYS "your answer", NOT "how you said it", and the difference is
             Q-1. The first draft read "Checking how you said it" — which tells a driver
             we are marking the WAY they speak, and Q-1's whole point is that accent is
             never scored. The rubric judges whether the answer was intelligible and
             landed, and the words a driver reads have to say that and nothing more.
             Caught by the i18n audit before it shipped, in all six locales at once,
             because a translated violation is six violations. -->
        <SpeakingIndicator :label="t('roadside.coach.checking')" />
      </template>

      <template v-else-if="!attempt">
        <p class="drill__note">
          {{ listening ? t("roadside.session.speak_now") : t("roadside.session.tap_instead") }}
        </p>
        <!-- hands-free is the default; the button is the fallback for a cab too loud for
             the detector, or a driver whose microphone was refused -->
        <button
          v-if="!handsFree || listening"
          class="drill__mic"
          :data-live="listening"
          type="button"
          :aria-label="t('roadside.session.answer')"
          :aria-pressed="listening"
          @pointerdown="start"
          @pointerup="stop"
          @pointercancel="stop"
        >
          <Mic :size="28" aria-hidden="true" />
        </button>
        <p v-if="micDenied" class="drill__note" role="alert">
          {{ t("roadside.session.mic_denied") }}
        </p>
        <button
          v-if="item.audio_url"
          class="drill__play"
          type="button"
          @click="play(item.audio_url)"
        >
          <Play :size="18" aria-hidden="true" />
          <span>{{ t("roadside.coach.play") }}</span>
        </button>
      </template>

      <template v-if="attempt">
        <p class="drill__heard">{{ attempt.transcript }}</p>
        <p class="drill__verdict" :data-passed="attempt.passed">
          {{ attempt.passed ? t("roadside.coach.passed") : t("roadside.coach.not_yet") }}
        </p>
        <button class="drill__next" type="button" @click="next">
          {{ remaining > 1 ? t("roadside.coach.next") : t("roadside.drill.finish") }}
        </button>
      </template>
    </template>
  </div>
</template>

<style scoped>
.drill {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding: var(--s-4);
}
.drill__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.drill__meta {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
}
.drill__line {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
.drill__note,
.drill__heard {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.drill__play {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  align-self: flex-start;
  min-height: var(--touch-min);
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-2);
  color: var(--text-1);
  font-family: var(--font-sans);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
}
.drill__mic {
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
/* live, so a driver can see the microphone is open — same signal the stop uses */
.drill__mic[data-live="true"] {
  background: var(--flare-500);
}
.drill__verdict {
  margin: 0;
  color: var(--marker-500);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.drill__verdict[data-passed="true"] {
  color: var(--ledger-500);
}
.drill__next {
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
