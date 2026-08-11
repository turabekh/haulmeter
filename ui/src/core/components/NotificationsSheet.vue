<!-- AI-CONTEXT: §23 entry 102 — the surface F8 never had.

     F8 has decided tiers, budgets, quiet hours and classes since it shipped and every
     decision ended in a row nobody could read. §23 entry 429 caught the miniature —
     "nothing may be filed P2 until a surface renders the digest" — and the general
     case was larger: nothing rendered ANY of it.

     Rules this list must not soften:
     · §13.5 — every notification deep-links to the exact screen and state it
       describes, never a tab root. The link is the server's, carried down rather than
       re-derived here, so push and inbox can never disagree about where a thing is.
     · A SUPPRESSED notification is shown, and says it was held. §13.1 caps unprompted
       INTERRUPTIONS; a driver who opens this list is asking, not being interrupted.
       Quiet hours defer — they do not destroy — and a list that hid what it deferred
       would turn a considerate rule into a lossy one.
     · "Nothing yet" is a real state and says so plainly (§15.3), because an empty
       inbox and a broken inbox look identical otherwise — which is exactly how this
       whole area went unnoticed for as long as it did.
     · Time is relative and coarse (`ageLabel`), the same vocabulary the map uses for
       crowd freshness. One wording everywhere (§14.3).

     DRIVING: this is reached from More, which is an S3 surface — a driver is not
     browsing an inbox at speed, and §13.4 already routes in-motion notifications to
     audio summaries rather than to a list. -->
<script setup>
import { computed, ref, onMounted } from "vue";
import { Bell, Clock } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { ageLabel } from "../presentation.js";
import { pushSupported, permissionState, isEnabled, enable, disable } from "../push.js";
import Spinner from "./Spinner.vue";
import {
  fetchNotificationClasses,
  setNotificationClass,
  fetchNotificationPrefs,
  setQuietHours,
} from "../api.js";

const props = defineProps({
  notifications: { type: Array, default: () => [] },
  now: { type: Number, default: () => Date.now() },
});
const emit = defineEmits(["open"]);
const { t } = useI18n();

// AI-CONTEXT: alerts are enrolled HERE and nowhere else (§23 entry 111). The browser's
// permission prompt is ONE-SHOT — a "no" is permanent for the origin — so asking on
// first launch would spend a driver's only chance before they know what we would send.
// §21.8 forbids exactly that. This sheet is the one place a driver has already come to
// ask about notifications, so it is the one place the offer is honest.
const pushState = ref("idle"); // idle | on | denied | unsupported | unconfigured | error
const busy = ref(false);

async function refreshPushState() {
  if (!pushSupported()) {
    pushState.value = "unsupported";
    return;
  }
  if (permissionState() === "denied") {
    pushState.value = "denied"; // cannot be re-asked from here; the browser owns it now
    return;
  }
  pushState.value = (await isEnabled()) ? "on" : "idle";
}
onMounted(refreshPushState);

async function togglePush() {
  busy.value = true;
  try {
    const result = pushState.value === "on" ? await disable() : await enable();
    if (result.ok) pushState.value = result.reason === "enabled" ? "on" : "idle";
    else pushState.value = result.reason;
  } finally {
    busy.value = false;
  }
}

// AI-CONTEXT: the lot-status prompt's switch (§23 entry 114, owner-approved placement).
//
// This is the ONLY way a driver can turn the prompt on. `dispatch` refuses an opt-in
// class before any tier logic and the class defaults to off, so until this existed the
// feature was suppressed `not_opted_in` for everyone — the third defect in one feature
// where the rules were right and nothing could reach them.
//
// Only this class is offered here. `vendor_alert` already has its own control in More,
// and `protection_gap` is ON by default for a stated reason — a driver cannot opt in to
// a warning they have never seen — so a switch for it is a separate decision.
const PROMPT_CLASS = "lot_status_prompt";
const promptOn = ref(null); // null until known: a switch must not render a guess
const promptBusy = ref(false);

