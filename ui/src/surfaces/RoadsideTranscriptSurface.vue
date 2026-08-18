<!-- AI-CONTEXT: the stop, played back — both voices, in order.

     WHY THIS EARNS ITS SCREEN. A driver practising English cannot hear their own mistakes
     while they are making them; almost all the value of a recorded stop is in the second
     listen. Every piece of this was already built and one was missing: `Turn.audio_ref`
     existed from the first migration, `classify_audio_30d` existed, the retention sweep
     ran unflagged — and nothing ever wrote the column, so the consent screen promised a
     recording that was transcribed and thrown away.

     THE RECORDING EXPIRES AND THE WORDS DO NOT, which is what consent says and what this
     screen has to show. Thirty days on, `audio_url` is null and `text` is still there: that
     renders as a line you can read and not play, with one honest sentence saying why —
     never a play button that fails when tapped.

     NOT A SCORE SCREEN. No band, no marks, no tags. The verdict lives on the result screen
     and the teaching on the coaching screen; a transcript annotated with grades is a report
     card, and this is a recording of a conversation.

     DRIVING: `withdraws`, like every other roadside surface — it is audio and reading. -->
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from "vue";
import { useRoute } from "vue-router";
import { Play } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { fetchRoadsideTranscript, API_BASE } from "../core/api.js";
import { LoadState, Failure, failureOf } from "../core/load-state.js";
import SkeletonCard from "../core/components/SkeletonCard.vue";

const { t } = useI18n();
const route = useRoute();
// AI-CONTEXT: `withdraws` at speed, and the contract test refuses the claim unless the
// surface actually consults the state. It is audio and reading — the two things a moving
// truck has no room for — so playback stops and the controls go, exactly as the stop does.
const { isDriving } = useDriverState();

const state = ref(LoadState.LOADING);
const failure = ref(null);
const turns = ref([]);
const playingSeq = ref(null);

const anyExpired = computed(
  () => turns.value.some((turn) => turn.text && !turn.audio_url),
);

let current = null;

async function load() {
  state.value = LoadState.LOADING;
  try {
    const body = await fetchRoadsideTranscript(route.params.sessionId);
    turns.value = body.turns || [];
    state.value = LoadState.LOADED;
  } catch (err) {
    failure.value = failureOf(err);
    state.value = LoadState.FAILED;
  }
}

function stop() {
  if (current) {
    current.onended = null;
    current.onerror = null;
    current.pause();
    current = null;
  }
  playingSeq.value = null;
}

function play(turn) {
  // one clip at a time — two voices over each other is not a replay of anything
  stop();
  if (!turn.audio_url) return;
  current = new Audio(`${API_BASE}${turn.audio_url}`);
  playingSeq.value = turn.seq;
  current.onended = stop;
  current.onerror = stop;
  current.play().catch(stop);
}

onMounted(load);
onBeforeUnmount(stop);

// motion ends playback mid-word rather than fading out — Q-4 is a hard pause, not a taper
watch(isDriving, (driving) => {
  if (driving) stop();
});
</script>

<template>
  <div class="script">
    <h1 class="script__title">{{ t("roadside.transcript.title") }}</h1>

    <p v-if="isDriving" class="script__note" role="status">
      {{ t("roadside.session.paused_driving") }}
    </p>

    <SkeletonCard v-else-if="state === LoadState.LOADING" :count="3" />

    <p v-else-if="state === LoadState.FAILED" class="script__note" role="alert">
      {{ failure === Failure.OFFLINE ? t("system.load_offline") : t("roadside.failed") }}
    </p>

    <p v-else-if="!turns.length" class="script__note">{{ t("roadside.transcript.empty") }}</p>

    <template v-else>
      <p v-if="anyExpired" class="script__note">{{ t("roadside.transcript.expired") }}</p>

      <ol class="script__list">
        <li v-for="turn in turns" :key="turn.seq" class="turn" :data-who="turn.speaker">
          <p class="turn__who">
            {{ turn.speaker === "officer"
               ? t("roadside.session.officer")
               : t("roadside.transcript.you") }}
          </p>
          <p class="turn__text">{{ turn.text || "—" }}</p>
          <p v-if="turn.unclear" class="turn__unclear">{{ t("roadside.session.unclear") }}</p>
          <button
            v-if="turn.audio_url"
            class="turn__play"
            type="button"
            :data-playing="playingSeq === turn.seq"
            @click="playingSeq === turn.seq ? stop() : play(turn)"
          >
            <Play :size="16" aria-hidden="true" />
            <span>{{ playingSeq === turn.seq
              ? t("roadside.transcript.stop")
              : t("roadside.coach.play") }}</span>
          </button>
        </li>
      </ol>
    </template>
  </div>
</template>

<style scoped>
.script {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding: var(--s-4);
}
.script__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.script__note {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.script__list {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
.turn {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-2);
}
/* the driver's own turns sit apart from the officer's, so a conversation reads as one */
.turn[data-who="driver"] {
  background: transparent;
}
.turn__who {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  text-transform: uppercase;
}
.turn__text {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.turn__unclear {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
}
.turn__play {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  align-self: flex-start;
  min-height: var(--touch-min);
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--text-1);
  font-family: var(--font-sans);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
}
.turn__play[data-playing="true"] {
  border-color: var(--accent-fill);
  color: var(--accent-fill);
}
</style>
