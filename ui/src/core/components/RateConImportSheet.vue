<!-- AI-CONTEXT: §10.2's empty-state action — "Add a load" by rate-con photo.

     PRD §108 calls this the PRIMARY way a load is created, and it has never existed:
     F6 stored `rate_con`, F9 parsed documents, and F5 took parsed terms, but the only
     place the three were ever joined was the Foundation e2e test. This tab offered a
     four-field manual form in its place.

     THE CONFIRM STEP IS THE FEATURE. M4-FR4 specifies it, and the reason is that a
     machine read of a photographed contract is a proposal — the driver is the only
     one who can see both the paper and the screen. Every parsed value lands in an
     editable field rather than being written straight into a load.

     Two honesty rules, both §11.7 discipline:
     · The screen NAMES WHO IS SPEAKING. A parsed value is labelled as read from the
       rate con, never presented as simply true — the same rule as "Vendor says halal"
       and "prompted: seals".
     · A term the contract is SILENT on is stated as silence, not as a zero. "Silent
       on detention" is a fact about the paper worth learning before accepting a load,
       not after four hours at a dock — and a driver who saw "$0/h" would believe the
       contract said so.

     When the parse fails — the state this stack runs in with no model key — the
     document is still filed and the manual form takes over. Inventing plausible terms
     would put a number the contract never contained behind a detention claim. -->
<script setup>
import { ref, reactive, computed } from "vue";
import { Camera, TriangleAlert, Check } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { importRateCon, createActiveLoad } from "../api.js";

const emit = defineEmits(["created"]);
const { t } = useI18n();

const file = ref(null);
const preview = ref(null);
const busy = ref(false);
// null = nothing read yet; otherwise the server's draft
const draft = ref(null);
const documentId = ref(null);
const chosenFacility = ref(null);
const failed = ref(false);

// the confirm form. Every field is editable — a parse is a proposal.
const form = reactive({
  facility: "",
  broker: "",
  reference: "",
  freeMin: "",
  rateHr: "",
});

const readable = computed(() => !!draft.value?.readable);
const candidates = computed(() => draft.value?.facility_candidates ?? []);
const silentOn = computed(() => draft.value?.silent_on ?? []);

function onFile(event) {
  const f = event.target.files?.[0];
  if (!f) return;
  file.value = f;
  preview.value = URL.createObjectURL(f);
}

function b64(f) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1]);
    r.onerror = reject;
    r.readAsDataURL(f);
  });
}

async function read() {
  if (!file.value || busy.value) return;
  busy.value = true;
  try {
    const res = await importRateCon({
      contentB64: await b64(file.value),
      filename: file.value.name,
      contentType: file.value.type,
    });
    draft.value = res;
    documentId.value = res.document_id;
    const p = res.parsed ?? {};
    form.facility = p.receiver_name ?? "";
    form.reference = p.reference_number ?? "";
    form.freeMin = p.free_time_minutes ?? "";
    form.rateHr = p.detention_rate_cents_per_hour
      ? Math.round(p.detention_rate_cents_per_hour / 100)
      : "";
    // NOTHING is pre-selected, and that is measured rather than cautious: pg_trgm
    // scores an unrelated "Dallas Distribution Center" at 0.645 against "ACME
    // Distribution Center" and the correct "ACME Distribution Ctr" at 0.679, so no
    // threshold tells them apart. A wrong match costs one tap to notice; a wrong
    // default costs a load attached to a dock the driver never visited.
    chosenFacility.value = null;
  } catch {
    // the document may or may not have been filed; either way the driver types it
    failed.value = true;
    draft.value = { readable: false };
  } finally {
    busy.value = false;
  }
}

