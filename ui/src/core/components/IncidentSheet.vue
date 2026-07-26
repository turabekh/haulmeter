<!-- AI-CONTEXT: Incident capture (M5-FR4, PRD §8.5) — a two-tap protection log
     for when something goes wrong at a stop (damage, refusal, unsafe site,
     theft). Pick a kind chip + an optional note; it files to /protection/incident
     which opens an F4 evidence log — the record that protects the driver if it's
     later disputed. A queued write (F12): taken in a dead zone it saves and
     replays exactly-once (idempotency key). One decision per step (§202); calm
     confirmation, never alarming (§15.3). Emits `filed` so the host can close. -->
<script setup>
import { ref } from "vue";
import { ShieldAlert, Check } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { fileIncident } from "../api.js";

const emit = defineEmits(["filed"]);
const { t } = useI18n();

const KINDS = ["damage", "refused", "unsafe", "theft", "other"];
const kind = ref(null);
const note = ref("");
const busy = ref(false);
const done = ref(null); // "filed" | "queued" once submitted

async function submit() {
  if (!kind.value || busy.value) return;
  busy.value = true;
  // the server's id for what was filed. It was dropped on the floor, so the pack it
  // produced could never be opened again — carrying it is what gives FR4 a route.
  // A queued incident has no id yet; the caller must handle that rather than assume.
  let incidentId = null;
  try {
    const res = await fileIncident(kind.value, note.value.trim() || null);
    done.value = res && res.queued ? "queued" : "filed";
    incidentId = res?.incident_id ?? null;
  } catch {
    done.value = "queued"; // treat a server hiccup as saved-locally; never lose it
  } finally {
    busy.value = false;
    emit("filed", { kind: kind.value, state: done.value, incident_id: incidentId });
  }
}
</script>

<template>
  <div class="incident">
    <div v-if="done" class="confirm">
      <Check :size="24" :stroke-width="2" class="confirm__ok" aria-hidden="true" />
      <p class="confirm__text">
        {{ done === "queued" ? t("incident.queued") : t("incident.filed") }}
      </p>
    </div>

    <template v-else>
      <div class="lead">
        <ShieldAlert :size="18" :stroke-width="2" class="lead__icon" aria-hidden="true" />
        <span class="lead__text">{{ t("incident.lead") }}</span>
      </div>

      <div class="chips" role="radiogroup" :aria-label="t('incident.kind')">
        <button
          v-for="k in KINDS"
          :key="k"
          type="button"
          class="chip"
          :class="{ 'chip--on': kind === k }"
          role="radio"
          :aria-checked="kind === k"
          @click="kind = k"
        >
          {{ t(`incident.k_${k}`) }}
        </button>
      </div>

      <label class="field">
        <span class="field__label">{{ t("incident.note") }}</span>
        <textarea
          v-model="note"
          class="field__input"
          rows="3"
          :placeholder="t('incident.note_hint')"
        ></textarea>
      </label>

      <button class="cta" type="button" :disabled="!kind || busy" @click="submit">
        {{ t("incident.file") }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.incident {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.lead {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.lead__icon {
  color: var(--flare-500);
  flex: none;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}
.chip {
  min-height: 44px;
  padding: 0 var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-pill);
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-label-size);
}
.chip--on {
  border-color: var(--shield-500);
  color: var(--shield-500);
  background: var(--shield-050, var(--ink-1));
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.field__label {
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.field__input {
  width: 100%;
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
  font-family: inherit;
  resize: vertical;
}
.cta {
  min-height: 56px;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta:disabled {
  opacity: 0.5;
}
.confirm {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-4) 0;
  text-align: center;
}
.confirm__ok {
  color: var(--ledger-500);
}
.confirm__text {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-body-size);
}
</style>