async function refreshClasses() {
  try {
    const data = await fetchNotificationClasses();
    const row = (data.classes || []).find((c) => c.key === PROMPT_CLASS);
    promptOn.value = row ? row.opted_in : null;
  } catch {
    promptOn.value = null; // offline or no session — say nothing rather than "off"
  }
}
onMounted(refreshClasses);

async function togglePrompt() {
  promptBusy.value = true;
  const next = !promptOn.value;
  try {
    const result = await setNotificationClass(PROMPT_CLASS, next);
    promptOn.value = result.opted_in;
  } catch {
    /* leave the switch where it was: §11.7 forbids showing a choice that did not land */
  } finally {
    promptBusy.value = false;
  }
}

// AI-CONTEXT: quiet hours (§13.3, §23 entry 115) — the half of that clause that had no
// surface, next to the half that had no zone.
//
// §13.3 is "default 22:00-06:00 local (driver-adjustable)". Neither was true: the server
// measured the window in UTC because nothing ever sent it a zone, and nothing could move
// the window either. The zone is now sent automatically on sign-in and is shown here
// rather than hidden, because a driver whose phone reports the wrong one deserves to see
// what we are using. There is no picker: a 400-entry IANA list on a 360 dp screen is the
// wrong control, and the browser already knows the answer.
const prefs = ref(null); // null until known — no control renders a guess
const quietBusy = ref(false);

async function refreshPrefs() {
  try {
    prefs.value = await fetchNotificationPrefs();
  } catch {
    prefs.value = null; // offline or no session
  }
}
onMounted(refreshPrefs);

async function onQuietChange() {
  if (!prefs.value) return;
  quietBusy.value = true;
  try {
    prefs.value = await setQuietHours(prefs.value.quiet_start, prefs.value.quiet_end);
  } catch {
    await refreshPrefs(); // never leave a window on screen that the server did not take
  } finally {
    quietBusy.value = false;
  }
}

// start == end can contain no hour, because `in_quiet_hours` compares start <= t < end.
// That is a real choice a driver can make, and saying so is cheaper than letting someone
// discover it by setting both to the same time and wondering why nothing is ever held.
const alwaysOn = computed(
  () => !!prefs.value && prefs.value.quiet_start === prefs.value.quiet_end,
);

const rows = computed(() =>
  props.notifications.map((n) => ({
    ...n,
    unread: !n.read_at,
    // the server said why it held this one back; the list repeats it rather than
    // rendering a silent gap the driver has to interpret
    held: n.status === "suppressed",
    age: n.created_at ? ageLabel(new Date(n.created_at).getTime(), props.now) : null,
  })),
);
</script>

