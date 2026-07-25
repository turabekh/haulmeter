<!-- AI-CONTEXT: the standing menu — what the cook sells and for how much, kept once
     instead of retyped for every appearance.

     The line that matters most on this screen is the note under the heading: editing
     a price changes what will be advertised NEXT. Every window already published
     keeps its own snapshot. A cook needs to know that before they change a number,
     or they will assume one of the two wrong things — that old listings silently
     update, or that they have to re-publish to fix a price going forward.

     PHASE A: a price is information. Nothing here takes an order or a payment. -->
<script setup>
import { onMounted, reactive, ref } from "vue";
import { Plus, Undo2 } from "lucide-vue-next";
import { useI18n } from "../../core/i18n.js";
import {
  addVendorMenuItem,
  fetchVendorMenu,
  retireVendorMenuItem,
  saveVendorMenuItem,
} from "../../core/api.js";
import { formatMoney } from "../../core/meter.js";

const { t } = useI18n();
const items = ref([]);
const retired = ref([]);
const error = ref(null);
const busy = ref(false);
const draft = reactive({ name: "", price: "", portions: "" });

async function load() {
  const all = await fetchVendorMenu(true).catch(() => []);
  items.value = all.filter((i) => i.is_active);
  retired.value = all.filter((i) => !i.is_active);
}
onMounted(load);

// dollars in the field, cents on the wire — a cook types 12.50, the API stores 1250
function toCents(text) {
  const n = Number.parseFloat(String(text).replace(/[^0-9.]/g, ""));
  return Number.isFinite(n) ? Math.round(n * 100) : null;
}

async function add() {
  const price_cents = toCents(draft.price);
  if (!draft.name.trim() || price_cents === null) return;
  busy.value = true;
  error.value = null;
  try {
    await addVendorMenuItem({
      name: draft.name.trim(),
      price_cents,
      portions: draft.portions ? Number.parseInt(draft.portions, 10) : null,
    });
    draft.name = "";
    draft.price = "";
    draft.portions = "";
    await load();
  } catch (e) {
    error.value = typeof e?.detail === "string" ? e.detail : t("vendor.menu_error");
  } finally {
    busy.value = false;
  }
}

async function savePrice(item, text) {
  const price_cents = toCents(text);
  if (price_cents === null || price_cents === item.price_cents) return;
  error.value = null;
  try {
    await saveVendorMenuItem(item.item_id, { price_cents });
    await load();
  } catch (e) {
    error.value = typeof e?.detail === "string" ? e.detail : t("vendor.menu_error");
    await load(); // put the shown value back to what the server actually holds
  }
}

async function retire(item) {
  await retireVendorMenuItem(item.item_id);
  await load();
}

async function restore(item) {
  await saveVendorMenuItem(item.item_id, { is_active: true });
  await load();
}
</script>

<template>
  <div class="menu">
    <h2 class="menu__title">{{ t("vendor.nav.menu") }}</h2>
    <!-- the thing a cook must know before changing a number -->
    <p class="menu__note">{{ t("vendor.menu_snapshot_note") }}</p>

    <section class="card">
      <table v-if="items.length" class="table">
        <thead>
          <tr>
            <th>{{ t("vendor.item") }}</th>
            <th>{{ t("vendor.price") }}</th>
            <th>{{ t("vendor.portions") }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="i in items" :key="i.item_id">
            <td>{{ i.name }}</td>
            <td>
              <input
                class="cell"
                type="text"
                inputmode="decimal"
                :value="(i.price_cents / 100).toFixed(2)"
                :aria-label="`${i.name} ${t('vendor.price')}`"
                @change="savePrice(i, $event.target.value)"
              />
            </td>
            <td class="table__figure">{{ i.portions ?? "—" }}</td>
            <td>
              <button class="link" type="button" @click="retire(i)">
                {{ t("vendor.retire") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="card__empty">{{ t("vendor.menu_empty") }}</p>
    </section>

    <section class="card">
      <h3 class="card__title">{{ t("vendor.add_item") }}</h3>
      <div class="row">
        <label class="field field--wide">
          <span class="field__label">{{ t("vendor.item") }}</span>
          <input v-model="draft.name" class="field__input" type="text" maxlength="120" />
        </label>
        <label class="field">
          <span class="field__label">{{ t("vendor.price") }}</span>
          <input v-model="draft.price" class="field__input" type="text" inputmode="decimal" />
        </label>
        <label class="field">
          <span class="field__label">{{ t("vendor.portions") }}</span>
          <input v-model="draft.portions" class="field__input" type="number" min="0" />
        </label>
      </div>
      <button class="cta" type="button" :disabled="busy || !draft.name || !draft.price" @click="add">
        <Plus :size="18" :stroke-width="2" aria-hidden="true" />
        {{ t("vendor.add_item") }}
      </button>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </section>

    <!-- retired rather than deleted: a seasonal dish comes back, and its price
         should come back with it -->
    <section v-if="retired.length" class="card">
      <h3 class="card__title">{{ t("vendor.retired") }}</h3>
      <ul class="retired">
        <li v-for="i in retired" :key="i.item_id" class="retired__row">
          <span>{{ i.name }}</span>
          <span class="table__figure">{{ formatMoney(i.price_cents) }}</span>
          <button class="link" type="button" @click="restore(i)">
            <Undo2 :size="16" :stroke-width="2" aria-hidden="true" />
            {{ t("vendor.restore") }}
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.menu__title {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.menu__note {
  margin: var(--s-2) 0 var(--s-4);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
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
.table {
  width: 100%;
  border-collapse: collapse;
}
.table th {
  padding: 0 var(--s-2) var(--s-2);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  font-weight: 400;
  text-align: left;
}
.table td {
  padding: var(--s-2);
  border-top: 1px solid var(--line-1);
  font-size: var(--type-body-size);
}
.table__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.cell {
  width: 96px;
  min-height: 44px;
  padding: 0 var(--s-2);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-body-size);
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-3);
}
.field {
  display: block;
  flex: 1 1 120px;
  margin-bottom: var(--s-3);
}
.field--wide {
  flex: 2 1 220px;
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
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
.retired {
  list-style: none;
  margin: 0;
  padding: 0;
}
.retired__row {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-2) 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.retired__row span:first-child {
  flex: 1 1 auto;
}
.error {
  margin: var(--s-3) 0 0;
  color: var(--flare-500);
  font-size: var(--type-body-size);
}
</style>
