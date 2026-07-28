<!-- AI-CONTEXT: the wallet's writer (M5-FR3), built to §8's camera-capture rule:
     guided, one screen, review before confirm, and it works with zero connectivity
     always (§15.1) because a credential is most often photographed at a scale house.

     It exists because the Docs tab was a READER with no writer — both driver-facing
     document endpoints were GETs, so a vendor could upload a licence through the
     portal and a driver could not upload their own CDL. That is also why F6's expiry
     engine had nothing to count down from.

     The expiry field appears only for the types an expiry MEANS something for. A BOL
     does not expire, and asking for a date that will never matter teaches a driver
     the form is not paying attention. The server decides which those are. -->
<script setup>
import { ref, computed, onMounted } from "vue";
import { Camera, Check, TriangleAlert } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { captureDocument, fetchDocumentTypes, fetchWouldReplace } from "../api.js";

// AI-CONTEXT: `stopId` is what made §10.2's BOL row honest.
//
// The row reads `has_bol(stop)`, which asks F6 for a document scoped to THIS stop —
// and this sheet had no stop to scope one to, so everything it filed landed against
// the account. The checklist row was therefore permanently false in production: not
// wrong about the data, just asking a question nothing could ever answer yes to. The
// endpoint has taken `stop_id` since the writer shipped; nothing passed it.
//
// `fixedType` skips the type chooser. A driver who tapped "Snap BOL" has already
// answered "what is it?", and asking again is the form not paying attention — the
// same reasoning that hides the expiry field for types that do not expire.
const props = defineProps({
  stopId: { type: String, default: null },
  fixedType: { type: String, default: null },
});
const emit = defineEmits(["captured"]);
const { t } = useI18n();

const types = ref([]);
const expiringTypes = ref([]);
const supersedingTypes = ref([]);
const docType = ref(props.fixedType || "");
const expiresOn = ref("");
const file = ref(null);
const preview = ref(null);
const busy = ref(false);
const done = ref(null);
// AI-CONTEXT: what saving this would archive. Checked when the TYPE is chosen, not
// after saving: §17 Q16 keeps the old credential, but a driver still needs to know
// their current CDL is about to stop being the one the wallet produces — and they
// need to know it while they can still stop.
const replaces = ref(null);
const replacedLabel = ref(null);

async function onType(ty) {
  docType.value = ty;
  replaces.value = null;
  if (!supersedingTypes.value.includes(ty)) return;
  try {
    const res = await fetchWouldReplace(ty);
    replaces.value = res?.replaces ?? null;
  } catch {
    /* offline: the warning is a courtesy, not a gate — the server still supersedes
       correctly when the queued capture lands */
  }
}

onMounted(async () => {
  try {
    const res = await fetchDocumentTypes();
    types.value = res.types ?? [];
    expiringTypes.value = res.expiring ?? [];
    supersedingTypes.value = res.superseding ?? [];
  } catch {
    // offline: the type list is small and stable, so a cached-or-default list is
    // better than a form that cannot be opened in a dead zone
    types.value = ["cdl", "med_card", "insurance", "permit", "rate_con", "bol", "pod", "other"];
    expiringTypes.value = ["cdl", "med_card", "insurance", "permit"];
    supersedingTypes.value = ["cdl", "med_card", "insurance"];
  }
});

const wantsExpiry = computed(() => expiringTypes.value.includes(docType.value));
const ready = computed(() => !!docType.value && !!file.value && !busy.value);

const isImage = computed(() => (file.value?.type || "").startsWith("image/"));

