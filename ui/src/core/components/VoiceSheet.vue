<!-- AI-CONTEXT: Voice Copilot sheet (M11, PRD §8.11 / design-prd §14).

     THE EARS AND THE MOUTH ARE THE SERVER'S NOW (decision 209), and the reason is that
     the browser's could not do the job for the drivers this product is for:

     · `SpeechRecognition` DOES NOT EXIST in Safari on iOS. An iPhone driver had a mic
       button that degraded to typing, forever, which is honest and is also why the
       owner's verdict was "it doesn't work".
     · `speechSynthesis` has no `uz-UZ`, `so-SO` or `pa-IN` voice on any mainstream
       handset, so the copilot was MUTE in exactly the languages it exists to serve —
       while a paid Azure Uzbek voice sat in the same codebase voicing M15.

     So: `MediaRecorder` -> `/voice/listen` -> Deepgram, and the answer comes back as mp3
     bytes from Azure, played from a blob. `MediaRecorder` works everywhere
     `SpeechRecognition` did and on iOS besides, so nothing was lost by dropping it.

     Hands-free by default, using the same energy-gate detector M15 built (`listen.js`,
     entry 187): nobody holds a button while driving. The hold-to-talk path stays as the
     fallback for a cab too loud for the detector.

     `speechSynthesis` REMAINS as the fallback voice only — for a box with no Azure key,
     where the honest degradation is a robot reading English rather than silence.
     Answers are ≤2 sentences, figure-first (§14.3). -->
<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import { Send, Mic, Square, Volume2 } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { askVoice, listenVoice } from "../api.js";
import Spinner from "./Spinner.vue";
import { synthesisSupported, speak, cancelSpeech } from "../speech.js";
import { listenForSpeech } from "../listen.js";

const props = defineProps({
  driving: { type: Boolean, default: false },
});
const { t, locale } = useI18n();

const text = ref("");
const answer = ref(null);
const asking = ref(false);
const listening = ref(false);
const hint = ref(""); // §14.5 graceful re-ask, shown once then falls back to typing
const speaking = ref(false);
const replayRequested = ref(false);

// MediaRecorder is the floor now, not SpeechRecognition — it exists wherever the old
// path did and on iOS besides, so the mic button is real on every handset.
const micOn = typeof window !== "undefined" && typeof window.MediaRecorder !== "undefined";
// the browser voice is the FALLBACK only, for a box with no Azure key
const ttsFallback = synthesisSupported();

let micStream = null;
let recorder = null;
let listener = null;
let chunks = [];
let current = null;

function releaseMic() {
  if (listener) { listener.stop(); listener = null; }
  if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
}

function stopRecorder() {
  if (recorder && recorder.state === "recording") recorder.stop();
  recorder = null;
}

// AI-CONTEXT: HANDS-FREE, because nobody holds a button while answering at 65 mph — the
// same argument entry 187 made for M15's session loop, and the same detector. The energy
// gate learns the cab's floor rather than using a constant: an idling truck is not a quiet
// kitchen, and a fixed threshold either never triggers in one or never stops in the other.
async function startListening() {
  if (!micOn || asking.value || listening.value) return;
  hint.value = "";
  cancelSpeech();
  stopAudio();
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    // a refusal is a fact about the device, not a thing to re-ask forever (§12.4)
    hint.value = t("voice.mic_blocked");
    return;
  }
  chunks = [];
  recorder = new MediaRecorder(micStream);
  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.onstop = () => {
    releaseMic();
    listening.value = false;
    send();
  };
  recorder.start();
  listening.value = true;
  listener = listenForSpeech(micStream, {
    onSpeechEnd: () => stopRecorder(),
    // heard nothing at all: say so and hand the button back rather than sitting with an
    // open microphone (§12.4 — what happened AND what to do)
    onTimeout: () => {
      listener = null;
      stopRecorder();
      hint.value = t("voice.retry");
    },
  });
}

function stopListening() {
  stopRecorder();
  releaseMic();
  listening.value = false;
}

async function send() {
  if (!chunks.length) return;
  asking.value = true;
  hint.value = "";
  try {
    const blob = new Blob(chunks, { type: "audio/webm" });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
    answer.value = await listenVoice(btoa(binary), props.driving, locale.value);
    play(answer.value);
    // heard, but not confidently enough to act on — the server says so rather than
    // routing a guess, and the driver is shown what it thought it heard
    if (answer.value?.data?.unclear) hint.value = t("voice.retry");
  } catch (err) {
    // AI-CONTEXT: SAY WHICH FAILURE IT WAS. The first version of this collapsed every
    // outcome into "voice needs a connection" — which is the defect entry 90 fixed for
    // the old recogniser, reintroduced by me the moment its taxonomy was deleted. The
    // owner then met a copilot that blamed the network for a vendor with no Uzbek model,
    // and the screenshot could not say which of the two it was.
    //
    // §12.4: what happened, and what to do instead. "Try again" is honest only when
    // trying again could work.
    answer.value = null;
    const status = Number(String(err?.message || "").match(/(\d{3})$/)?.[1]);
    hint.value =
      status === 401
        ? t("voice.signed_out")
        : status === 503
          ? t("voice.speech_down")
          : status === 422
            ? t("voice.retry")
            : t("voice.net_down");
  }
  asking.value = false;
}

