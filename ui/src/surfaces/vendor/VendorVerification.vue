<!-- AI-CONTEXT: the verification ladder, stated for exactly what it is.

     Three rungs, and the middle one is the one a portal is tempted to oversell:
     `documents_on_file` means PAPERWORK WAS RECEIVED. Not that anyone visited, not
     that a kitchen passed anything. §23 already fixed that this rung renders
     NEUTRAL rather than positive for drivers; the same restraint applies here, where
     the reader is the person who would most like it to mean more.

     Uploading is not approval either — a fresh document reads "pending", because a
     cook who thinks they are verified and finds out otherwise on their pin has been
     misled by their own dashboard. -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { FileCheck, Upload } from "lucide-vue-next";
import { useI18n } from "../../core/i18n.js";
import { fetchMyDocuments, uploadVendorDocument } from "../../core/api.js";

const RUNGS = ["unverified", "documents_on_file", "verified"];

const { t } = useI18n();
const state = ref(null);
const busy = ref(false);
const error = ref(null);
const kind = ref("");
const file = ref(null);

const rungIndex = computed(() => RUNGS.indexOf(state.value?.verify_status ?? "unverified"));

async function load() {
  state.value = await fetchMyDocuments().catch(() => null);
  if (state.value?.kinds?.length && !kind.value) kind.value = state.value.kinds[0];
}
onMounted(load);

function onFile(event) {
  file.value = event.target.files?.[0] ?? null;
}

function readBase64(f) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(f);
  });
}

async function upload() {
  if (!file.value || !kind.value) return;
  busy.value = true;
  error.value = null;
  try {
    await uploadVendorDocument({
      kind: kind.value,
      content_b64: await readBase64(file.value),
      filename: file.value.name,
    });
    file.value = null;
    await load();
  } catch (e) {
    error.value = typeof e?.detail === "string" ? e.detail : t("vendor.upload_error");
  } finally {
    busy.value = false;
  }
}

function when(iso) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";
}
</script>

<template>
  <div class="ver">
    <h2 class="ver__title">{{ t("vendor.nav.verification") }}</h2>

    <section v-if="state" class="card">
      <ol class="ladder">
        <li
          v-for="(r, i) in RUNGS"
          :key="r"
          class="rung"
          :class="{ 'rung--on': i <= rungIndex, 'rung--here': i === rungIndex }"
        >
          <span class="rung__name">{{ t(`vendor.${r}`) }}</span>
          <span class="rung__means">{{ t(`vendor.rung_means.${r}`) }}</span>
        </li>
      </ol>
    </section>

    <section class="card">
      <h3 class="card__title">{{ t("vendor.your_documents") }}</h3>
      <p v-if="!state?.documents?.length" class="card__empty">{{ t("vendor.no_documents") }}</p>
      <table v-else class="table">
        <tbody>
          <tr v-for="d in state.documents" :key="d.document_id">
            <td>
              <FileCheck :size="16" :stroke-width="2" aria-hidden="true" />
              {{ t(`vendor.doc.${d.kind}`) }}
            </td>
            <td class="table__when">{{ when(d.at) }}</td>
            <!-- pending is said plainly; an upload is not an approval -->
            <td>{{ t(`vendor.doc_status.${d.review_status}`) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card">
      <h3 class="card__title">{{ t("vendor.upload") }}</h3>
      <label class="field">
        <span class="field__label">{{ t("vendor.doc_kind") }}</span>
        <select v-model="kind" class="field__input">
          <option v-for="k in state?.kinds || []" :key="k" :value="k">
            {{ t(`vendor.doc.${k}`) }}
          </option>
        </select>
      </label>
      <label class="field">
        <span class="field__label">{{ t("vendor.file") }}</span>
        <input class="field__input" type="file" @change="onFile" />
      </label>
      <button class="cta" type="button" :disabled="busy || !file" @click="upload">
        <Upload :size="18" :stroke-width="2" aria-hidden="true" />
        {{ t("vendor.upload") }}
      </button>
      <p class="field__hint">{{ t("vendor.upload_note") }}</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </section>
  </div>
</template>

<style scoped>
.ver__title {
  margin: 0 0 var(--s-4);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.card {
  margin-bottom: var(--s-4);
  padding: var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.card__title {
  margin: 0 0 var(--s-3);
  color: var(--text-2);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.card__empty {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.ladder {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.rung {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  padding-left: var(--s-4);
  border-left: 2px solid var(--line-1);
  color: var(--text-3);
}
/* only the TOP rung earns the positive token — the middle one is a statement about
   paperwork, and colouring it as success would imply an inspection (§23) */
.rung--on {
  border-left-color: var(--text-2);
  color: var(--text-2);
}
.rung--here {
  border-left-color: var(--shield-500);
  color: var(--text-1);
}
.rung__name {
  font-size: var(--type-body-size);
  font-weight: 500;
}
.rung__means {
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.table {
  width: 100%;
  border-collapse: collapse;
}
.table td {
  padding: var(--s-3) var(--s-2);
  border-bottom: 1px solid var(--line-1);
  font-size: var(--type-body-size);
}
.table__when {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.field {
  display: block;
  margin-bottom: var(--s-3);
}
.field__label {
  display: block;
  margin-bottom: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.field__input {
  width: 100%;
  min-height: 48px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.field__hint {
  display: block;
  margin-top: var(--s-2);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  min-height: 48px;
  padding: 0 var(--s-4);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta:disabled {
  opacity: 0.5;
}
.error {
  margin: var(--s-3) 0 0;
  color: var(--flare-500);
  font-size: var(--type-body-size);
}
</style>
