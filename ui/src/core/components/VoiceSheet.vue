<!-- AI-CONTEXT: Voice Copilot sheet (M11, PRD §8.11 / design-prd §14). The wake
     affordance opens this; the driver asks in words and the app answers over its
     OWN data (intent routing, api.js -> /voice/ask). Real STT is the F9 seam
     (wired at activation); here the input is text/dictation. Motion-aware: while
     DRIVING the spoken answer is the hero (large), matching voice-first policy
     (M11-FR2). The answer is intent-routed by the backend; the sheet just shows
     it and, when the intent hands off, could deep-link (kept simple here). -->
<script setup>
import { ref } from "vue";
import { Send } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { askVoice } from "../api.js";

const props = defineProps({
  driving: { type: Boolean, default: false },
});
const { t } = useI18n();

const text = ref("");
const answer = ref(null);
const asking = ref(false);

async function ask() {
  const q = text.value.trim();
  if (!q) return;
  asking.value = true;
  try {
    answer.value = await askVoice(q, props.driving);
  } catch {
    // offline / no session — the copilot needs the live data behind it
    answer.value = { spoken: t("system.offline"), intent: "unknown" };
  }
  asking.value = false;
  text.value = "";
}
</script>

<template>
  <div class="voice">
    <p v-if="answer" class="voice__answer" :class="{ hero: driving }" aria-live="polite">
      {{ answer.spoken }}
    </p>

    <form class="voice__form" @submit.prevent="ask">
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
  margin: 0;
  padding: var(--s-3);
  border-radius: var(--r-card);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
/* voice-first: while driving the spoken answer is oversized (§14 / S1) */
.voice__answer.hero {
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
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