// AI-CONTEXT: the answer's OWN voice, in the driver's language, from Azure. The browser
// fallback runs only when the server sent no audio — which means either no Azure key on
// this box or a locale we have no voice for, and a robot reading English is better than
// silence in the first case and is all we have in the second.
function stopAudio() {
  if (current) {
    current.onended = null;
    current.pause();
    current = null;
  }
  speaking.value = false;
}

function play(a) {
  if (!a) return;
  const wanted = props.driving || replayRequested.value;
  replayRequested.value = false;
  if (!wanted) return;
  if (a.audio_b64) {
    stopAudio();
    current = new Audio(`data:audio/mpeg;base64,${a.audio_b64}`);
    speaking.value = true;
    current.onended = stopAudio;
    current.onerror = stopAudio;
    current.play().catch(stopAudio);
    return;
  }
  if (ttsFallback && a.spoken) speak(a.spoken, locale.value);
}

async function ask() {
  const q = text.value.trim();
  if (!q) return;
  stopListening();
  asking.value = true;
  try {
    answer.value = await askVoice(q, props.driving, locale.value);
    play(answer.value);
  } catch {
    // offline / no session — the copilot needs the live data behind it
    answer.value = { spoken: t("system.offline"), intent: "unknown" };
  }
  asking.value = false;
  text.value = "";
}

function replay() {
  replayRequested.value = true;
  play(answer.value);
}

onMounted(() => {
  // opened from a mic tap (a user gesture) -> start listening; errors fall back to typing
  if (micOn) {
    startListening();
    return;
  }
  hint.value = t("voice.unsupported");
});
onBeforeUnmount(() => {
  stopListening();
  stopAudio();
  cancelSpeech();
});
</script>

<template>
  <div class="voice">
    <div v-if="answer" class="voice__answer" :class="{ hero: driving }">
      <p class="voice__spoken" aria-live="polite">{{ answer.spoken }}</p>
      <!-- AI-CONTEXT: offered when EITHER voice can serve it — the server's mp3 or the
           browser's fallback. Gating this on `synthesisSupported()` alone hid the button
           on precisely the phones that now have a real Azure voice available to them.
           `data-playing` acknowledges the tap on screen whether or not sound reaches the
           ear, which is entry 205's lesson from the coaching surface. -->
      <button
        v-if="answer.audio_b64 || ttsFallback"
        class="voice__replay"
        type="button"
        :data-playing="speaking"
        :aria-label="speaking ? t('voice.stop') : t('voice.replay')"
        @click="speaking ? stopAudio() : replay()"
      >
        <Volume2 :size="18" :stroke-width="2" aria-hidden="true" />
      </button>
    </div>

    <p v-if="listening" class="voice__hint voice__hint--live" role="status">{{ t("voice.listening") }}</p>
    <p v-else-if="hint" class="voice__hint" role="alert">{{ hint }}</p>

    <form class="voice__form" @submit.prevent="ask">
      <button
        v-if="micOn"
        class="voice__mic"
        :class="{ 'voice__mic--on': listening }"
        type="button"
        :aria-label="listening ? t('voice.stop') : t('voice.mic')"
        :aria-pressed="listening"
        @click="listening ? stopListening() : startListening()"
      >
        <Square v-if="listening" :size="18" :stroke-width="2.5" aria-hidden="true" />
        <Mic v-else :size="20" :stroke-width="2" aria-hidden="true" />
      </button>
      <input
        v-model="text"
        class="voice__input"
        type="text"
        :placeholder="t('voice.placeholder')"
        :aria-label="t('voice.title')"
      />
      <button
        class="voice__send"
        type="submit"
        :disabled="asking"
        :aria-label="asking ? t('busy.working') : t('voice.ask')"
      >
        <Spinner v-if="asking" :size="20" />
        <Send v-else :size="20" :stroke-width="2" aria-hidden="true" />
      </button>
    </form>
  </div>
</template>

<style scoped>
.voice {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.voice__answer {
  display: flex;
  align-items: flex-start;
  gap: var(--s-2);
  margin: 0;
  padding: var(--s-3);
  border-radius: var(--r-card);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.voice__spoken {
  margin: 0;
  flex: 1;
}
.voice__replay {
  flex: none;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--shield-500);
}
/* voice-first: while driving the spoken answer is oversized (§14 / S1) */
.voice__answer.hero .voice__spoken {
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
}
.voice__hint {
  margin: 0;
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.voice__hint--live {
  color: var(--shield-500);
}
.voice__mic {
  flex: none;
  width: 56px;
  min-height: 56px;
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  color: var(--text-1);
  display: flex;
  align-items: center;
  justify-content: center;
}
.voice__mic--on {
  background: var(--shield-500);
  border-color: var(--shield-500);
  color: var(--on-accent);
}
.voice__form {
  display: flex;
  align-items: stretch;
  gap: var(--s-2);
}
/* `min-width: 0` is what lets this shrink. A flex item's default `min-width: auto`
   floors it at its intrinsic content width, so once the send button stopped
   collapsing, the row overflowed 360 dp instead — the two rules only work together. */
.voice__input {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 56px;
  padding: 0 var(--s-3);
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
/* `width: 56px` is not a floor — as a flex child it shrank to 32 dp beside a growing
   input, so the send button rendered narrower than §6.5 allows while its declared
   width said otherwise. `flex: none` is what makes the 56 real. */
.voice__send {
  flex: none;
  width: 56px;
  min-width: 56px;
  min-height: 56px;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  display: flex;
  align-items: center;
  justify-content: center;
}
.voice__send:disabled {
  opacity: 0.6;
}
</style>