async function create() {
  busy.value = true;
  try {
    await createActiveLoad({
      facility_name: form.facility || "Receiver",
      lat: 32.7767,
      lon: -96.797,
      counterparty: form.broker || "Broker",
      reference_number: form.reference || null,
      free_time_minutes: Number(form.freeMin) || null,
      rate_cents_per_hour: form.rateHr ? Math.round(Number(form.rateHr) * 100) : null,
      facility_id: chosenFacility.value,
      rate_con_document_id: documentId.value,
    });
    emit("created");
  } catch {
    /* leave the form as typed — losing a confirmed rate con to a failed request
       would make the driver photograph it again */
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="rc">
    <!-- step 1: the photo -->
    <template v-if="!draft">
      <p class="rc__lead">{{ t("load.rc_lead") }}</p>
      <label class="rc__field">
        <span class="rc__label">{{ t("load.rc_photo") }}</span>
        <input class="rc__input" type="file" accept="image/*,application/pdf" @change="onFile" />
      </label>
      <img v-if="preview" :src="preview" class="rc__preview" :alt="t('load.rc_photo')" />
      <button class="rc__cta" type="button" :disabled="!file || busy" @click="read">
        <Camera :size="18" :stroke-width="2" aria-hidden="true" />
        {{ busy ? t("load.rc_reading") : t("load.rc_read") }}
      </button>
    </template>

    <!-- step 2: confirm. Parsed or typed, the driver signs off before anything exists -->
    <template v-else>
      <p v-if="readable" class="rc__from">
        <Check :size="16" :stroke-width="2" aria-hidden="true" />
        {{ t("load.rc_from") }}
      </p>
      <p v-else class="rc__unread">
        <TriangleAlert :size="16" :stroke-width="2" aria-hidden="true" />
        {{ t("load.rc_unreadable") }}
      </p>

      <!-- a term the contract does not state, said as silence rather than as a zero -->
      <p v-if="silentOn.length" class="rc__silent">
        <TriangleAlert :size="16" :stroke-width="2" aria-hidden="true" />
        {{ t("load.rc_silent") }}
        <span class="rc__terms">{{ silentOn.map((s) => t(`load.rc_term.${s}`)).join(" · ") }}</span>
      </p>

      <!-- the matched facility. Offered, never assumed: the driver can decline it and
           the load then creates its own — but a wrong match is one tap to undo, while
           a duplicate facility row quietly splits that dock's dwell history in two. -->
      <div v-if="candidates.length" class="rc__match">
        <span class="rc__label">{{ t("load.rc_matched") }}</span>
        <label v-for="c in candidates" :key="c.facility_id" class="rc__opt">
          <input v-model="chosenFacility" type="radio" :value="c.facility_id" />
          <span>{{ c.name }}</span>
        </label>
        <label class="rc__opt">
          <input v-model="chosenFacility" type="radio" :value="null" />
          <span>{{ t("load.rc_no_match") }}</span>
        </label>
      </div>

      <label class="rc__field">
        <span class="rc__label">{{ t("load.facility") }}</span>
        <input v-model="form.facility" class="rc__input" type="text" />
      </label>
      <label class="rc__field">
        <span class="rc__label">{{ t("load.broker") }}</span>
        <input v-model="form.broker" class="rc__input" type="text" />
      </label>
      <label class="rc__field">
        <span class="rc__label">{{ t("calc.free_min") }}</span>
        <input v-model="form.freeMin" class="rc__input" type="number" inputmode="numeric" />
      </label>
      <label class="rc__field">
        <span class="rc__label">{{ t("calc.rate_hr") }}</span>
        <input v-model="form.rateHr" class="rc__input" type="number" inputmode="decimal" />
      </label>

      <button class="rc__cta" type="button" :disabled="busy" @click="create">
        {{ t("load.create") }}
      </button>
      <p class="rc__hint">{{ t("load.rc_confirm_hint") }}</p>
    </template>
  </div>
</template>

<style scoped>
.rc {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.rc__lead {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.rc__label {
  display: block;
  margin-bottom: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.rc__field {
  display: block;
}
.rc__input {
  width: 100%;
  min-height: 56px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.rc__preview {
  display: block;
  width: 100%;
  max-height: 240px;
  object-fit: contain;
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
}
.rc__cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 56px;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.rc__cta:disabled {
  opacity: 0.5;
}
.rc__from {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0;
  color: var(--ledger-500);
  font-size: var(--type-caption-size);
}
/* marker, not flare: an unreadable rate con costs the driver typing, not money */
.rc__unread,
.rc__silent {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: 0;
  padding: var(--s-3);
  border: 1px solid var(--marker-500);
  border-radius: var(--r-control);
  color: var(--marker-500);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.rc__terms {
  font-weight: 500;
}
.rc__match {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.rc__opt {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 48px;
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.rc__hint {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
</style>
