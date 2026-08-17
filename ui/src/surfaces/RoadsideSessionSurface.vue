<!-- AI-CONTEXT: the live session (M15-FR3). THIS IS WHERE THE WEBSOCKET FINALLY CARRIES A
     FRAME — the transport shipped in Session B and had never run outside a test.

     S1 SHAPE, and the reason is the situation being simulated: a driver at a window with
     an officer talking to them. Oversized officer line, one control, nothing else to read.
     §6.5's glove spec sets the floor at 48 dp; the mic is 56 because it is the only thing
     on the screen you are meant to hit while looking somewhere else.

     Q-4's HARD PAUSE is implemented here as a STATE, not as a redirect. `assert_may_continue`
     closes the socket with CLOSE_DRIVING if a frame arrives in motion, so the client's job
     is to stop sending BEFORE that happens and to say why. A driver who gets bounced to the
     map mid-sentence learns nothing; a driver who sees "paused — the truck is moving"
     learns the rule. Recording stops on the same edge, because the alternative is holding
     a live microphone open at speed.

     WHAT THIS FILE DOES NOT DO: it does not score, branch, or decide anything. The socket's
     own docstring makes that claim about the server for the same reason it holds here —
     every judgement about a driver's English lives in `session_loop.py`, and a client that
     interpreted anything would be a second opinion nobody could audit.

     THE OFFICER'S AUDIO IS REFERENCED, NOT STREAMED. `audio_url` points at F6; playing it
     from there is what keeps synthesis latency out of the turn. When it is absent — which
     is every seeded line today, because no audio has been synthesized — the TEXT is the
     simulation. That is a degraded mode, not a broken one, and it is why the text mirror
     is not optional here. -->
<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Mic } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { roadsideStreamUrl, API_BASE } from "../core/api.js";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const { isDriving } = useDriverState();

const Phase = {
  CONNECTING: "connecting",
  OFFICER: "officer",
  RECORDING: "recording",
  SCORING: "scoring",
  PAUSED: "paused",
  FAILED: "failed",
  MIC_DENIED: "mic_denied",
};

const phase = ref(Phase.CONNECTING);
const officerText = ref("");
const officerAudio = ref(null);

let socket = null;
let recorder = null;
let chunks = [];

function send(frame) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(frame));
}

function askForNextLine() {
  if (isDriving.value) return pause();
  send({ type: "ready", driver_state: "IDLE" });
}

function pause() {
  stopRecording();
  phase.value = Phase.PAUSED;
}

onMounted(() => {
  try {
    socket = new WebSocket(roadsideStreamUrl(route.params.sessionId));
  } catch {
    phase.value = Phase.FAILED;
    return;
  }
  socket.onopen = askForNextLine;
  socket.onerror = () => {
    if (phase.value !== Phase.PAUSED) phase.value = Phase.FAILED;
  };
  socket.onclose = () => {
    // a close during a pause is the server agreeing with us (CLOSE_DRIVING), not a fault
    if (![Phase.PAUSED, Phase.SCORING].includes(phase.value)) phase.value = Phase.FAILED;
  };
  socket.onmessage = (event) => {
    const frame = JSON.parse(event.data);
    if (frame.type === "officer") {
      officerText.value = frame.text;
      officerAudio.value = frame.audio_url ? `${API_BASE}${frame.audio_url}` : null;
      phase.value = Phase.OFFICER;
    } else if (frame.type === "scored") {
      // the score itself is NOT shown per turn — a running verdict mid-inspection turns
      // practice into a test, and E3 puts the reading on the result surface
      askForNextLine();
    } else if (frame.type === "complete") {
      router.replace({ name: "roadside-result", params: { sessionId: route.params.sessionId } });
    }
  };
});

// Q-4: the pause is an EDGE, watched rather than polled, so it fires mid-turn
watch(isDriving, (driving) => {
  if (driving) pause();
  else if (phase.value === Phase.PAUSED) askForNextLine();
});

async function startRecording() {
  if (isDriving.value) return pause();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      sendAnswer();
    };
    recorder.start();
    phase.value = Phase.RECORDING;
  } catch {
    phase.value = Phase.MIC_DENIED;
  }
}

function stopRecording() {
  if (recorder && recorder.state === "recording") recorder.stop();
  recorder = null;
}

async function sendAnswer() {
  phase.value = Phase.SCORING;
  const blob = new Blob(chunks, { type: "audio/webm" });
  const buffer = await blob.arrayBuffer();
  let binary = "";
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  send({ type: "answer", audio_b64: btoa(binary), driver_state: "IDLE" });
}

function end() {
  send({ type: "bye" });
  router.replace({ name: "roadside-result", params: { sessionId: route.params.sessionId } });
}

onBeforeUnmount(() => {
  stopRecording();
  if (socket && socket.readyState === WebSocket.OPEN) socket.close();
});
</script>

<template>
  <div class="session">
    <p v-if="phase === Phase.PAUSED" class="session__paused" role="status">
      {{ t("roadside.session.paused_driving") }}
      <span class="session__hint">{{ t("roadside.session.paused_driving_hint") }}</span>
    </p>

    <p v-else-if="phase === Phase.FAILED" class="session__failed" role="alert">
      {{ t("roadside.session.failed") }}
    </p>

    <p v-else-if="phase === Phase.MIC_DENIED" class="session__failed" role="alert">
      {{ t("roadside.session.mic_denied") }}
    </p>

    <p v-else-if="phase === Phase.CONNECTING" class="session__status">
      {{ t("roadside.session.connecting") }}
    </p>

    <template v-else>
      <p class="session__who">{{ t("roadside.session.officer") }}</p>
      <p class="session__line">{{ officerText }}</p>
      <audio v-if="officerAudio" :src="officerAudio" autoplay class="session__audio" />

      <p class="session__status">
        {{ phase === Phase.RECORDING ? t("roadside.session.listening")
           : phase === Phase.SCORING ? t("roadside.session.scoring")
           : t("roadside.session.answer") }}
      </p>

      <button
        class="session__mic"
        type="button"
        :aria-label="t('roadside.session.answer')"
        :aria-pressed="phase === Phase.RECORDING"
        :disabled="phase === Phase.SCORING"
        @pointerdown="startRecording"
        @pointerup="stopRecording"
        @pointercancel="stopRecording"
      >
        <Mic :size="28" aria-hidden="true" />
      </button>
    </template>

    <button class="session__end" type="button" @click="end">
      {{ t("roadside.session.end") }}
    </button>
  </div>
</template>

<style scoped>
.session {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-4);
  min-height: 100%;
  padding: var(--s-4);
}
.session__who {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  text-transform: uppercase;
}
/* the officer line is the screen. §6.2's display step, not a body paragraph. */
.session__line {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
  text-align: center;
}
.session__status,
.session__paused,
.session__failed {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
  text-align: center;
}
.session__paused {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.session__hint {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.session__audio {
  display: none;
}
/* 56 dp — above §6.5's 48 floor, because it is the one control you hit without looking */
.session__mic {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border: 0;
  border-radius: var(--r-pill);
  background: var(--accent-fill);
  color: var(--on-accent);
}
.session__mic[aria-pressed="true"] {
  background: var(--flare-500);
}
.session__end {
  min-height: var(--touch-min);
  margin-top: auto;
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
