<!-- AI-CONTEXT: Docs tab (design-prd §10.4) — wallet + capture inbox.

     The capture chip is back, and the round trip is the point. It shipped as a
     control with no handler, was removed under §23's registry precedent (a
     capability whose destination does not exist is labelled, never linked), and
     returns now that `POST /protection/documents` exists for it to reach. The wallet
     was a READER with no writer — which is why this tab was empty and why F6's
     expiry engine had nothing to count down from.

     Anatomy at
     360 dp: Inspection-mode button (top, 56 dp, ≤2 taps from cold start, works
     offline) → expiring-soon strip (marker pills) → document grid by type →
     capture chip → the archive. S2 dock-task session. Doc-type acronyms
     (CDL/BOL/POD) stay English inside the locale catalogue (§12.3).

     The wallet is now writable in both directions: a driver files a document and can
     take one back out. Removal is NOT deletion — §17 Q16 forbids hard delete, so a
     removed document leaves the grid, leaves inspection mode and stops the expiry
     ladder while the row and the bytes stay exactly where they are, restorable from
     the archive sheet. -->
<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { ShieldCheck, Plus, Archive, RotateCcw, ChevronRight } from "lucide-vue-next";
import BottomSheet from "../core/components/BottomSheet.vue";
import DocumentCaptureSheet from "../core/components/DocumentCaptureSheet.vue";
import DocumentViewer from "../core/components/DocumentViewer.vue";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import {
  fetchWallet,
  fetchArchivedDocuments,
  archiveDocument,
  restoreDocument,
} from "../core/api.js";
import { SAMPLE_WALLET } from "../core/fixtures.js";

const { t } = useI18n();
const { isDriving } = useDriverState();
const router = useRouter();
const data = ref(SAMPLE_WALLET);
const inspecting = ref(false);
const capturing = ref(false);
// AI-CONTEXT: SM-3 — the capture BUTTON was guarded and the SHEET was not.
//
// `v-if="!isDriving"` hid the chip, but the sheet is a sibling at the top of the
// surface, so a driver who opened it while stopped and then pulled away kept a live
// camera-capture UI — file input, expiry field, submit — on screen at speed. The
// control that opens a flow and the flow itself are two different things to guard,
// and only one of them was. §10.4 lets inspection mode survive DRIVING; capture does
// not, so this closes rather than merely hiding: a sheet that sprang back open at the
// next stop would be a surprise nobody asked for.
watch(isDriving, (driving) => {
  if (driving) capturing.value = false;
});
// AI-CONTEXT: the document a driver (or an officer) is looking at. Tapping a row
// opens it, in the wallet AND in inspection mode — the point of the wallet is
// producing the credential, not reporting that one exists.
const viewing = ref(null);

// AI-CONTEXT: the archive — where removal goes, because removal is not deletion.
// §17 Q16 forbids hard delete, so a document a driver removes leaves the wallet and
// stays in the record; this is the half of that promise the driver can actually see.
// Sheets stack max 1 deep (§8), so opening a document from here closes the archive
// and reopens it on the way back rather than stacking a second sheet over it.
const archiveOpen = ref(false);
const archived = ref([]);
const returnToArchive = ref(false);
// the document waiting on its confirm. §8: a destructive action gets its own sheet.
const removing = ref(null);
const busy = ref(false);

async function refresh() {
  try {
    data.value = await fetchWallet();
  } catch {
    /* offline: keep what is on screen — a wallet that empties itself in a dead zone
       is worse than one that is briefly stale */
  }
  try {
    archived.value = (await fetchArchivedDocuments()).documents;
  } catch {
    /* the archive is a secondary view; failing to load it must not blank the wallet */
  }
}

async function onCaptured() {
  // §15.1: sync completion is silent. The wallet simply has the document in it — the
  // driver watched it arrive, so announcing it again is noise. The archive refreshes
  // too: filing a one-at-a-time credential supersedes the old one, so it just gained
  // a row, and the same is true after an edit reopens a reminder ladder.
  capturing.value = false;
  await refresh();
}