<template>
  <div class="notif">
    <p v-if="!rows.length" class="notif__empty">{{ t("notifications.empty") }}</p>

    <ul v-else class="notif__list">
      <li v-for="n in rows" :key="n.id">
        <button
          class="notif__row"
          :class="{ 'notif__row--unread': n.unread }"
          type="button"
          @click="emit('open', n)"
        >
          <span class="notif__head">
            <Bell v-if="n.unread" :size="16" :stroke-width="2.5" aria-hidden="true" />
            <span class="notif__title">{{ n.title }}</span>
          </span>
          <span class="notif__body">{{ n.body }}</span>
          <span class="notif__meta">
            <span v-if="n.age" class="notif__age">{{ n.age }}</span>
            <span v-if="n.held" class="notif__held">
              <Clock :size="14" :stroke-width="2.5" aria-hidden="true" />
              {{ t("notifications.held") }}
            </span>
          </span>
        </button>
      </li>
    </ul>

    <!-- The offer says what will be sent BEFORE the browser prompt appears, because
         the prompt itself cannot say it. Turning it off is one tap, like turning it
         on (§21.8). -->
    <section class="push">
      <p class="push__what">{{ t("push.what") }}</p>
      <button
        v-if="['idle', 'on', 'error'].includes(pushState)"
        class="push__cta"
        type="button"
        :disabled="busy"
        @click="togglePush"
      >
        <Spinner v-if="busy" />
        {{ busy
          ? t("busy.saving")
          : pushState === "on" ? t("push.disable") : t("push.enable") }}
      </button>
      <p v-else class="push__why">{{ t(`push.why_${pushState}`) }}</p>
      <p v-if="pushState === 'error'" class="push__why">{{ t("push.why_error") }}</p>
    </section>

    <!-- What we ASK, as opposed to how we reach you. The offer states the cost before
         the switch, the same rule the push block above follows: this one asks the driver
         for labour, and §21.8 forbids helping ourselves to it. -->
    <!-- `prompt-class` is the §22.3 harness's handle. It borrows the push block's shape
         deliberately — same tokens, same full-width control, no new component pattern —
         but it needs its own selector, because a state the harness cannot PROVE it
         rendered is a state that ships unmeasured. -->
    <section v-if="promptOn !== null" class="push prompt-class">
      <p class="push__what">{{ t("prompts.lot_what") }}</p>
      <button class="push__cta" type="button" :disabled="promptBusy" @click="togglePrompt">
        <Spinner v-if="promptBusy" />
        {{ promptBusy ? t("busy.saving") : promptOn ? t("prompts.lot_off") : t("prompts.lot_on") }}
      </button>
    </section>

    <!-- §13.3, the driver-adjustable half. The zone is stated rather than chosen: the
         browser knows it and a driver should not have to configure their way out of a
         bug. `quiet` is the harness's handle — this row renders only after the server
         answers, so a state it cannot prove it rendered ships unmeasured. -->
    <section v-if="prefs" class="push quiet">
      <p class="push__what">{{ t("quiet.what") }}</p>
      <div class="quiet__row">
        <label class="quiet__field">
          <span class="quiet__label">{{ t("quiet.from") }}</span>
          <input
            v-model="prefs.quiet_start"
            class="field__input quiet__input"
            type="time"
            :disabled="quietBusy"
            @change="onQuietChange"
          />
        </label>
        <label class="quiet__field">
          <span class="quiet__label">{{ t("quiet.to") }}</span>
          <input
            v-model="prefs.quiet_end"
            class="field__input quiet__input"
            type="time"
            :disabled="quietBusy"
            @change="onQuietChange"
          />
        </label>
      </div>
      <p class="push__why">{{ alwaysOn ? t("quiet.always") : t("quiet.zone", { zone: prefs.timezone }) }}</p>
    </section>
  </div>
</template>

<style scoped>
.push {
  margin-top: var(--s-4);
  padding-top: var(--s-4);
  border-top: 1px solid var(--line-1);
}
.push__what {
  margin: 0 0 var(--s-3);
  font-size: var(--type-caption-size);
  color: var(--text-2);
}
.push__cta {
  width: 100%;
  min-height: var(--touch-min);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--text-1);
  font-size: var(--type-label-size);
}
.push__cta:disabled {
  opacity: 0.5;
}
.push__why {
  margin: 0;
  font-size: var(--type-caption-size);
  color: var(--text-2);
}
/* §202 forms, matching AuthSurface's `.field__input` declaration rather than inventing
   a second look: 56 dp clears §6.5's 48 dp glove spec with room, and the two fields wrap
   instead of shrinking so +40% under xx-XL grows the row rather than the target. */
.quiet__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-3);
  margin-bottom: var(--s-3);
}
.quiet__field {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  flex: 1 1 8rem;
  min-width: 0;
}
.quiet__label {
  font-size: var(--type-caption-size);
  color: var(--text-2);
}
.quiet__input {
  min-height: 56px;
  padding: 0 var(--s-3);
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
  width: 100%;
}
.quiet__input:disabled {
  opacity: 0.5;
}
.notif__empty {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.notif__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.notif__row {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  width: 100%;
  min-height: 64px;
  padding: var(--s-3);
  text-align: left;
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
}
.notif__row--unread {
  border-color: var(--marker-500);
}
.notif__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  color: var(--text-1);
  font-size: var(--type-label-size);
  font-weight: 600;
}
.notif__title {
  min-width: 0;
}
.notif__body {
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.notif__meta {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.notif__age {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.notif__held {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
}
</style>
