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
import { listenForSpeech } from "../core/listen.js";
import SpeakingIndicator from "../core/components/SpeakingIndicator.vue";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const { isDriving } = useDriverState();

const Phase = {
  CONNECTING: "connecting",
  OFFICER: "officer",
  RECORDING: "recording",
  SCORING: "scoring",
  HEARD: "heard",
  WAITING: "waiting",
  PAUSED: "paused",
  FAILED: "failed",
  MIC_DENIED: "mic_denied",
};

const phase = ref(Phase.CONNECTING);
const officerText = ref("");
const officerAudio = ref(null);
// AI-CONTEXT: the officer's line arrives before his voice does (the server sends two
// frames). True between them — the question is readable, but he has not said it yet, so
// the mic stays shut.
const awaitingAudio = ref(false);
// AI-CONTEXT: THE SOUND A PERSON MAKES WHILE THEY ARE STILL LISTENING. Handed over once
// with the first officer frame and played the instant the microphone closes, over the
// ~1.5s the machine needs to transcribe and think. Fetching one at the moment it is needed
// would arrive exactly too late to be the thing that covers the wait, which is why the
// client holds the pool and chooses.
const thinkingUrls = ref([]);
// AI-CONTEXT: what the RECOGNISER heard, shown back before the next question.
//
// The `scored` frame has always carried `transcript`, `confidence` and `review_needed`,
// and this surface discarded all three — so a driver spoke into a mic and the screen did
// nothing until a new question replaced the old one. That is not a practice tool, it is a
// prompt with a microphone next to it.
//
// It shows the TRANSCRIPT, never the score. A running verdict mid-inspection turns
// practice into a test, and the reading belongs on the result surface. But "here is what
// I heard you say" is not a verdict — it is the one piece of feedback that lets a driver
// tell "I said it wrong" from "it heard me wrong", which is the difference between a tool
// they can improve with and one they distrust.
const heardText = ref("");
const heardUnclear = ref(false);
// the driver's own recording, kept in the browser for the length of the turn so they can
// hear themselves. Nothing is uploaded for this — it is the blob that was just sent.
// AI-CONTEXT: hands-free is the DEFAULT and the button is the fallback, not the other way
// round. Nobody holds a button while answering a police officer, and a driver at a window
// has their hands on paperwork. `handsFree` goes false the moment the detector cannot hear
// anything — a loud cab, a dead mic — and the surface offers the button instead of leaving
// someone talking into a screen that is not listening.
const handsFree = ref(true);
const ackText = ref("");
// what the officer said back of the driver's OWN answer — "Chicago." — played before the
// acknowledgement. The difference between a machine that scored you and a person who heard
// you, and E3 budgets the runtime TTS for exactly this.
const echoText = ref("");
const closingText = ref("");

let socket = null;
let recorder = null;
let chunks = [];
let listener = null;
let micStream = null;
// AI-CONTEXT: the conversation CARRIES ITSELF. Requiring a tap between every question
// turned a roadside stop into a form — a real officer does not wait to be asked for the
// next question. The beat is long enough to read what was heard and short enough that the
// exchange still feels like one, and ANY interaction cancels it: a driver who reaches for
// the replay is engaging, not idling, and yanking the screen away mid-tap is the rudest
// thing an auto-advance can do. The button stays for anyone who wants to move now.
// AI-CONTEXT: NOT the mechanism — the stall guard. The server sends the officer's next
// line unprompted, immediately after the score, so nothing here paces the conversation any
// more. This exists only so a dropped frame does not leave a driver looking at a screen
// that will never speak again. Generous on purpose: firing it early would ask for a second
// question while the first is still in flight.
const STALL_GUARD_MS = 12000;
let advanceTimer = null;

function cancelAutoAdvance() {
  if (advanceTimer) clearTimeout(advanceTimer);
  advanceTimer = null;
}

// AI-CONTEXT: two clips, in order, without stacking them on top of each other. `Audio`
// plays immediately, so firing both at once makes the officer say "ChicagoOkay" over
// himself — which is worse than saying neither.
function playInOrder(urls, onDone) {
  const queue = urls.filter(Boolean);
  if (!queue.length) {
    if (onDone) onDone();
    return;
  }
  const next = () => {
    const url = queue.shift();
    if (!url) {
      if (onDone) onDone();
      return;
    }
    const audio = new Audio(`${API_BASE}${url}`);
    audio.onended = next;
    audio.onerror = next;
    audio.play().catch(next);
  };
  next();
}

function send(frame) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(frame));
}

function askForNextLine() {
  if (isDriving.value) return pause();
  send({ type: "ready", driver_state: "IDLE" });
}

