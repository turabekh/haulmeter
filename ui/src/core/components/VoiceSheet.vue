<!-- AI-CONTEXT: Voice Copilot sheet (M11, PRD §8.11 / design-prd §14). The mic
     affordance opens this; the driver speaks and the app answers over its OWN
     data (intent routing, api.js -> /voice/ask). On-device Web Speech: the mic
     button captures speech (SpeechRecognition -> text -> /ask) and answers are
     spoken back (SpeechSynthesis) — voice-first + audio-out while DRIVING
     (§14.1). Typing is always available; where the platform lacks the API the
     mic/speaker hide and it degrades to text (§14.5 — one graceful re-ask, never
     pretend to understand). Answers are ≤2 sentences, figure-first (§14.3). -->
<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import { Send, Mic, Square, Volume2 } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { askVoice } from "../api.js";
import {
  recognitionSupported,
  createRecognizer,
  synthesisSupported,
  speak,
  cancelSpeech,
} from "../speech.js";

const props = defineProps({
  driving: { type: Boolean, default: false },
});
const { t, locale } = useI18n();

const text = ref("");
const answer = ref(null);
const asking = ref(false);
const listening = ref(false);
const hint = ref(""); // §14.5 graceful re-ask, shown once then falls back to typing

const micOn = recognitionSupported();
const ttsOn = synthesisSupported();
let recognizer = null;

function startListening() {
  if (!micOn || asking.value) return;
  hint.value = "";
  cancelSpeech(); // don't listen over our own spoken answer
  recognizer = createRecognizer(locale.value, {
    onResult: (transcript) => {
      text.value = transcript;
      ask(); // heard something -> route it immediately (voice-first)
    },
    onError: (err) => {
      listening.value = false;
      // one graceful re-ask, then the visible input is the fallback (§14.5)
      hint.value = err === "not-allowed" ? t("voice.mic_blocked") : t("voice.retry");
    },
    onEnd: () => {
      listening.value = false;
    },
  });
  listening.value = true;
  recognizer.start();
}

function stopListening() {
  if (recognizer) recognizer.stop();
  listening.value = false;
}

async function ask() {
  const q = text.value.trim();
  if (!q) return;
  stopListening();
  asking.value = true;
  try {
    answer.value = await askVoice(q, props.driving);
  } catch {
    // offline / no session — the copilot needs the live data behind it
    answer.value = { spoken: t("system.offline"), intent: "unknown" };
  }
  asking.value = false;
  text.value = "";
  // while DRIVING the answer is audio-first (§14.1/§13.4); stopped, tap to hear
  if (props.driving && ttsOn && answer.value?.spoken) speak(answer.value.spoken, locale.value);
}

function replay() {
  if (answer.value?.spoken) speak(answer.value.spoken, locale.value);
}

onMounted(() => {
  // opened from a mic tap (a user gesture) -> start listening; errors fall back
  if (micOn) startListening();
});
onBeforeUnmount(() => {
  stopListening();
  cancelSpeech();
});
</script>

<template>
  <div class="voice">
    <div v-if="answer" class="voice__answer" :class="{ hero: driving }">
      <p class="voice__spoken" aria-live="polite">{{ answer.spoken }}</p>
      <button
        v-if="ttsOn"
        class="voice__replay"
        type="button"
        :aria-label="t('voice.replay')"
        @click="replay"
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
      <button class="voice__send" type="submit" :disabled="asking" :aria-label="t('voice.ask')">
        <Send :size="20" :stroke-width="2" aria-hidden="true" />
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
.voice__input {
  flex: 1 1 auto;
  min-height: 56px;
  padding: 0 var(--s-3);
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.voice__send {
  width: 56px;
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
