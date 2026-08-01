<!-- AI-CONTEXT: Data & ingest — where the map's facts come from and when they last
     arrived. Source URLs are shown because a wrong endpoint is the commonest cause
     of a silently stale layer, and it is invisible on every other surface. -->
<script setup>
import { onMounted, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import {
  fetchAdminIngest,
  fetchFacilities,
  createFacility,
  editFacility,
  mergeFacility,
  facilityDuplicates,
} from "../../core/api.js";

const { t } = useI18n();
const data = ref(null);

function stamp(iso) {
  // never localized: an operator correlating with logs needs one stable format
  return iso ? iso.replace("T", " ").slice(0, 16) : null;
}

// decision 7: console-native facility management. Every write goes through the F2
// pipeline as an ADMIN SOURCE, so a correction never erases what a feed recorded —
// the copy says so where an operator is about to edit.
const facilities = ref([]);
const facSearch = ref("");
const dupes = ref({});
const draft = ref({ name: "", facility_type: "truck_stop", lat: "", lon: "", is_dev: false });

const KINDS = [
  "truck_stop", "rest_area", "parking_property", "shipper_receiver",
  "fuel_station", "repair", "weigh_station", "scale", "composite",
];

async function loadFacilities() {
  facilities.value = await fetchFacilities(facSearch.value || undefined).catch(() => []);
}

async function addFacility() {
  if (!draft.value.name || draft.value.lat === "") return;
  await createFacility({
    ...draft.value,
    lat: Number(draft.value.lat),
    lon: Number(draft.value.lon),
  });
  draft.value = { name: "", facility_type: "truck_stop", lat: "", lon: "", is_dev: false };
  await loadFacilities();
}

async function rename(fac, name) {
  if (!name || name === fac.name) return;
  await editFacility(fac.facility_id, { name });
  await loadFacilities();
}

async function findDupes(fac) {
  dupes.value = { ...dupes.value, [fac.facility_id]: await facilityDuplicates(fac.facility_id) };
}

// AI-CONTEXT: a merge cannot be undone from this console — there is no unmerge — so
// design-prd §8's destructive rule applies: it gets its own confirm naming what goes.
// One click used to do it, beside a suggestion that showed only a name.
const merging = ref(null);

function requestMerge(canonical, duplicate) {
  merging.value = { canonical, duplicate };
}

async function merge(canonicalId, duplicateId) {
  merging.value = null;
  await mergeFacility(canonicalId, duplicateId);
  dupes.value = {};
  await loadFacilities();
}

onMounted(async () => {
  data.value = await fetchAdminIngest().catch(() => null);
  await loadFacilities();
});
</script>

<template>
  <div v-if="data">
    <section class="panel">
      <h2 class="panel__title">{{ t("admin.data.by_source") }}</h2>
      <ul class="stats">
        <li class="stat">
          <span class="stat__figure">{{ data.facilities.total }}</span>
          <span class="stat__label">{{ t("admin.ov.facilities") }}</span>
        </li>
        <li v-for="(n, source) in data.facilities.by_source" :key="source" class="stat">
          <span class="stat__figure">{{ n }}</span>
          <span class="stat__label">{{ source }}</span>
        </li>
      </ul>
    </section>

    <section class="panel">
      <h2 class="panel__title">{{ t("admin.data.last_ingest") }}</h2>
      <table class="table">
        <tbody>
          <tr v-for="(info, source) in data.freshness" :key="source">
            <td class="table__name">{{ source }}</td>
            <!-- a source that never ingested shows a dash, not a zero date -->
            <td class="table__figure">{{ stamp(info.last_ingested_at) || "—" }}</td>
            <td class="table__figure">{{ info.records }}</td>
            <td class="table__muted">{{ t("admin.data.records") }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel">
      <h2 class="panel__title">{{ t("admin.fac.title") }}</h2>
      <!-- stated where the operator is about to act, not buried in a doc -->
      <p class="panel__note">{{ t("admin.fac.provenance") }}</p>
      <input
        v-model="facSearch"
        class="field__input fac__search"
        type="search"
        :placeholder="t('admin.fac.search')"
        @keyup.enter="loadFacilities"
      />
      <table class="table">
        <tbody>
          <tr v-for="f in facilities" :key="f.facility_id">
            <td class="table__name">
              <input
                class="field__input"
                :value="f.name"
                type="text"
                @change="rename(f, $event.target.value)"
              />
              <div class="table__muted">{{ f.facility_type }}</div>
            </td>
            <td class="table__muted">
              {{ t("admin.fac.sources") }}: {{ f.sources.join(", ") }}
            </td>
            <td class="table__muted">
              <span v-if="f.is_dev">is_dev</span>
            </td>
            <td>
              <button class="btn" type="button" @click="findDupes(f)">
                {{ t("admin.fac.dupes") }}
              </button>
              <div v-for="d in dupes[f.facility_id] || []" :key="d.facility_id" class="fac__dupe">
                <!-- §11.7: a suggestion is a figure, and a figure travels with what
                     produced it. Name alone cannot tell 5 m from 140 m, which is the
                     difference between one site mapped twice and the rest area on the
                     other carriageway. -->
                <span class="table__muted">{{ d.name }}</span>
                <span class="fac__dupe-evidence">
                  {{ d.facility_type }}<template v-if="d.distance_m !== null && d.distance_m !== undefined">
                    · {{ d.distance_m }} m</template>
                </span>
                <button class="btn" type="button" @click="requestMerge(f, d)">
                  {{ t("admin.fac.merge") }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="panel__note">{{ t("admin.fac.no_delete") }}</p>

      <div v-if="merging" class="confirm" role="alertdialog">
        <p class="confirm__title">{{ t("admin.fac.merge_confirm_title") }}</p>
        <p class="confirm__key">
          {{ merging.duplicate.name }} → {{ merging.canonical.name }}
          <template v-if="merging.duplicate.distance_m !== null && merging.duplicate.distance_m !== undefined">
            · {{ merging.duplicate.distance_m }} m
          </template>
        </p>
        <p class="confirm__body">{{ t("admin.fac.merge_confirm_body") }}</p>
        <button
          class="btn btn--danger fac__merge-confirm"
          type="button"
          @click="merge(merging.canonical.facility_id, merging.duplicate.facility_id)"
        >
          {{ t("admin.confirm") }}
        </button>
        <button class="btn" type="button" @click="merging = null">{{ t("admin.cancel") }}</button>
      </div>

      <div class="fac__form">
        <input v-model="draft.name" class="field__input" type="text" :placeholder="t('admin.acct.name')" />
        <select v-model="draft.facility_type" class="field__input">
          <option v-for="k in KINDS" :key="k" :value="k">{{ k }}</option>
        </select>
        <input v-model="draft.lat" class="field__input" type="number" step="0.0001" placeholder="lat" />
        <input v-model="draft.lon" class="field__input" type="number" step="0.0001" placeholder="lon" />
        <label class="fac__dev">
          <input v-model="draft.is_dev" type="checkbox" /> is_dev
        </label>
        <button class="btn btn--accent" type="button" @click="addFacility">
          {{ t("admin.fac.add") }}
        </button>
      </div>
    </section>

    <section class="panel">
      <h2 class="panel__title">{{ t("admin.data.sources") }}</h2>
      <table class="table">
        <tbody>
          <tr v-for="(url, key) in data.sources" :key="key">
            <td class="table__name">{{ key }}</td>
            <td class="table__muted">{{ url }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
@import "./admin-shared.css";
.fac__search {
  width: 100%;
  margin-bottom: var(--s-3);
}
.fac__form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin-top: var(--s-3);
}
.fac__dupe {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-2);
}
.fac__dev {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
</style>
