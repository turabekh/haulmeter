<!-- AI-CONTEXT: Comms ghostwriter (M11-FR3, PRD §8.11). Removes the tone problem
     that suppresses claims: the driver picks a tone (relationship -> firm) and
     says what happened; the app writes a firm, professional, English message and
     the driver ALWAYS approves before it goes (F8). Tone is a segmented control
     (§202 over a dropdown). Outbound is English regardless of input language
     (F15/M11-FR6). Live via api.js -> /voice/draft; offline shows a local draft. -->
<script setup>
import { ref } from "vue";
import { useI18n } from "../i18n.js";
import { draftMessage } from "../api.js";
import Spinner from "./Spinner.vue";

const { t } = useI18n();

const TONES = ["relationship", "neutral", "firm"];
const tone = ref("neutral");
const facts = ref("");
const draft = ref(null);
const copied = ref(false);
const copyFailed = ref(false);
const busy = ref(false);
// AI-CONTEXT: THE PRIMARY THAT DID NOTHING (§23 entry 233, owner-reported).
//
// `write()` opened with a bare `if (!f) return`, and "Write it" is a full-weight Primary
// CTA sitting directly under the empty box. So the most obvious gesture on this sheet —
// open it, tap the big blue button — produced no request, no message and no change of
// any kind. Measured in the running app before this was touched: 0 requests, 0 DOM
// change. To a driver that is not a validation rule, it is a broken app, and it is the
// same family as entry 218's "Approve & send" whose handler was one assignment.
//
// §7's form rule wants every error "inline, specific, and next to its field", and §15.4
// asks the driver to act only when only they can — which is exactly this case: nobody
// else can say what happened. So the button stays enabled and ANSWERS. A disabled
// Primary would have been the same silence wearing a greyer coat.
const missing = ref(false);

async function write() {
  const f = facts.value.trim();
  if (!f) {
    missing.value = true;
    return;
  }
  missing.value = false;
  busy.value = true;
  try {
    const res = await draftMessage({ kind: "detention notice", facts: f, tone: tone.value });
    draft.value = res.draft;
  } catch {
    // offline: a local English stub so the flow still demonstrates (F9 seam)
    draft.value = `[draft] A ${tone.value} detention notice, in English. Facts: ${f}`;
  }
  busy.value = false;
}

// AI-CONTEXT: THE BUTTON SAID "Approve & send", THE SCREEN THEN SAID "Sent", AND
// NOTHING LEFT THE SYSTEM (§23 entry 222).
//
// The whole handler was `sent.value = true`, under a comment claiming "the actual send
// is the F8 counterparty seam" — which it never called. So a driver chasing a broker for
// unpaid detention read the word **Sent** and waited on a message that had never been
// written to anything. The validation law in CLAUDE.md names exactly this: "nothing
// 'sends' that didn't actually leave the system."
//
// AUTO-SENDING IS NOT THE FIX, and that is a logged decision rather than a preference:
// entry 142 routed chasing through this sheet precisely so "the driver reads and sends
// the message themselves — no second automatic mail beside the dunning job's own
// cadence". So the honest version of this control is the one that hands the driver the
// words. It copies, and it says it copied.
async function copyDraft() {
  copyFailed.value = false;
  try {
    await navigator.clipboard.writeText(draft.value);
    copied.value = true;
  } catch {
    // a denied permission or an insecure context — the draft stays on screen and the
    // driver is told to select it, rather than being told it went somewhere
    copyFailed.value = true;
  }
}
</script>

<template>
  <div class="ghost">
      <div class="ghost__tones" role="group" :aria-label="t('ghost.title')">
        <button
          v-for="tn in TONES"
          :key="tn"
          class="tone"
          :class="{ 'tone--on': tone === tn }"
          type="button"
          @click="tone = tn"
        >
          {{ t(`ghost.tone.${tn}`) }}
        </button>
      </div>

      <label class="field">
        <span class="field__label">{{ t("ghost.facts") }}</span>
        <textarea
          v-model="facts"
          class="field__input"
          rows="3"
          :placeholder="t('ghost.facts_placeholder')"
          :aria-invalid="missing ? 'true' : undefined"
          :aria-describedby="missing ? 'ghost-facts-missing' : undefined"
          @input="missing = false"
        ></textarea>
        <!-- next to its field, which is where §7 puts an error -->
        <span v-if="missing" id="ghost-facts-missing" class="field__error" role="alert">
          {{ t("ghost.facts_required") }}
        </span>
      </label>

      <p v-if="draft" class="draft">
        <span class="draft__badge">{{ t("ghost.english") }}</span>
        <span class="draft__body">{{ draft }}</span>
      </p>

      <button v-if="!draft" class="cta" type="button" :disabled="busy" @click="write">
        <Spinner v-if="busy" />
        {{ busy ? t("busy.working") : t("ghost.draft") }}
      </button>
      <button v-else class="cta" type="button" @click="copyDraft">{{ t("ghost.copy") }}</button>
      <p v-if="copied" class="sent">{{ t("ghost.copied") }}</p>
      <p v-if="copyFailed" class="sent">{{ t("ghost.copy_failed") }}</p>
  </div>
</template>

<style scoped>
.ghost {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.ghost__tones {
  display: flex;
  gap: var(--s-2);
}
.tone {
  flex: 1 1 0;
  min-height: 48px;
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: transparent;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.tone--on {
  background: var(--accent-fill);
  color: var(--on-accent);
  border-color: var(--accent-fill);
}
.field__error {
  color: var(--flare-500);
  font-size: var(--type-caption-size);
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.field__label {
  font-size: var(--type-label-size);
  color: var(--text-2);
}
.field__input {
  width: 100%;
  padding: var(--s-3);
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
  font-family: inherit;
  resize: vertical;
}
.draft {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-3);
  border-radius: var(--r-card);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
}
.draft__badge {
  align-self: flex-start;
  padding: 1px var(--s-2);
  border-radius: var(--r-pill);
  background: var(--ledger-500);
  color: var(--on-accent);
  font-size: var(--type-caption-size);
}
.draft__body {
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.cta {
  width: 100%;
  min-height: 56px;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta:disabled {
  opacity: 0.6;
}
.sent {
  margin: 0;
  padding: var(--s-4) 0;
  text-align: center;
  color: var(--ledger-500);
  font-size: var(--type-title-size);
  font-weight: 500;
}
</style>
