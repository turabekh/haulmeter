<!-- AI-CONTEXT: the business's own details. Until this session only languages and the
     halal answer were editable here; a cook who moved city or changed their phone
     number had to ask support.

     The two fields the Q-4 floor checks are marked as such, because they are not
     optional in the way the others are: without them nothing can be published, and
     finding that out at publish time is the failure the floor exists to avoid. -->
<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import { fetchVendorProfile, saveVendorProfile } from "../../core/api.js";

const TYPES = ["food_mobile", "service_center"];

const { t } = useI18n();
const profile = ref(null);
const busy = ref(false);
const saved = ref(false);
const error = ref(null);

const CLAIMS = ["not_claimed", "self_declared", "certified"];

const form = reactive({
  name: "",
  vendor_type: "food_mobile",
  metro: "",
  contact_phone: "",
  categories: "",
  languages: "",
  halal_disclosure: "",
  halal_claim: "not_claimed",
});

const gaps = computed(() => profile.value?.profile_gaps ?? []);

function fill(p) {
  profile.value = p;
  form.name = p.name || "";
  form.vendor_type = p.vendor_type || "food_mobile";
  form.metro = p.metro || "";
  form.contact_phone = p.contact_phone || "";
  form.categories = (p.categories || []).join(", ");
  form.languages = (p.languages || []).join(", ");
  form.halal_disclosure = p.halal_disclosure || "";
  form.halal_claim = p.halal_claim || "not_claimed";
}

// only the rungs the SERVER will honour. `certified` appears once an approved halal
// certificate exists, so the control never promises something taken back on save.
const claimsAvailable = computed(
  () => profile.value?.halal_claims_available ?? ["not_claimed", "self_declared"],
);

function csv(text) {
  return text
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

async function save() {
  busy.value = true;
  saved.value = false;
  error.value = null;
  try {
    fill(
      await saveVendorProfile({
        name: form.name.trim(),
        vendor_type: form.vendor_type,
        metro: form.metro.trim(),
        contact_phone: form.contact_phone.trim(),
        categories: csv(form.categories),
        languages: csv(form.languages),
        halal_disclosure: form.halal_disclosure.trim(),
        halal_claim: form.halal_claim,
        // answering at all is what the floor checks — "no halal claim" is a complete
        // answer and a blank is not, so saving marks it answered
        halal_answered: true,
      }),
    );
    saved.value = true;
  } catch (e) {
    error.value = typeof e?.detail === "string" ? e.detail : t("vendor.save_error");
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  const p = await fetchVendorProfile().catch(() => null);
  if (p) fill(p);
});
</script>

<template>
  <div class="prof">
    <h2 class="prof__title">{{ t("portal.vendor.profile") }}</h2>

    <form class="card" @submit.prevent="save">
      <label class="field">
        <span class="field__label">{{ t("vendor.join.name") }}</span>
        <input v-model="form.name" class="field__input" type="text" maxlength="160" />
      </label>

      <fieldset class="field">
        <legend class="field__label">{{ t("vendor.join.type") }}</legend>
        <div class="types">
          <button
            v-for="ty in TYPES"
            :key="ty"
            type="button"
            class="type"
            :class="{ 'type--on': form.vendor_type === ty }"
            @click="form.vendor_type = ty"
          >
            {{ t(`vendor.type.${ty}`) }}
          </button>
        </div>
      </fieldset>

      <div class="row">
        <label class="field">
          <span class="field__label">{{ t("vendor.join.metro") }}</span>
          <input v-model="form.metro" class="field__input" type="text" maxlength="80" />
        </label>
        <label class="field">
          <span class="field__label">{{ t("vendor.phone") }}</span>
          <input v-model="form.contact_phone" class="field__input" type="tel" />
        </label>
      </div>

      <label class="field">
        <span class="field__label">{{ t("vendor.categories") }}</span>
        <input v-model="form.categories" class="field__input" type="text" />
      </label>

      <!-- the two the floor checks, marked as such rather than discovered later -->
      <label class="field">
        <span class="field__label">
          {{ t("vendor.languages") }}
          <span v-if="gaps.includes('languages')" class="req">{{ t("vendor.required") }}</span>
        </span>
        <input v-model="form.languages" class="field__input" type="text" />
        <span class="field__hint">{{ t("vendor.join.languages_hint") }}</span>
      </label>
      <label class="field">
        <span class="field__label">
          {{ t("vendor.halal") }}
          <span v-if="gaps.includes('halal_disclosure')" class="req">
            {{ t("vendor.required") }}
          </span>
        </span>
        <input v-model="form.halal_disclosure" class="field__input" type="text" />
        <span class="field__hint">{{ t("vendor.join.halal_hint") }}</span>
      </label>

      <!-- the same answer as a closed question, so drivers can FILTER on it. The
           sentence above is still what they read; this is what they search by, and
           keeping them separate is what stops the platform interpreting a cook (§23). -->
      <fieldset class="field">
        <legend class="field__label">{{ t("vendor.halal_claim_label") }}</legend>
        <div class="types">
          <button
            v-for="c in CLAIMS"
            :key="c"
            type="button"
            class="type"
            :class="{ 'type--on': form.halal_claim === c }"
            :disabled="!claimsAvailable.includes(c)"
            @click="form.halal_claim = c"
          >
            {{ t(`vendor.halal_claim.${c}`) }}
          </button>
        </div>
        <span class="field__hint">{{ t("vendor.halal_claim_hint") }}</span>
      </fieldset>

      <button class="cta" type="submit" :disabled="busy">{{ t("portal.vendor.save") }}</button>
      <p v-if="saved" class="ok">{{ t("vendor.saved") }}</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </form>
  </div>
</template>

<style scoped>
.prof__title {
  margin: 0 0 var(--s-4);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.card {
  padding: var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.field {
  display: block;
  flex: 1 1 200px;
  margin-bottom: var(--s-4);
  border: 0;
  padding: 0;
}
.field__label {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  margin-bottom: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.req {
  color: var(--marker-500);
  font-size: var(--type-caption-size);
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
  flex-wrap: wrap;
  gap: var(--s-3);
}
.types {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}
.type {
  flex: 1 1 auto;
  min-height: 48px;
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.type--on {
  border-color: var(--shield-500);
  color: var(--shield-500);
}
/* a rung the server will not honour is shown but not selectable — hiding it would
   leave a cook wondering how anyone gets certified */
.type:disabled {
  opacity: 0.45;
}
.cta {
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
.ok {
  margin: var(--s-3) 0 0;
  color: var(--ledger-500);
  font-size: var(--type-body-size);
}
.error {
  margin: var(--s-3) 0 0;
  color: var(--flare-500);
  font-size: var(--type-body-size);
}
</style>
