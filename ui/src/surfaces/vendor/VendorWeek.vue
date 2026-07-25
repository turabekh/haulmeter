<!-- AI-CONTEXT: the schedule, and the button that was missing.

     Until this section existed the portal could CANCEL an appearance but not create
     one — a cook could empty their week and not fill it. `POST /vendor/appearances`
     had been there since M13-FR8 with nothing calling it.

     Two things this form must get right:
     · The Q-4 floor answers a refused publish with the EXACT missing fields. They are
       rendered as named lines, not as "something went wrong", because the whole point
       of the floor is that a cook can fix it in one pass.
     · Offerings come from the standing menu by default. Publishing SNAPSHOTS them, so
       a price edited next week never rewrites what this window advertised. -->
<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { CalendarPlus } from "lucide-vue-next";
import { useI18n } from "../../core/i18n.js";
import {
  cancelVendorAppearance,
  fetchVendorMenu,
  fetchVendorSchedule,
  publishVendorAppearance,
  searchFacilities,
} from "../../core/api.js";
import { formatMoney } from "../../core/meter.js";

const { t } = useI18n();
const schedule = ref([]);
const menu = ref([]);
const facilities = ref([]);
const missing = ref([]);
const error = ref(null);
const busy = ref(false);
const showForm = ref(false);

// ISO weekday numbers, Monday first — a weekly schedule materialises concrete
// occurrences server-side; this only says which days.
const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7];

const form = reactive({
  facility_id: "",
  facility_q: "",
  date: "",
  start: "11:00",
  end: "14:00",
  weekly: [],
  property_approved: false,
  menu_item_ids: [],
});

const upcoming = computed(() =>
  schedule.value.filter((a) => ["scheduled", "live"].includes(a.status)),
);
const past = computed(() =>
  schedule.value.filter((a) => !["scheduled", "live"].includes(a.status)),
);
// nothing priced means the floor will refuse, so say so before the button is pressed
const canPublish = computed(
  () => form.facility_id && form.date && form.menu_item_ids.length > 0,
);

async function load() {
  [schedule.value, menu.value] = await Promise.all([
    fetchVendorSchedule().catch(() => []),
    fetchVendorMenu().catch(() => []),
  ]);
  // default to the whole menu: the common case is "the usual, at this stop"
  form.menu_item_ids = menu.value.map((i) => i.item_id);
}
onMounted(load);

async function lookupFacilities() {
  facilities.value = await searchFacilities(form.facility_q).catch(() => []);
}

function pickFacility(f) {
  form.facility_id = f.id;
  form.facility_q = f.name;
  facilities.value = [];
}

function toggleDay(d) {
  const at = form.weekly.indexOf(d);
  if (at === -1) form.weekly.push(d);
  else form.weekly.splice(at, 1);
}

function toggleItem(id) {
  const at = form.menu_item_ids.indexOf(id);
  if (at === -1) form.menu_item_ids.push(id);
  else form.menu_item_ids.splice(at, 1);
}

async function publish() {
  busy.value = true;
  missing.value = [];
  error.value = null;
  try {
    await publishVendorAppearance({
      facility_id: form.facility_id,
      starts_at: new Date(`${form.date}T${form.start}`).toISOString(),
      ends_at: new Date(`${form.date}T${form.end}`).toISOString(),
      menu_item_ids: form.menu_item_ids,
      property_approved: form.property_approved,
      weekly: form.weekly.length ? form.weekly : null,
    });
    showForm.value = false;
    await load();
  } catch (e) {
    // the floor names what is missing; anything else is reported as itself
    if (e?.detail?.missing) missing.value = e.detail.missing;
    else if (e?.detail?.error === "publish_suspended") error.value = t("portal.vendor.suspended");
    else error.value = t("vendor.publish_failed");
  } finally {
    busy.value = false;
  }
}

async function drop(id, wholeSeries = false) {
  await cancelVendorAppearance(id, wholeSeries);
  await load();
}