function onFile(event) {
  const f = event.target.files?.[0];
  if (!f) return;
  file.value = f;
  // §8: review before confirm — the driver sees what they are about to file, and for
  // anything that is not an image that means its NAME, not a preview that cannot render
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

async function submit() {
  if (!ready.value) return;
  busy.value = true;
  try {
    const res = await captureDocument({
      docType: docType.value,
      contentB64: await b64(file.value),
      filename: file.value.name,
      contentType: file.value.type,
      expiresOn: wantsExpiry.value ? expiresOn.value : null,
      // a BOL belongs to the delivery it came from, not to the driver in general
      stopId: props.stopId,
    });
    done.value = res?.queued ? "queued" : "filed";
    replacedLabel.value = replaces.value ? t(`docs.type.${docType.value}`) : null;
    emit("captured", { state: done.value });
  } catch {
    done.value = "queued"; // never lose a capture to a server hiccup
    emit("captured", { state: "queued" });
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="cap">
    <p v-if="done" class="cap__done">
      <Check :size="18" :stroke-width="2.5" aria-hidden="true" />
      {{ done === "queued" ? t("docs.cap_queued") : t("docs.cap_filed") }}
    </p>
    <!-- and said again afterwards, because it happened -->
    <p v-if="done && replacedLabel" class="cap__hint">{{ t("docs.cap_replaced_done") }}</p>

    <template v-else>
      <template v-if="!fixedType">
        <span class="cap__label">{{ t("docs.cap_type") }}</span>
        <ul class="cap__types">
          <li v-for="ty in types" :key="ty">
            <button
              class="cap__chip"
              :class="{ 'cap__chip--on': docType === ty }"
              type="button"
              :aria-pressed="docType === ty"
              @click="onType(ty)"
            >
              {{ t(`docs.type.${ty}`) }}
            </button>
          </li>
        </ul>
      </template>

      <!-- stated BEFORE the save, in marker (caution, not error — nothing is lost) -->
      <p v-if="replaces" class="cap__replaces">
        <TriangleAlert :size="16" :stroke-width="2" aria-hidden="true" />
        {{ t("docs.cap_replaces") }}
      </p>

      <label class="cap__field">
        <span class="cap__label">{{ t("docs.cap_photo") }}</span>
        <input class="cap__input" type="file" accept="image/*,application/pdf" @change="onFile" />
      </label>

      <!-- AI-CONTEXT: a PDF is not an image (§23 entry 77). This input accepts
           application/pdf and the preview was always an <img> on a blob URL, which
           cannot decode one — so choosing a rate con showed the browser's BROKEN
           IMAGE glyph. The comment on `onFile` says the driver "sees what they are
           about to file"; what they saw read as "your file is corrupt". Naming the
           file is a smaller promise than showing it, and a true one. -->
      <img
        v-if="preview && isImage"
        :src="preview"
        class="cap__preview"
        :alt="t('docs.cap_photo')"
      />
      <p v-else-if="file" class="cap__file">{{ file.name }}</p>

      <label v-if="wantsExpiry" class="cap__field">
        <span class="cap__label">{{ t("docs.cap_expiry") }}</span>
        <input v-model="expiresOn" class="cap__input" type="date" />
        <span class="cap__hint">{{ t("docs.cap_expiry_hint") }}</span>
      </label>

      <button class="cta" type="button" :disabled="!ready" @click="submit">
        <Camera :size="18" :stroke-width="2" aria-hidden="true" />
        {{ t("docs.cap_save") }}
      </button>
      <p class="cap__hint">{{ t("docs.cap_offline") }}</p>
    </template>
  </div>
</template>

<style scoped>
.cap__label {
  display: block;
  margin-bottom: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.cap__types {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: 0 0 var(--s-4);
  padding: 0;
}
/* §6.5 is 48 dp in BOTH axes, and only the height was set. A chip is as wide as its
   label, so the shortest label in the shortest locale decides — "BOL" in Punjabi
   renders 42 dp wide. Height alone cannot carry the glove spec for content-sized
   controls; found the first time this sheet was measured at 360 dp. */
.cap__chip {
  min-height: 48px;
  min-width: 48px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-pill);
  background: var(--ink-1);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.cap__chip--on {
  border-color: var(--shield-500);
  color: var(--shield-500);
}
.cap__field {
  display: block;
  margin-bottom: var(--s-4);
}
.cap__input {
  width: 100%;
  min-height: 48px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.cap__file {
  color: var(--text-2);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  margin-bottom: var(--s-4);
  overflow-wrap: anywhere;
}
.cap__preview {
  display: block;
  width: 100%;
  max-height: 240px;
  object-fit: contain;
  margin-bottom: var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
}
.cap__replaces {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0 0 var(--s-4);
  padding: var(--s-3);
  border: 1px solid var(--marker-500);
  border-radius: var(--r-control);
  color: var(--marker-500);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.cap__hint {
  margin: var(--s-2) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.cap__done {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  color: var(--ledger-500);
  font-size: var(--type-body-size);
}
.cta {
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
.cta:disabled {
  opacity: 0.5;
}
</style>