function open(doc, { fromArchive = false } = {}) {
  returnToArchive.value = fromArchive;
  archiveOpen.value = false;
  viewing.value = {
    id: doc.id,
    label: docLabel(doc.doc_type),
    content_type: doc.content_type,
    expires_on: doc.expires_on,
    archived: fromArchive,
  };
}

function closeViewer() {
  viewing.value = null;
  if (returnToArchive.value) {
    archiveOpen.value = true;
    returnToArchive.value = false;
  }
}

async function openArchive() {
  archiveOpen.value = true;
  try {
    archived.value = (await fetchArchivedDocuments()).documents;
  } catch {
    /* show what was last loaded rather than an error screen for a secondary view */
  }
}

function askRemove(doc) {
  // the viewer closes and the confirm takes its place: one sheet at a time (§8)
  viewing.value = null;
  returnToArchive.value = false;
  removing.value = doc;
}

async function confirmRemove() {
  busy.value = true;
  try {
    await archiveDocument(removing.value.id);
    removing.value = null;
    await refresh();
  } catch {
    removing.value = null;
  } finally {
    busy.value = false;
  }
}

async function restore(row) {
  busy.value = true;
  try {
    await restoreDocument(row.id);
    await refresh();
  } catch {
    /* the row said whether this would work; a race is possible and the refresh
       below re-states the truth rather than asserting a success that did not happen */
    await refresh();
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  try {
    data.value = await fetchWallet();
  } catch {
    data.value = SAMPLE_WALLET;
  }
  try {
    archived.value = (await fetchArchivedDocuments()).documents;
  } catch {
    archived.value = [];
  }
});

const INSPECTION_TYPES = ["cdl", "med_card", "insurance", "permit"];
// AI-CONTEXT: the labels are TRANSLATED. `docs.type.*` has carried all six locales
// since the capture sheet was built, and this surface was deriving its own English
// from the enum beside it — so a Somali driver read "Med Card" in the grid and
// "Kaarka caafimaadka" in the form for the same document. The acronyms (CDL/BOL/POD)
// stay English inside the catalogue itself, which is where §12.3 wants that decision.
function docLabel(type) {
  const key = `docs.type.${type}`;
  const label = t(key);
  return label === key ? type.replace(/_/g, " ") : label;
}
const inspectionDocs = computed(() =>
  data.value.documents.filter((d) => INSPECTION_TYPES.includes(d.doc_type)),
);
// §10.4: "document grid BY TYPE". It has always rendered one flat list in upload
// order, so a driver with two permits and three BOLs scanned the grid to find them.
// AI-CONTEXT: collapsed by default (§23 entry 80). Three sections is the right
// SHAPE and still the wrong screen when one of them holds 23 documents: a driver
// opening Docs to check a med card scrolled past every BOL they had ever filed. The
// headings are the index; the count is on the heading, so nothing has to be opened to
// learn whether it is worth opening. The expiring strip is untouched above this and
// still surfaces what needs action without any tap at all.
const open_ = ref(new Set());
function toggle(key) {
  const next = new Set(open_.value);
  next.has(key) ? next.delete(key) : next.add(key);
  open_.value = next;
}

const paperwork = computed(() => data.value.load_paperwork ?? []);
const unattached = computed(() => data.value.unattached ?? []);
function routeLabel(p) {
  return p.destination_name ? `${p.facility_name} → ${p.destination_name}` : p.facility_name;
}
function openLoad(p) {
  router.push(`/load/${p.stop_id}/evidence`);
}
async function removeOrphan(d) {
  // removal is the ARCHIVE (§17 Q16 forbids hard delete): it leaves the wallet and
  // stays recoverable, which is what the rest of this surface already means by remove.
  try {
    await archiveDocument(d.id);
    await refresh();
  } catch {
    /* offline: the wallet reloads on next open rather than lying about the removal */
  }
}

