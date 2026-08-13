<!-- AI-CONTEXT: Cargo-condition capture (M5-FR2, PRD §8.5). A camera-first,
     one-decision-per-step guided sequence (S2 dock task, §202): trailer → seals
     → load blocking → reefer setpoint, each a hash-chained F4 photo. The driver
     just points and shoots; the app builds the evidence chain that protects them
     if cargo is disputed. Ties to the active stop (api.js activeStopId). Photos
     are transactional evidence (not the crowd write-queue); offline retry is the
     F12 evidence-envelope follow-up. -->
<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { ArrowLeft, Camera, Check, TriangleAlert, Clock } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import {
  activeStopId,
  startConditionCapture,
  addConditionPhoto,
  CAPTURE_NOT_STORED,
} from "../core/api.js";

const router = useRouter();
const { t, has } = useI18n();
const { isDriving } = useDriverState();

const sequence = ref([]);
const index = ref(0);
const captureId = ref(null);
const done = ref(false);
const busy = ref(false);
const noStop = ref(false);
const lost = ref(false);

onMounted(async () => {
  if (!activeStopId.value) {
    noStop.value = true;
    return;
  }
  try {
    const res = await startConditionCapture(activeStopId.value);
    captureId.value = res.capture_id;
    sequence.value = res.sequence;
  } catch {
    noStop.value = true; // offline / no session — can't start the chain
  }
});

const step = computed(() => sequence.value[index.value]);

/* AI-CONTEXT: this is the worst of the six upload sites, because it is a SEQUENCE — a
 * driver photographs a trailer corner, a seal and a load six times in a row, and every one
 * of them read 3–8 MB to a base64 string on the main thread before anything moved. The
 * freeze was therefore per shot, in the one flow that guarantees several.
 * `addConditionPhoto` takes the File now and downscales it off-thread.
 *
 * AI-CONTEXT: §15.1's "queued items show a subtle pending glyph", built for the first
 * time — and it is the honest version of the optimistic update the owner asked for.
 *
 * A photograph the driver has just taken EXISTS: it is on their phone, in their hand.
 * Rendering it immediately is not a guess about the server, it is a true statement about
 * a local fact, which is why this is allowed where an optimistic write is not. §23 entry
 * 136 settled that boundary already — "a card vanishing while the write sits in a queue
 * would tell a driver their decision is recorded when it is not" — so what the glyph
 * carries is exactly the part that is still uncertain: whether it has reached us yet.
 *
 * Before this, a queued photo appeared NOWHERE. The only sync signal in the product is a
 * global count on the status strip, so a driver walking a six-shot sequence in a dead
 * zone watched a step counter advance past photographs they had no evidence existed. */
const shots = ref([]);
// AI-CONTEXT: an id, because IDENTITY IS NOT USABLE HERE. `ref([])` is deeply reactive,
// so reading `shots.value` hands back proxies — `s !== shot` compares a proxy against the
// raw object it wraps and is therefore true for every element. Removing a lost capture by
// identity silently removed nothing, and the strip went on showing a photograph the
// product did not have. Caught by the test, not by reading it.
let _shotSeq = 0;

// the same guarded lookup EvidenceSurface and LoadRecordSurface use: a dynamic key
// family cannot be checked statically, and an invented one throws inside an `alt` and
// kills the whole render (§23 entry 137, HANDOFF-123 §4.8).
function photoLabel(prompt) {
  if (!prompt) return t("claim.ev_photo");
  const key = `cond.step.${prompt}`;
  return has(key) ? t(key) : prompt;
}

// §16: the glyph is `aria-hidden`, so the STATE has to reach a screen reader through the
// only text this element has. A visual-only signal is not a signal.
function shotLabel(shot) {
  const label = photoLabel(shot.prompt);
  return shot.pending ? `${label} — ${t("docs.cap_queued")}` : label;
}

async function onCapture(event) {
  const file = event.target.files?.[0];
  event.target.value = ""; // allow re-picking the same file
  if (!file || busy.value) return;
  busy.value = true;
  lost.value = false;

  // shown BEFORE the await, from the local file: this is the instant feedback, and it
  // asserts nothing about the server
  const shot = { id: ++_shotSeq, url: URL.createObjectURL(file), prompt: step.value, pending: true };
  shots.value = [...shots.value, shot];

  try {
    const res = await addConditionPhoto(captureId.value, step.value, file, file.type || null);
    // `queued` is the server saying nothing yet — the glyph stays until it does
    shot.pending = res?.queued === true;
    shots.value = [...shots.value];
    if (index.value + 1 >= sequence.value.length) done.value = true;
    else index.value += 1;
  } catch (err) {
    // §15.4: a capture that reached no storage at all must not look like a dead zone,
    // which is the one failure this flow already tolerates silently. The thumbnail comes
    // back off the strip — leaving it there would be the product asserting it holds a
    // photograph it does not have.
    shots.value = shots.value.filter((s) => s.id !== shot.id);
    try {
      URL.revokeObjectURL(shot.url);
    } catch {
      /* nothing to revoke */
    }
    if (err?.message === CAPTURE_NOT_STORED) lost.value = true;
    /* otherwise offline / failed — stay on this step; the driver retries (F12 follow-up) */
  }
  busy.value = false;
}

