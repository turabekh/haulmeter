<!-- AI-CONTEXT: the document itself, full-screen.
     Inspection mode exists to PRODUCE a credential to a DOT officer. Until this
     component, the wallet could only show metadata — a row reading "CDL ·
     2028-01-17", which is not a credential but our claim that the driver has one.
     Asserting on the driver's behalf to a police officer is the worst audience for
     the honesty problem this product keeps solving elsewhere.

     Two things it must survive, because both are the normal case at a scale house:
     · NO SIGNAL. The bytes are fetched once and held as an object URL; the route
       sets an immutable year-long cache, so a document opened at home opens again
       at the scale. A failure says so plainly rather than showing an empty frame.
     · A PDF. Some credentials are filed as PDFs, which an <img> cannot render — it
       gets an object tag, and the fallback is a plain link rather than a blank box.

     DRIVING is not guarded here: the driver hands the PHONE to an officer, and by
     then the truck is stopped. The guard belongs on capture, which is where it is.

     It renders NO header of its own. The BottomSheet hosting it already provides the
     title and the close control, and duplicating them put two "CDL" headings and two
     × buttons on the screen — visible immediately, invisible to every test. -->
<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { FileText, TriangleAlert, Pencil, Trash2 } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { useDriverState } from "../state.js";
import { fetchDocumentBytes, editDocument } from "../api.js";
import Spinner from "./Spinner.vue";

const props = defineProps({
  document: { type: Object, required: true },
});
const emit = defineEmits(["edited", "remove"]);
const { t } = useI18n();
const { isDriving } = useDriverState();

const url = ref(null);
const failed = ref(false);
const loading = ref(true);
const isPdf = computed(() => (props.document.content_type || "").includes("pdf"));

// AI-CONTEXT: editing corrects what was RECORDED about a document — a mistyped
// expiry is the common case, and until now a driver who fat-fingered a year had no
// way to fix it and would be warned on the wrong schedule forever.
//
// The bytes are deliberately not editable. Replacing the image is a new capture,
// which supersedes and archives, so what a driver files and what an inspector sees
// can never quietly diverge.
const editing = ref(false);
const expiresOn = ref(props.document.expires_on || "");
const saving = ref(false);
const savedAt = ref(null);

async function save() {
  saving.value = true;
  try {
    const res = await editDocument(props.document.id, { expiresOn: expiresOn.value });
    savedAt.value = res.expires_on;
    editing.value = false;
    emit("edited", res);
  } catch {
    /* leave the form open with what they typed — losing a correction to a failed
       request would make them type it twice */
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  try {
    url.value = await fetchDocumentBytes(props.document.id);
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
});

onBeforeUnmount(() => {
  if (url.value) URL.revokeObjectURL(url.value);
});
</script>

<template>
  <div class="viewer">
    <p v-if="loading" class="viewer__state">{{ t("docs.view_loading") }}</p>

    <p v-else-if="failed" class="viewer__state viewer__state--bad" role="alert">
      <TriangleAlert :size="18" :stroke-width="2" aria-hidden="true" />
      {{ t("docs.view_failed") }}
    </p>

    <template v-else-if="url">
      <object v-if="isPdf" :data="url" type="application/pdf" class="viewer__frame">
        <a class="viewer__fallback" :href="url" target="_blank" rel="noopener">
          <FileText :size="18" :stroke-width="2" aria-hidden="true" />
          {{ t("docs.view_open") }}
        </a>
      </object>
      <img v-else :src="url" class="viewer__frame" :alt="document.label" />
    </template>

    <div v-if="document.expires_on || savedAt" class="viewer__meta">
      <span class="viewer__expiry">
        {{ t("docs.view_expires") }}
        <span class="viewer__date">{{ savedAt || document.expires_on }}</span>
      </span>
      <!-- an archived document refuses edits with a 409: it records what was true,
           and editing it would rewrite history rather than correct the present. So
           the control is not offered rather than offered and refused. -->
      <button
        v-if="!editing && !document.archived"
        class="viewer__edit"
        type="button"
        @click="editing = true"
      >
        <Pencil :size="16" :stroke-width="2" aria-hidden="true" />
        {{ t("docs.view_edit") }}
      </button>
    </div>

    <div v-if="editing" class="viewer__form">
      <label class="viewer__label" for="doc-expiry">{{ t("docs.cap_expiry") }}</label>
      <input id="doc-expiry" v-model="expiresOn" class="viewer__input" type="date" />
      <p class="viewer__hint">{{ t("docs.view_edit_hint") }}</p>
      <button class="viewer__save" type="button" :disabled="saving" @click="save">
        <Spinner v-if="saving" />
        {{ saving ? t("busy.saving") : t("portal.vendor.save") }}
      </button>
    </div>

    <!-- AI-CONTEXT: removal — the driver's "delete", which does not delete (§17 Q16).
         §8: destructive controls are flare-filled and require their own confirm
         sheet, so this only ASKS; the sheet belongs to the surface, because sheets
         stack max 1 deep and this component is already inside one.

         DRIVING: a confirm is an interactive prompt (Forbidden #11), so it does not
         render at speed. The viewer itself deliberately has no DRIVING guard — the
         driver hands the phone to an officer and by then the truck is stopped — but
         a destructive decision taken at 65 mph is a different thing entirely. -->
    <button
      v-if="!document.archived && !isDriving"
      class="viewer__remove"
      type="button"
      @click="emit('remove', document)"
    >
      <Trash2 :size="16" :stroke-width="2" aria-hidden="true" />
      {{ t("docs.view_remove") }}
    </button>
  </div>
</template>

<style scoped>
.viewer {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.viewer__frame {
  width: 100%;
  min-height: 60vh;
  max-height: 78vh;
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-0);
  object-fit: contain;
}
.viewer__state {
  margin: var(--s-5) 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.viewer__state--bad {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  color: var(--flare-500);
}
.viewer__meta {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  font-size: var(--type-body-size);
  color: var(--text-2);
}
.viewer__expiry {
  flex: 1 1 auto;
}
.viewer__date {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-1);
}
.viewer__edit {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 48px;
  padding: 0 var(--s-3);
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
.viewer__form {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.viewer__label {
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.viewer__input {
  width: 100%;
  min-height: 48px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.viewer__hint {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.viewer__save {
  min-height: 48px;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.viewer__save:disabled {
  opacity: 0.5;
}
/* §8: destructive = flare. Outlined rather than filled — the sheet it opens carries
   the filled confirm, and two flare-filled buttons in one flow would make the ask
   look like the act. */
.viewer__remove {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 48px;
  border-radius: var(--r-control);
  background: transparent;
  border: 1px solid var(--flare-500);
  color: var(--flare-500);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.viewer__fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  min-height: 48px;
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
</style>