const groups = computed(() => {
  const byType = new Map();
  for (const doc of data.value.documents) {
    if (!byType.has(doc.doc_type)) byType.set(doc.doc_type, []);
    byType.get(doc.doc_type).push(doc);
  }
  return [...byType.entries()].map(([type, docs]) => ({ type, label: docLabel(type), docs }));
});
const archivedCount = computed(() => data.value.archived_count ?? archived.value.length);
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
         how this surface was found looking broken rather than empty. The action came
         back with `POST /protection/documents`, so §15.3 now has both halves. -->
    <p v-if="!data.documents.length && !paperwork.length && !unattached.length"
       class="docs__empty">{{ t("docs.empty") }}</p>
    <div v-else class="groups">
      <!-- AI-CONTEXT: the wallet is the driver's OWN documents (§23 entry 79). It
           returned everything on the account grouped by type, so a CDL sat between
           rate cons — measured on a real account, 40 documents of which 5 were
           theirs. Grouping by type is right for a credential and wrong for
           paperwork: a BOL matters for the load it belongs to, not for being a BOL. -->
      <section v-if="data.documents.length" class="group">
        <button class="group__head" type="button" @click="toggle('mine')">
          <ChevronRight :size="16" :stroke-width="2" class="group__caret"
                        :class="{ 'group__caret--open': open_.has('mine') }" aria-hidden="true" />
          <h2 class="group__label">{{ t("docs.mine") }}</h2>
          <span class="group__count">{{ data.documents.length }}</span>
        </button>
        <div v-for="g in groups" v-if="open_.has('mine')" :key="g.type" class="subgroup">
          <h3 class="group__sub">{{ g.label }}</h3>
          <ul class="grid">
            <li v-for="d in g.docs" :key="d.id">
              <button class="doc" type="button" @click="open(d)">
                <span class="doc__type">{{ g.label }}</span>
                <span class="doc__expiry">{{ d.expires_on || "—" }}</span>
              </button>
            </li>
          </ul>
        </div>
      </section>

      <section v-if="paperwork.length" class="group">
        <button class="group__head" type="button" @click="toggle('paperwork')">
          <ChevronRight :size="16" :stroke-width="2" class="group__caret"
                        :class="{ 'group__caret--open': open_.has('paperwork') }"
                        aria-hidden="true" />
          <h2 class="group__label">{{ t("docs.paperwork") }}</h2>
          <span class="group__count">{{ paperwork.length }}</span>
        </button>
        <ul v-if="open_.has('paperwork')" class="paper">
          <li v-for="p in paperwork" :key="p.load_id">
            <button class="paper__row" type="button" @click="openLoad(p)">
              <span class="paper__route">{{ routeLabel(p) }}</span>
              <span class="paper__meta">
                <template v-if="p.reference_number">{{ p.reference_number }} · </template
                >{{ p.created_at.slice(0, 10) }}
              </span>
              <span class="paper__types">
                {{ p.doc_types.map((k) => t(`docs.type.${k}`)).join(" · ") }}
              </span>
            </button>
          </li>
        </ul>
      </section>

      <!-- photographed, parsed, and never turned into a load. Said plainly rather
           than left looking like a filed document, and removal is the archive
           (§17 Q16 forbids hard delete), so nothing is thrown away. -->
      <section v-if="unattached.length" class="group">
        <button class="group__head" type="button" @click="toggle('unattached')">
          <ChevronRight :size="16" :stroke-width="2" class="group__caret"
                        :class="{ 'group__caret--open': open_.has('unattached') }"
                        aria-hidden="true" />
          <h2 class="group__label">{{ t("docs.unattached") }}</h2>
          <span class="group__count">{{ unattached.length }}</span>
        </button>
        <ul v-if="open_.has('unattached')" class="paper">
          <li v-for="d in unattached" :key="d.id" class="orphan">
            <button class="paper__row" type="button" @click="open(d)">
              <span class="paper__route">{{ t(`docs.type.${d.doc_type}`) }}</span>
              <span class="paper__meta">{{ d.uploaded_at.slice(0, 16).replace("T", " ") }}</span>
              <span class="paper__types">{{ t("docs.unattached_hint") }}</span>
            </button>
            <button class="orphan__rm" type="button" @click="removeOrphan(d)">
              {{ t("docs.remove_short") }}
            </button>
          </li>
        </ul>
      </section>
    </div>

    <!-- §10.4's capture chip. DRIVING: capture is Forbidden #11 territory, so the
         chip does not render at speed — a credential photographed at 65 mph is not
         a credential, it is a hazard. -->
    <button v-if="!isDriving" class="capture" type="button" @click="capturing = true">
      <Plus :size="20" :stroke-width="2" aria-hidden="true" />
      {{ t("docs.add") }}
    </button>

    <!-- The archive, as a tertiary control (§8) opening a sheet (NAV-3: secondary
         views are sheets). It renders only when there is something in it — an
         "Archived · 0" row is a control that teaches the driver nothing. -->
    <button v-if="archivedCount" class="archive" type="button" @click="openArchive">
      <Archive :size="18" :stroke-width="2" aria-hidden="true" />
      {{ t("docs.archived") }}
      <span class="archive__count">{{ archivedCount }}</span>
    </button>

    <BottomSheet :open="capturing" :title="t('docs.add')" @close="capturing = false">
      <DocumentCaptureSheet @captured="onCaptured" />
    </BottomSheet>

    <BottomSheet :open="inspecting" :title="t('docs.inspection')" @close="inspecting = false">
      <!-- the officer's screen. Tapping produces the credential itself, which is
           the entire purpose of inspection mode — a list of types and dates is our
           CLAIM that the driver holds them, not the documents. -->
      <ul class="grid">
        <li v-for="d in inspectionDocs" :key="d.id">
          <button class="doc doc--inspect" type="button" @click="open(d)">
            <span class="doc__type">{{ docLabel(d.doc_type) }}</span>
            <span class="doc__expiry">{{ d.expires_on || "—" }}</span>
          </button>
        </li>
      </ul>
      <p class="docs__hint">{{ t("docs.view_hint") }}</p>
    </BottomSheet>

    <BottomSheet :open="!!viewing" :title="viewing?.label || ''" @close="closeViewer">
      <DocumentViewer
        v-if="viewing"
        :document="viewing"
        @edited="onCaptured"
        @remove="askRemove"
      />
    </BottomSheet>

    <!-- The archive. Every row says WHY it is here, because "replaced by a newer one"
         and "you removed this" are different facts that lead to different decisions,
         and whether Restore will actually work — a control that exists only to fail
         is the dead-control pattern this surface has already been caught by twice. -->
    <BottomSheet :open="archiveOpen" :title="t('docs.arch_title')" @close="archiveOpen = false">
      <p v-if="!archived.length" class="docs__empty">{{ t("docs.arch_empty") }}</p>
      <ul v-else class="arch">
        <li v-for="row in archived" :key="row.id" class="arch__row">
          <button class="arch__doc" type="button" @click="open(row, { fromArchive: true })">
            <span class="doc__type">{{ docLabel(row.doc_type) }}</span>
            <span class="arch__why">
              {{ row.reason === "superseded" ? t("docs.arch_superseded") : t("docs.arch_removed") }}
            </span>
            <span class="doc__expiry">{{ row.archived_at.slice(0, 10) }}</span>
          </button>
          <button
            v-if="row.restorable && !isDriving"
            class="arch__restore"
            type="button"
            :disabled="busy"
            @click="restore(row)"
          >
            <RotateCcw :size="16" :stroke-width="2" aria-hidden="true" />
            {{ t("docs.arch_restore") }}
          </button>
          <p v-else-if="!row.restorable" class="arch__blocked">{{ t("docs.arch_blocked") }}</p>
        </li>
      </ul>
      <p class="docs__hint">{{ t("docs.arch_hint") }}</p>
    </BottomSheet>

    <!-- §8: a destructive action gets its OWN confirm sheet, and §12.2 says the
         button names exactly what happens. The body states the consequence and the
         limit of it in the same breath — reminders stop, nothing is deleted —
         because a driver who believes Remove destroys their CDL will never press it,
         and one who believes it is harmless will be surprised when the reminders go. -->
    <BottomSheet :open="!!removing" :title="t('docs.rm_title')" @close="removing = null">
      <p class="docs__empty">{{ t("docs.rm_body") }}</p>
      <button class="rm__go" type="button" :disabled="busy" @click="confirmRemove">
        {{ t("docs.rm_confirm") }}
      </button>
      <button class="rm__keep" type="button" @click="removing = null">
        {{ t("docs.rm_keep") }}
      </button>
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
.docs__hint {
  margin: var(--s-3) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
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
  width: 100%;
  min-height: 64px;
  text-align: left;
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
.groups {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
/* §23 entry 80: the heading IS the control. 48 dp target, tokens only, and the caret
   turns rather than swapping glyphs so the row never reflows as it opens. */
.group__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 48px;
  padding: 0;
  background: none;
  border: 0;
  text-align: left;
  cursor: pointer;
}
.group__caret {
  flex: none;
  color: var(--text-3);
  transition: transform 120ms ease;
}
.group__caret--open {
  transform: rotate(90deg);
}
.group__count {
  margin-left: auto;
  color: var(--text-3);
  font-size: var(--type-label-size);
  font-variant-numeric: tabular-nums;
}
@media (prefers-reduced-motion: reduce) {
  .group__caret {
    transition: none;
  }
}
.group__head .group__label {
  margin: 0;
}
.group__label {
  margin: 0 0 var(--s-2);
  font-size: var(--type-label-size);
  font-weight: 500;
  color: var(--text-2);
}
/* §23 entry 79: three sections, one type scale. The per-type heading inside the
   wallet steps DOWN from the section heading rather than introducing a new size. */
.subgroup {
  margin-bottom: var(--s-4);
}
.group__sub {
  margin: 0 0 var(--s-2);
  font-size: var(--type-label-size);
  font-weight: 500;
  color: var(--text-3);
}
.paper {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.paper__row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-1);
  width: 100%;
  min-height: 48px;
  padding: var(--s-3);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  text-align: left;
  cursor: pointer;
}
.paper__route {
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.paper__meta,
.paper__types {
  color: var(--text-3);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
}
.orphan {
  display: flex;
  align-items: stretch;
  gap: var(--s-2);
}
.orphan .paper__row {
  flex: 1 1 auto;
  min-width: 0;
}
.orphan__rm {
  flex: none;
  min-width: 48px;
  min-height: 48px;
  padding: 0 var(--s-3);
  background: transparent;
  border: 0;
  color: var(--flare-500);
  font-size: var(--type-label-size);
  font-weight: 500;
  cursor: pointer;
}
/* tertiary control (§8): text weight, no fill — the archive is a secondary view and
   must not compete with Inspection mode, which is this screen's one Primary */
.archive {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 48px;
  margin-top: var(--s-3);
  color: var(--text-2);
  font-size: var(--type-label-size);
  font-weight: 500;
  background: transparent;
}
.archive__count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-3);
}
.arch {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.arch__row {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-3);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
}
.arch__doc {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  min-height: 48px;
  text-align: left;
  background: transparent;
}
.arch__why {
  font-size: var(--type-caption-size);
  color: var(--text-2);
}
.arch__restore {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 48px;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
  background: transparent;
}
.arch__restore:disabled {
  opacity: 0.5;
}
.arch__blocked {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
/* §8: destructive = flare FILLED, and it is the confirm that carries the fill */
.rm__go {
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-4);
  border-radius: var(--r-control);
  background: var(--flare-500);
  color: var(--ink-0);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.rm__go:disabled {
  opacity: 0.5;
}
.rm__keep {
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-2);
  border-radius: var(--r-control);
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
  font-size: var(--type-label-size);
  font-weight: 500;
}
</style>
