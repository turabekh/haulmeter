<!-- AI-CONTEXT: Cargo-condition capture (M5-FR2, PRD §8.5). A camera-first,
     one-decision-per-step guided sequence (S2 dock task, §202): trailer → seals
     → load blocking → reefer setpoint, each a hash-chained F4 photo. The driver
     just points and shoots; the app builds the evidence chain that protects them
     if cargo is disputed. Ties to the active stop (api.js activeStopId). Photos
     are transactional evidence (not the crowd write-queue); offline retry is the
     F12 evidence-envelope follow-up. -->
<script setup>
import { ref, computed, onMounted } from "vue";
import { ArrowLeft, Camera, Check, TriangleAlert } from "lucide-vue-next";
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
const { t } = useI18n();
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

// AI-CONTEXT: this is the worst of the six upload sites, because it is a SEQUENCE —
// a driver photographs a trailer corner, a seal and a load six times in a row, and every
// one of them read 3–8 MB to a base64 string on the main thread before anything moved.
// The freeze was therefore per shot, in the one flow that guarantees several.
// `addConditionPhoto` takes the File now and downscales it off-thread.
async function onCapture(event) {
  const file = event.target.files?.[0];
  event.target.value = ""; // allow re-picking the same file
  if (!file || busy.value) return;
  busy.value = true;
  lost.value = false;
  try {
    await addConditionPhoto(captureId.value, step.value, file, file.type || null);
    if (index.value + 1 >= sequence.value.length) done.value = true;
    else index.value += 1;
  } catch (err) {
    // §15.4: a capture that reached no storage at all must not look like a dead zone,
    // which is the one failure this flow already tolerates silently.
    if (err?.message === CAPTURE_NOT_STORED) lost.value = true;
    /* otherwise offline / failed — stay on this step; the driver retries (F12 follow-up) */
  }
  busy.value = false;
}
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