onBeforeUnmount(() => {
  for (const shot of shots.value) {
    try {
      URL.revokeObjectURL(shot.url);
    } catch {
      /* nothing to revoke */
    }
  }
});
</script>

<template>
  <div class="cond">
    <header class="cond__head">
      <button class="back" type="button" aria-label="Back" @click="router.back()">
        <ArrowLeft :size="24" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="cond__title">{{ t("cond.title") }}</h1>
    </header>

    <p v-if="noStop" class="muted">{{ t("load.start") }}</p>

    <template v-else-if="done">
      <section class="done">
        <div class="done__mark" aria-hidden="true"><Check :size="40" :stroke-width="2.5" /></div>
        <span class="done__text">{{ t("cond.done") }}</span>
      </section>
      <button class="cta" type="button" @click="router.push('/load')">{{ t("booking.done") }}</button>
    </template>

    <template v-else-if="step">
      <p class="cond__progress">{{ t("cond.step") }} {{ index + 1 }} {{ t("cond.of") }} {{ sequence.length }}</p>
      <h2 class="cond__step">{{ t(`cond.step.${step}`) }}</h2>

      <!-- AI-CONTEXT: SM-3, and this screen had no DRIVING behaviour at all.
           `capture="environment"` opens the rear camera directly, and §22.3's
           DRIVING box was never filled for this surface — while the route
           `/protection/condition` carries no guard of its own (the router has only
           an auth `beforeEach`), so a deep link, the back button or a §13.5
           notification could open a camera at speed. Forbidden #11.

           Same shape as EvidenceSurface: what you can READ stays — the step and the
           progress are still there — and only the acting stops. The progress is
           already durable server-side, so saying so is a fact, not a reassurance. -->
      <!-- §15.4: the step does not advance, so without this the driver taps the shutter,
           nothing visibly happens, and the only reading available is "the camera is
           broken". It clears on the next attempt. -->
      <p v-if="lost" class="cond__lost" role="alert">
        <TriangleAlert :size="18" :stroke-width="2" aria-hidden="true" />
        {{ t("docs.cap_lost") }}
      </p>

      <!-- AI-CONTEXT: §15.1's pending glyph, per item. `Clock` in `--text-3` is calm,
           not red: waiting for signal is a MODE, not an error, and the same restraint
           the status strip already uses ("Offline — everything saves to your phone").
           The alt text carries the state too, because a glyph is not a signal to
           anyone using a screen reader (§16). -->
      <ul v-if="shots.length" class="shots" :aria-label="t('evidence.photos')">
        <li v-for="s in shots" :key="s.id" class="shots__item">
          <img class="shots__img" :src="s.url" :alt="shotLabel(s)" decoding="async" />
          <span v-if="s.pending" class="shots__pending" :title="t('docs.cap_queued')">
            <Clock :size="14" :stroke-width="2" aria-hidden="true" />
          </span>
        </li>
      </ul>

      <p v-if="isDriving" class="muted">{{ t("cond.driving") }}</p>
      <label v-else class="shoot">
        <Camera :size="40" :stroke-width="2" aria-hidden="true" />
        <span>{{ t("cond.take") }}</span>
        <input
          class="shoot__input"
          type="file"
          accept="image/*"
          capture="environment"
          :disabled="busy"
          @change="onCapture"
        />
      </label>
    </template>
  </div>
</template>

<style scoped>
.cond {
  display: flex;
  flex-direction: column;
  padding: var(--s-4);
  min-height: 100%;
}
.cond__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-bottom: var(--s-4);
}
.back {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-1);
}
.cond__title {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.cond__progress {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.cond__step {
  margin: var(--s-1) 0 var(--s-5);
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
/* the captured strip. Composed from LoadRecordSurface's `.shots` treatment rather than
   invented (§22.2: compose from what exists) — same 72 dp square, same radius, same
   `--ink-2` resting fill. */
.shots {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: 0 0 var(--s-4);
  padding: 0;
}
.shots__item {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: var(--r-control);
  overflow: hidden;
  background: var(--ink-2, var(--line-1));
}
.shots__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
/* §15.1 "a subtle pending glyph": calm, not red — waiting for signal is a mode, not a
   failure. Sat on a scrim so it stays legible over a bright dock photograph. */
.shots__pending {
  position: absolute;
  right: 2px;
  bottom: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: var(--r-pill);
  background: var(--ink-0);
  color: var(--text-3);
}

/* §15.4 / §8: `flare` is the error grade. Sits above the shutter so it is read on the
   way back to the control the driver is about to use again. */
.cond__lost {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0 0 var(--s-4);
  color: var(--flare-500);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
/* camera-first: one giant target (S2 gloves, §6.5) */
.shoot {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  min-height: 200px;
  border-radius: var(--r-card);
  border: 2px dashed var(--line-1);
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
  cursor: pointer;
}
.shoot__input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  overflow: hidden;
}
.done {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-6) 0;
}
.done__mark {
  width: 72px;
  height: 72px;
  border-radius: var(--r-pill);
  background: var(--ledger-500);
  color: var(--on-accent);
  display: flex;
  align-items: center;
  justify-content: center;
}
.done__text {
  font-size: var(--type-title-size);
  font-weight: 500;
}
.muted {
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.cta {
  width: 100%;
  min-height: 56px;
  margin-top: auto;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
</style>