function pause() {
  cancelAutoAdvance();
  stopRecording();
  releaseMic();
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
      cancelAutoAdvance(); // the officer spoke; the stall guard has nothing to guard
      // AI-CONTEXT: a stop OPENS. The greeting rides the first officer frame rather than
      // the session-create response, because the surface that creates a session is the
      // consent screen and a driver must not hear "Afternoon" while still deciding
      // whether to consent. One source, one place to play it.
      if (frame.opening) {
        officerText.value = `${frame.opening}\n\n${frame.text}`;
        if (frame.opening_audio_url) {
          playInOrder([frame.opening_audio_url, frame.audio_url]);
          officerAudio.value = null; // played by the queue, not by the <audio> element
        }
      }
      // AI-CONTEXT: `audio_pending` means the voice is still being synthesized and will
      // arrive on its own frame. Without this branch the surface reads "no audio_url" as
      // "he has already spoken" and opens the mic on top of him — recording a driver
      // answering a question they have not heard yet. TRAPS 80 in the other direction:
      // the server grew a frame, so the surface has to grow the reading of it.
      if (Array.isArray(frame.thinking_audio_urls)) {
        thinkingUrls.value = frame.thinking_audio_urls;
        preloadThinkingNoises(frame.thinking_audio_urls);
      }
      awaitingAudio.value = Boolean(frame.audio_pending);
      // no audio to wait for means the question is already "said" — open the mic now
      if (!officerAudio.value && !awaitingAudio.value && handsFree.value) openMic();
    } else if (frame.type === "officer_audio") {
      // AI-CONTEXT: the voice, catching up with the line. A null url is a synthesis
      // that failed: the question is on the screen, so the driver is released to answer
      // it rather than left waiting for a sound that is never coming.
      awaitingAudio.value = false;
      // AI-CONTEXT: THE BYTES, IF THEY CAME. Measured from a client on the other side of
      // the world, fetching the mp3 from `audio_url` cost 1050ms AFTER this frame arrived
      // — a fresh DNS/TCP/TLS round trip and a signed-URL check for 17KB — so real time to
      // first speech was ~3.0s while every server number said 1.9s. The socket already
      // carried the sentence; now it carries the sound. `audio_url` remains the fallback,
      // and is still what replay and retention are built on.
      const inline = frame.audio_b64 ? `data:audio/mpeg;base64,${frame.audio_b64}` : null;
      if (inline || frame.audio_url) {
        officerAudio.value = inline || `${API_BASE}${frame.audio_url}`;
      } else if (handsFree.value && phase.value === Phase.OFFICER) {
        openMic();
      }
    } else if (frame.type === "scored") {
      heardText.value = frame.transcript || "";
      heardUnclear.value = Boolean(frame.review_needed);
      echoText.value = frame.echo || "";
      ackText.value = frame.ack || "";
      phase.value = Phase.HEARD;
      // AI-CONTEXT: THE STOP DOES NOT PAUSE TO BE MARKED. The officer says your own answer
      // back, THEN acknowledges — "Dallas." then "Okay." — and the next question follows
      // the moment he stops speaking. Queued rather than fired together: `Audio` plays
      // immediately, so both at once makes him talk over himself.
      //
      // What this REPLACED is the thing that made a conversation read as a quiz: a 3.2s
      // panel between every exchange with a transcript, a replay scrubber and a "Next
      // question" button. None of that happens at a window. The echo IS the receipt —
      // hearing "Dallas." back is how a driver knows they were understood — so the written
      // one only appears when the recogniser did NOT understand, which is the one case a
      // driver genuinely cannot infer from the officer's reply.
      cancelAutoAdvance();
      playInOrder([frame.echo_audio_url, frame.ack_audio_url]);
      // AI-CONTEXT: THE CLIENT NO LONGER ASKS FOR THE NEXT LINE. The server answers in the
      // same breath as the score, so asking would draw a SECOND question and show the
      // driver only one of them. The timer that remains is a stall guard, not the
      // mechanism: if no officer frame arrives at all, the stop must not sit there.
      advanceTimer = setTimeout(nextQuestion, STALL_GUARD_MS);
    } else if (frame.type === "complete") {
      // a stop ENDS — the officer lets you go rather than the screen simply changing
      closingText.value = frame.closing || "";
      const leave = () =>
        router.replace({ name: "roadside-result", params: { sessionId: route.params.sessionId } });
      if (frame.closing_audio_url) {
        const audio = new Audio(`${API_BASE}${frame.closing_audio_url}`);
        audio.onended = leave;
        audio.onerror = leave;
        officerText.value = frame.closing || officerText.value;
        phase.value = Phase.OFFICER;
        audio.play().catch(leave);
      } else {
        leave();
      }
    }
  };
});

// Q-4: the pause is an EDGE, watched rather than polled, so it fires mid-turn
watch(isDriving, (driving) => {
  if (driving) pause();
  else if (phase.value === Phase.PAUSED) askForNextLine();
});

async function openMic() {
  if (isDriving.value) return pause();
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    phase.value = Phase.MIC_DENIED;
    return;
  }
  phase.value = Phase.WAITING;
  recorder = new MediaRecorder(micStream);
  chunks = [];
  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.onstop = () => {
    releaseMic();
    sendAnswer();
  };
  recorder.start();

  listener = listenForSpeech(micStream, {
    onSpeechStart: () => {
      phase.value = Phase.RECORDING;
    },
    onSpeechEnd: () => stopRecording(),
    // AI-CONTEXT: heard nothing at all. Rather than sit forever with an open microphone,
    // the surface admits it and hands the driver the button — §12.4's rule that an error
    // states what happened AND what to do.
    onTimeout: () => {
      handsFree.value = false;
      listener = null;
      stopRecording();
      releaseMic();
      phase.value = Phase.OFFICER;
    },
  });
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