function when(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
</script>

<template>
  <div class="week">
    <div class="week__head">
      <h2 class="week__title">{{ t("vendor.nav.week") }}</h2>
      <button class="cta" type="button" @click="showForm = !showForm">
        <CalendarPlus :size="18" :stroke-width="2" aria-hidden="true" />
        {{ t("vendor.add_appearance") }}
      </button>
    </div>

    <form v-if="showForm" class="card" @submit.prevent="publish">
      <label class="field">
        <span class="field__label">{{ t("vendor.where") }}</span>
        <input
          v-model="form.facility_q"
          class="field__input"
          type="text"
          @input="lookupFacilities"
        />
      </label>
      <ul v-if="facilities.length" class="picker">
        <li v-for="f in facilities" :key="f.id">
          <button class="picker__opt" type="button" @click="pickFacility(f)">
            {{ f.name }} <span class="picker__type">{{ t(`facility.type.${f.facility_type}`) }}</span>
          </button>
        </li>
      </ul>

      <div class="row">
        <label class="field">
          <span class="field__label">{{ t("vendor.date") }}</span>
          <input v-model="form.date" class="field__input" type="date" />
        </label>
        <label class="field">
          <span class="field__label">{{ t("vendor.from") }}</span>
          <input v-model="form.start" class="field__input" type="time" />
        </label>
        <label class="field">
          <span class="field__label">{{ t("vendor.to") }}</span>
          <input v-model="form.end" class="field__input" type="time" />
        </label>
      </div>

      <fieldset class="field">
        <legend class="field__label">{{ t("vendor.repeat") }}</legend>
        <div class="days">
          <button
            v-for="d in WEEKDAYS"
            :key="d"
            type="button"
            class="day"
            :class="{ 'day--on': form.weekly.includes(d) }"
            @click="toggleDay(d)"
          >
            {{ t(`vendor.weekday.${d}`) }}
          </button>
        </div>
        <span class="field__hint">{{ t("vendor.repeat_hint") }}</span>
      </fieldset>

      <fieldset class="field">
        <legend class="field__label">{{ t("vendor.what") }}</legend>
        <p v-if="!menu.length" class="field__hint">
          {{ t("vendor.menu_empty_hint") }}
          <router-link class="link" to="/vendor-portal/menu">{{ t("vendor.nav.menu") }}</router-link>
        </p>
        <div v-else class="items">
          <button
            v-for="i in menu"
            :key="i.item_id"
            type="button"
            class="item"
            :class="{ 'item--on': form.menu_item_ids.includes(i.item_id) }"
            @click="toggleItem(i.item_id)"
          >
            {{ i.name }}
            <span class="item__price">{{ formatMoney(i.price_cents) }}</span>
          </button>
        </div>
      </fieldset>

      <label class="check">
        <input v-model="form.property_approved" type="checkbox" />
        <span>{{ t("vendor.property_approved") }}</span>
      </label>
      <!-- Q11: the attestation is self-declared, and a false one is actionable —
           saying so here is what makes it an attestation rather than a checkbox -->
      <p class="field__hint">{{ t("vendor.property_approved_hint") }}</p>

      <button class="cta" type="submit" :disabled="busy || !canPublish">
        {{ t("vendor.publish") }}
      </button>

      <!-- the Q-4 floor, named field by field -->
      <ul v-if="missing.length" class="missing" role="alert">
        <li v-for="m in missing" :key="m">{{ t(`vendor.gap.${m}`) }}</li>
      </ul>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </form>

    <section class="card">
      <h3 class="card__title">{{ t("vendor.upcoming") }}</h3>
      <p v-if="!upcoming.length" class="card__empty">{{ t("portal.vendor.no_schedule") }}</p>
      <table v-else class="table">
        <tbody>
          <tr v-for="a in upcoming" :key="a.appearance_id">
            <td class="table__when">{{ when(a.starts_at) }}</td>
            <td>{{ a.facility_name || "—" }}</td>
            <td class="table__figure">{{ a.offerings.length }}</td>
            <td>
              <button class="link" type="button" @click="drop(a.appearance_id)">
                {{ t("portal.vendor.cancel") }}
              </button>
              <button
                v-if="a.series_id"
                class="link"
                type="button"
                @click="drop(a.appearance_id, true)"
              >
                {{ t("vendor.cancel_series") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="past.length" class="card">
      <h3 class="card__title">{{ t("vendor.past") }}</h3>
      <table class="table">
        <tbody>
          <tr v-for="a in past" :key="a.appearance_id">
            <td class="table__when">{{ when(a.starts_at) }}</td>
            <td>{{ a.facility_name || "—" }}</td>
            <!-- what a driver was shown for THAT window, kept as published -->
            <td class="table__figure">
              <template v-if="a.offerings.length">
                {{ formatMoney(Math.min(...a.offerings.map((o) => o.price_cents))) }}+
              </template>
            </td>
            <td>{{ t(`vendor.appearance.${a.status}`) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.week__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  margin-bottom: var(--s-4);
}
.week__title {
  margin: 0;
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
  font-size: var(--type-label-size);
  font-weight: 500;
  color: var(--text-2);
}
.card__empty {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.field {
  display: block;
  margin-bottom: var(--s-4);
  border: 0;
  padding: 0;
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
  margin-top: var(--s-1);
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.row {
  display: flex;
  gap: var(--s-3);
}
.row .field {
  flex: 1 1 0;
}
.picker {
  list-style: none;
  margin: 0 0 var(--s-4);
  padding: 0;
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  max-height: 220px;
  overflow-y: auto;
}
.picker__opt {
  display: flex;
  justify-content: space-between;
  gap: var(--s-3);
  width: 100%;
  min-height: 48px;
  padding: 0 var(--s-3);
  background: transparent;
  color: var(--text-1);
  font-size: var(--type-body-size);
  text-align: left;
}
.picker__type {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.days,
.items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}
.day,
.item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 48px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.day--on,
.item--on {
  border-color: var(--shield-500);
  color: var(--shield-500);
}
.item__price {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.check {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 48px;
  color: var(--text-1);
  font-size: var(--type-body-size);
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
.link {
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  text-decoration: none;
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
.table__when,
.table__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.missing {
  margin: var(--s-3) 0 0;
  padding-left: var(--s-4);
  color: var(--flare-500);
  font-size: var(--type-body-size);
}
.error {
  margin: var(--s-3) 0 0;
  color: var(--flare-500);
  font-size: var(--type-body-size);
}
</style>
