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
import { FileText, TriangleAlert } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { fetchDocumentBytes } from "../api.js";

const props = defineProps({
  document: { type: Object, required: true },
});
const { t } = useI18n();

const url = ref(null);
const failed = ref(false);
const loading = ref(true);
const isPdf = computed(() => (props.document.content_type || "").includes("pdf"));

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