function officerFinishedSpeaking() {
  if (handsFree.value && phase.value === Phase.OFFICER) openMic();
}

// AI-CONTEXT: PRELOADED, which is the difference between this working and this being
// pointless. The clips exist to land in the silence the moment a driver stops talking —
// and an `Audio` constructed at that moment must first FETCH the file, so on a truck-stop
// connection the sound arrives somewhere in the middle of the gap it was meant to cover,
// or after it. They are fetched when the pool arrives instead, while the officer is still
// asking his question and nobody is waiting.
let thinkingClips = [];

function preloadThinkingNoises(urls) {
  thinkingClips = urls.map((url) => {
    const audio = new Audio(`${API_BASE}${url}`);
    audio.preload = "auto";
    audio.load();
    return audio;
  });
}

function makeThinkingNoise() {
  // a different one each time — the same noise four times in a stop is a machine again
  if (!thinkingClips.length) return;
  const clip = thinkingClips[Math.floor(Math.random() * thinkingClips.length)];
  try {
    clip.currentTime = 0;
  } catch {
    // a clip still loading has no seekable timeline yet; playing from wherever it is
    // beats not making a sound at all
  }
  clip.play().catch(() => {});
}

async function sendAnswer() {
  phase.value = Phase.SCORING;
  // AI-CONTEXT: BEFORE the upload, not after. The whole value of this sound is that it
  // lands in the silence a person leaves when they stop talking; playing it once the
  // request is away would put it a round trip late, in the middle of the gap it exists
  // to fill rather than at the start of it.
  makeThinkingNoise();
  const blob = new Blob(chunks, { type: "audio/webm" });
  const buffer = await blob.arrayBuffer();
  let binary = "";
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  send({ type: "answer", audio_b64: btoa(binary), driver_state: "IDLE" });
}

function nextQuestion() {
  // AI-CONTEXT: two timers can race here — the fallback ceiling and the post-speech beat.
  // Guarded on the phase rather than on the handles, because the cost of firing twice is
  // asking the officer for two lines and showing the driver only the second.
  if (phase.value !== Phase.HEARD) return;
  cancelAutoAdvance();
  heardText.value = "";
  heardUnclear.value = false;
  askForNextLine();
}

function end() {
  cancelAutoAdvance();
  send({ type: "bye" });
  router.replace({ name: "roadside-result", params: { sessionId: route.params.sessionId } });
}

onBeforeUnmount(() => {
  cancelAutoAdvance();
  stopRecording();
  releaseMic();
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
      <audio
        v-if="officerAudio"
        :src="officerAudio"
        autoplay
        class="session__audio"
        @ended="officerFinishedSpeaking"
      />

      <!-- AI-CONTEXT: THE STOP DOES NOT STOP TO MARK YOU. What stood here was a panel
           between every exchange — "HEARD", the transcript, a replay scrubber and a "Next
           question" button — and it is what made a working conversation read as a quiz.
           None of it happens at a real window.

           The officer's spoken echo ("Dallas.") is the receipt, so the WRITTEN one appears
           only when the recogniser did not understand — the one case a driver cannot infer
           from his reply, and the case Q-2 says must be stated rather than hidden. -->
      <!-- AI-CONTEXT: the ~2s where the officer is choosing and voicing his next line. The
           listening noise covers it for the ear; nothing covered it for the EYE, so a
           driver watching a still screen had no reason to believe anything was happening.
           Owner's request, logged as a decision — §22.2 reserves new component patterns. -->
      <SpeakingIndicator v-if="phase === Phase.SCORING" />

      <template v-if="phase === Phase.HEARD">
        <p v-if="echoText || ackText" class="session__ack">
          {{ [echoText, ackText].filter(Boolean).join(" ") }}
        </p>
        <p v-if="heardUnclear" class="session__unclear">
          {{ t("roadside.session.unclear") }}
          <span v-if="heardText" class="session__heard">{{ heardText }}</span>
        </p>
      </template>

      <template v-else>
      <p v-if="phase !== Phase.SCORING" class="session__status">
        {{ phase === Phase.RECORDING ? t("roadside.session.listening")
           : phase === Phase.WAITING ? t("roadside.session.speak_now")
           : handsFree ? t("roadside.session.speak_now")
           : t("roadside.session.tap_instead") }}
      </p>

      <button
        v-if="!handsFree || phase === Phase.RECORDING || phase === Phase.WAITING"
        class="session__mic"
        :data-live="phase === Phase.WAITING || phase === Phase.RECORDING"
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
.session__mic[aria-pressed="true"],
.session__mic[data-live="true"] {
  background: var(--flare-500);
}
/* what the officer said back, in his voice's place on the screen */
.session__ack {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  text-align: center;
}
/* only shown when the recogniser did NOT understand, so it reads as the officer's own
   aside rather than as a mark against the driver */
.session__unclear {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
  text-align: center;
}
.session__heard {
  display: block;
  color: var(--text-1);
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
