<!-- AI-CONTEXT: promotions (M13-FR6 / §23 Q10). Free in Phase A, labelled slots only,
     no price, bid or budget anywhere.

     Delivery is reported as what ACTUALLY went out. The `vendor_alert` class caps
     sends at one per driver per day on top of the §13.1 budget, respects quiet hours
     and per-vendor mutes, so "3 drivers told" is usually fewer than the number of
     drivers nearby. Reporting a reach figure instead would misrepresent the product
     to the person paying attention to it.

     Editing never re-sends. The alert budget was spent when the promotion was
     created; an edit that pushed again would be a way around the daily cap. -->
<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { Megaphone } from "lucide-vue-next";
import { useI18n } from "../../core/i18n.js";
import {
  cancelVendorPromotion,
  createVendorPromotion,
  editVendorPromotion,
  fetchVendorPromotions,
} from "../../core/api.js";

const MAX_CHARS = 140; // m13.MAX_PROMOTION_CHARS

const { t } = useI18n();
const promotions = ref([]);
const error = ref(null);
const draft = reactive({ text: "", days: 1, busy: false, delivered: null });
const editing = reactive({ id: null, text: "" });

const active = computed(() => promotions.value.filter((p) => p.status === "active"));
const finished = computed(() => promotions.value.filter((p) => p.status !== "active"));
const left = computed(() => MAX_CHARS - draft.text.length);

async function load() {
  promotions.value = await fetchVendorPromotions().catch(() => []);
}
onMounted(load);

async function add() {
  if (!draft.text.trim()) return;
  draft.busy = true;
  error.value = null;
  try {
    const starts = new Date();
    const result = await createVendorPromotion({
      text: draft.text.trim(),
      starts_at: starts.toISOString(),
      ends_at: new Date(starts.getTime() + draft.days * 86400000).toISOString(),
    });
    draft.delivered = result.alerts_delivered;
    draft.text = "";
    await load();
  } catch (e) {
    error.value = typeof e?.detail === "string" ? e.detail : t("vendor.promo_error");
  } finally {
    draft.busy = false;
  }
}

function startEdit(p) {
  editing.id = p.promotion_id;
  editing.text = p.text;
}

async function saveEdit() {
  error.value = null;
  try {
    await editVendorPromotion(editing.id, { text: editing.text.trim() });
    editing.id = null;
    await load();
  } catch (e) {
    error.value = typeof e?.detail === "string" ? e.detail : t("vendor.promo_error");
  }
}

async function drop(id) {
  await cancelVendorPromotion(id);
  await load();
}

function when(iso) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
</script>

<template>
  <div class="promos">
    <h2 class="promos__title">{{ t("vendor.nav.promotions") }}</h2>

    <section class="card">
      <h3 class="card__title">{{ t("portal.vendor.add_promotion") }}</h3>
      <label class="field">
        <span class="field__label">{{ t("vendor.promo_text") }}</span>
        <input v-model="draft.text" class="field__input" type="text" :maxlength="MAX_CHARS" />
        <span class="field__hint">{{ left }} {{ t("vendor.chars_left") }}</span>
      </label>
      <label class="field">
        <span class="field__label">{{ t("vendor.runs_for") }}</span>
        <select v-model.number="draft.days" class="field__input">
          <option :value="1">1 {{ t("vendor.days") }}</option>
          <option :value="3">3 {{ t("vendor.days") }}</option>
          <option :value="7">7 {{ t("vendor.days") }}</option>
        </select>
      </label>
      <button class="cta" type="button" :disabled="draft.busy || !draft.text" @click="add">
        <Megaphone :size="18" :stroke-width="2" aria-hidden="true" />
        {{ t("portal.vendor.add_promotion") }}
      </button>
      <!-- what actually went out, not what could have -->
      <p v-if="draft.delivered !== null" class="delivered">
        <span class="figure">{{ draft.delivered }}</span>
        {{ t("portal.vendor.delivered") }}
        <span class="delivered__why">{{ t("vendor.delivery_caps") }}</span>
      </p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </section>

    <section class="card">
      <h3 class="card__title">{{ t("vendor.running") }}</h3>
      <p v-if="!active.length" class="card__empty">{{ t("portal.vendor.no_promotions") }}</p>
      <table v-else class="table">
        <tbody>
          <tr v-for="p in active" :key="p.promotion_id">
            <td>
              <input
                v-if="editing.id === p.promotion_id"
                v-model="editing.text"
                class="field__input"
                type="text"
                :maxlength="MAX_CHARS"
              />
              <template v-else>{{ p.text }}</template>
            </td>
            <td class="table__when">{{ when(p.ends_at) }}</td>
            <td>
              <template v-if="editing.id === p.promotion_id">
                <button class="link" type="button" @click="saveEdit">{{ t("vendor.save") }}</button>
                <button class="link" type="button" @click="editing.id = null">
                  {{ t("vendor.cancel_edit") }}
                </button>
              </template>
              <template v-else>
                <button class="link" type="button" @click="startEdit(p)">
                  {{ t("vendor.edit") }}
                </button>
                <button class="link" type="button" @click="drop(p.promotion_id)">
                  {{ t("portal.vendor.cancel") }}
                </button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
      <!-- an edit reaches the pin, never the notification tray -->
      <p v-if="active.length" class="field__hint">{{ t("vendor.edit_no_resend") }}</p>
    </section>

    <section v-if="finished.length" class="card">
      <h3 class="card__title">{{ t("vendor.finished") }}</h3>
      <table class="table">
        <tbody>
          <tr v-for="p in finished" :key="p.promotion_id">
            <td>{{ p.text }}</td>
            <td class="table__when">{{ when(p.ends_at) }}</td>
            <td>{{ t(`vendor.promo.${p.status}`) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.promos__title {
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
  margin-top: var(--s-1);
  color: var(--text-3);
  font-size: var(--type-caption-size);
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
.delivered {
  margin: var(--s-3) 0 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.delivered__why {
  display: block;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.error {
  margin: var(--s-3) 0 0;
  color: var(--flare-500);
  font-size: var(--type-body-size);
}
</style>
