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
import SkeletonCard from "../core/components/SkeletonCard.vue";
import Spinner from "../core/components/Spinner.vue";

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

let recorder = null;
let chunks = [];

async function load() {
  state.value = LoadState.LOADING;
  try {
    const body = await fetchTodaysDrill();
    plan.value = body.plan;
    state.value = LoadState.LOADED;
  } catch (err) {
    failure.value = failureOf(err);
    state.value = LoadState.FAILED;
  }
}

onMounted(load);

function play(url) {
  if (url) new Audio(`${API_BASE}${url}`).play().catch(() => {});
}

async function start() {
  if (isDriving.value) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      send();
    };
    recorder.start();
    attempt.value = null;
  } catch {
    failure.value = Failure.SERVER;
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
  if (index.value < plan.value.items.length - 1) {
    index.value += 1;
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

onBeforeUnmount(stop);
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
      <button
        v-if="item.audio_url"
        class="drill__play"
        type="button"
        @click="play(item.audio_url)"
      >
        <Play :size="18" aria-hidden="true" />
        <span>{{ t("roadside.coach.play") }}</span>
      </button>

      <p v-if="isDriving" class="drill__note">{{ t("roadside.session.paused_driving") }}</p>
      <button
        v-else
        class="drill__mic"
        type="button"
        :aria-label="t('roadside.session.answer')"
        :disabled="busy"
        @pointerdown="start"
        @pointerup="stop"
        @pointercancel="stop"
      >
        <Spinner v-if="busy" />
        <Mic v-else :size="28" aria-hidden="true" />
      </button>

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
