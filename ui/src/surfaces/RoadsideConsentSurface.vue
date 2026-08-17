<!-- AI-CONTEXT: consent, and it is a SCREEN rather than a checkbox because of what it is
     consenting to (M15-FR3, E3 §E3.1.9).

     `start_session` checks consent FIRST, before anything else, and raises
     `ConsentRequired` — "asking after recording has begun is not consent". This surface is
     the half of that the driver sees. It states three things before the mic exists:

       · that their VOICE is recorded, and what for
       · that recordings are deleted after 30 days, while scores and progress stay
       · that the phone is about to ask for the microphone

     The 30-day line is a PROMISE THE PRODUCT ALREADY KEEPS — F6's retention class and its
     sweep delete the bytes and keep the row (entry 178). Saying it here is not marketing
     copy; it is the sentence that makes the sweep meaningful to the person it protects.

     "Not now" is a real option with equal weight in the layout. A consent screen whose
     decline is a faint link is not offering a choice, and the whole value of the record
     rests on the choice being real.

     DRIVING: `withdraws`. The agree action disappears at speed — consenting to be
     recorded is a decision, and Forbidden #11 bans interactive prompts in motion. -->
<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { openRoadsideSession } from "../core/api.js";
import Spinner from "../core/components/Spinner.vue";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const { isDriving } = useDriverState();

const busy = ref(false);
const failed = ref(false);

async function agree() {
  if (busy.value) return;
  busy.value = true;
  failed.value = false;
  try {
    // AI-CONTEXT: `consented: true` travels WITH the request that opens the session,
    // rather than being stored as a preference. Consent is given for a recording, not
    // once for all time, so it belongs to the thing being consented to.
    const body = await openRoadsideSession({
      scenario_version_id: route.params.scenarioId,
      consented: true,
      driver_state: "IDLE",
    });
    router.push({ name: "roadside-session", params: { sessionId: body.session_id } });
  } catch {
    failed.value = true;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="consent">
    <h1 class="consent__title">{{ t("roadside.consent.title") }}</h1>

    <ul class="consent__points">
      <li class="consent__point">{{ t("roadside.consent.recording") }}</li>
      <li class="consent__point">{{ t("roadside.consent.retention") }}</li>
      <li class="consent__point">{{ t("roadside.consent.mic") }}</li>
    </ul>

    <p v-if="failed" class="consent__failed" role="alert">{{ t("roadside.failed") }}</p>

    <p v-if="isDriving" class="consent__paused">
      {{ t("roadside.session.paused_driving") }}
      <span class="consent__hint">{{ t("roadside.session.paused_driving_hint") }}</span>
    </p>

    <div class="consent__actions">
      <button
        v-if="!isDriving"
        class="consent__agree"
        type="button"
        :disabled="busy"
        @click="agree"
      >
        <Spinner v-if="busy" />
        <span v-else>{{ t("roadside.consent.agree") }}</span>
      </button>
      <button class="consent__decline" type="button" @click="router.back()">
        {{ t("roadside.consent.decline") }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.consent {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding: var(--s-4);
}
.consent__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.consent__points {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
.consent__point,
.consent__paused,
.consent__failed {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.consent__paused {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.consent__hint {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
/* AI-CONTEXT: both actions carry the same weight and the same target size. A decline
   styled as a faint link is not a choice being offered. */
.consent__actions {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.consent__agree,
.consent__decline {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--touch-primary);
  padding: var(--s-3) var(--s-4);
  border-radius: var(--r-control);
  font-family: var(--font-sans);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  font-weight: var(--type-label-weight);
}
.consent__agree {
  border: 0;
  background: var(--accent-fill);
  color: var(--on-accent);
}
.consent__decline {
  border: 1px solid var(--line-1);
  background: var(--ink-2);
  color: var(--text-1);
}
</style>
