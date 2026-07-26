<!-- AI-CONTEXT: Docs tab (design-prd §10.4) — wallet + capture inbox.

     The §10.4 anatomy ends with a capture chip and this surface does not render one.
     That is deliberate: M5 has no document-upload endpoint, so the chip said "Add
     document" and pressing it did nothing. §23 settled this exact case for the
     module registry — a capability whose destination does not exist is LABELLED,
     never linked — and §22.2's first heuristic is remove rather than add. It returns
     when there is an upload path for it to reach.

     Anatomy at
     360 dp: Inspection-mode button (top, 56 dp, ≤2 taps from cold start, works
     offline) → expiring-soon strip (marker pills) → document grid by type →
     capture chip REMOVED — see below. S2 dock-task session. Fixture-backed pending live
     /protection/wallet. Doc-type acronyms (CDL/BOL/POD) stay English (§12.3). -->
<script setup>
import { ref, computed, onMounted } from "vue";
import { ShieldCheck } from "lucide-vue-next";
import BottomSheet from "../core/components/BottomSheet.vue";
import { useI18n } from "../core/i18n.js";
import { fetchWallet } from "../core/api.js";
import { SAMPLE_WALLET } from "../core/fixtures.js";

const { t } = useI18n();
const data = ref(SAMPLE_WALLET);
const inspecting = ref(false);

onMounted(async () => {
  try {
    data.value = await fetchWallet();
  } catch {
    data.value = SAMPLE_WALLET;
  }
});

const INSPECTION_TYPES = ["cdl", "med_card", "insurance", "permit"];
const ACRONYMS = { cdl: "CDL", bol: "BOL", pod: "POD" };
function docLabel(type) {
  return (
    ACRONYMS[type] ??
    type.split("_").map((w) => w[0].toUpperCase() + w.slice(1)).join(" ")
  );
}
const inspectionDocs = computed(() =>
  data.value.documents.filter((d) => INSPECTION_TYPES.includes(d.doc_type)),
);
const statusToken = { ok: "--text-3", expiring: "--marker-500", expired: "--flare-500" };
</script>

<template>
  <div class="docs">
    <button class="inspect" type="button" @click="inspecting = true">
      <ShieldCheck :size="24" :stroke-width="2" aria-hidden="true" />
      {{ t("docs.inspection") }}
    </button>

    <div v-if="data.expiring.length" class="expiring">
      <span
        v-for="d in data.expiring"
        :key="d.id"
        class="pill"
        :style="{ '--pill-color': `var(${statusToken[d.status]})` }"
      >
        {{ docLabel(d.doc_type) }} · {{ t(`docs.status.${d.status}`) }}
      </span>
    </div>

    <!-- AI-CONTEXT: §15.3 — "one sentence of purpose + one starting action". An
         empty wallet used to render an empty grid under a dead "Add document" chip;
         removing the chip (§23 registry precedent — a capability with no destination
         is labelled, never linked) left literally nothing on the screen, which is
         how this surface was found looking broken rather than empty.

         There is deliberately NO action button: M5 has no upload path yet, and
         inventing one here would put the dead control straight back. The sentence
         says what the wallet is for and what fills it, which is the honest half of
         §15.3 when the other half does not exist yet. The action returns with the
         upload path. -->
    <p v-if="!data.documents.length" class="docs__empty">{{ t("docs.empty") }}</p>
    <ul v-else class="grid">
      <li v-for="d in data.documents" :key="d.id" class="doc">
        <span class="doc__type">{{ docLabel(d.doc_type) }}</span>
        <span class="doc__expiry">{{ d.expires_on || "—" }}</span>
      </li>
    </ul>

    <BottomSheet :open="inspecting" :title="t('docs.inspection')" @close="inspecting = false">
      <ul class="grid">
        <li v-for="d in inspectionDocs" :key="d.id" class="doc doc--inspect">
          <span class="doc__type">{{ docLabel(d.doc_type) }}</span>
          <span class="doc__expiry">{{ d.expires_on || "—" }}</span>
        </li>
      </ul>
    </BottomSheet>
  </div>
</template>

<style scoped>
.docs {
  padding: var(--s-4);
}
.inspect {
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
  margin-bottom: var(--s-4);
}
.expiring {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin-bottom: var(--s-4);
}
.pill {
  padding: 2px var(--s-2);
  border-radius: var(--r-pill);
  font-size: var(--type-caption-size);
  font-weight: 500;
  color: var(--ink-0);
  background: var(--pill-color);
}
.docs__empty {
  margin: var(--s-5) var(--s-4) 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-3);
}
.doc {
  min-height: 88px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: var(--s-3);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
}
.doc__type {
  font-size: var(--type-body-size);
  font-weight: 500;
}
.doc__expiry {
  font-family: var(--font-mono);
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.capture {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-4);
  border-radius: var(--r-control);
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
  font-size: var(--type-label-size);
  font-weight: 500;
}
</style>
