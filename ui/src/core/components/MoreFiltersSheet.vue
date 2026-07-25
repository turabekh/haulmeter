<!-- AI-CONTEXT: the "More filters" sheet §11.3 has specified since v1.0 and nobody
     had built — `PresetChips.vue`'s own header already referred to it.

     "Presets over filters" is the law: presets remain the interface, and this sheet
     is the ONE place a driver narrows further. It exists because the food layer
     collects three facts the publish floor already forces a cook to provide —
     languages, a halal answer, a priced dish — and until now a driver could read all
     three only by opening vendors one at a time.

     Rules this sheet must not soften:
     · A filter NARROWS. The server applies it after the §E1.9 quality laws and the
       Q-3 ranking, so nothing here can surface a lapsed listing or reorder anything.
     · The halal chip carries the RUNG, never a bare "Halal". `self_declared` reads
       "vendor says halal", because the platform makes no halal claim of its own
       (§23) — the cook does, and the label says who.
     · Everything is bounded by the current view. An empty result means "none here",
       and the caller says exactly that.
     · DRIVING: this sheet is never opened at speed (Forbidden #11 — no keyboard
       while moving). Filters already set keep narrowing the corridor. -->
<script setup>
import { computed, reactive, watch } from "vue";
import { Check } from "lucide-vue-next";
import { useI18n } from "../i18n.js";

// the six shipped locales, offered as "who speaks my language" — a driver picks,
// nothing is pre-selected. Defaulting a filter would silently hide vendors.
const LANGUAGES = ["en", "es", "pa", "ru", "uz", "so"];
const HALAL_RUNGS = ["self_declared", "certified"];

const props = defineProps({
  modelValue: { type: Object, default: () => ({ q: "", language: "", halal: "" }) },
});
const emit = defineEmits(["update:modelValue", "close"]);
const { t } = useI18n();

const draft = reactive({ q: "", language: "", halal: "" });
watch(
  () => props.modelValue,
  (v) => Object.assign(draft, { q: "", language: "", halal: "", ...v }),
  { immediate: true, deep: true },
);

const active = computed(() => !!(draft.q.trim() || draft.language || draft.halal));

function toggle(key, value) {
  draft[key] = draft[key] === value ? "" : value;
}

function apply() {
  emit("update:modelValue", { q: draft.q.trim(), language: draft.language, halal: draft.halal });
  emit("close");
}

function clear() {
  Object.assign(draft, { q: "", language: "", halal: "" });
  emit("update:modelValue", { q: "", language: "", halal: "" });
  emit("close");
}
</script>

<template>
  <div class="filters">
    <label class="field">
      <span class="field__label">{{ t("filters.dish") }}</span>
      <input
        v-model="draft.q"
        class="field__input"
        type="search"
        :placeholder="t('filters.dish_placeholder')"
        maxlength="60"
      />
      <!-- §11.7-shaped honesty: the search is bounded, and saying so here stops an
           empty result reading as "nobody anywhere cooks this" -->
      <span class="field__hint">{{ t("filters.in_view") }}</span>
    </label>

    <fieldset class="field">
      <legend class="field__label">{{ t("filters.halal") }}</legend>
      <div class="chips">
        <button
          v-for="rung in HALAL_RUNGS"
          :key="rung"
          type="button"
          class="chip"
          :class="{ 'chip--on': draft.halal === rung }"
          :aria-pressed="draft.halal === rung"
          @click="toggle('halal', rung)"
        >
          <Check v-if="draft.halal === rung" :size="16" :stroke-width="2" aria-hidden="true" />
          {{ t(`vendor.halal_claim.${rung}`) }}
        </button>
      </div>
      <!-- who is speaking, said in the sheet as well as on the label -->
      <span class="field__hint">{{ t("filters.halal_hint") }}</span>
    </fieldset>

    <fieldset class="field">
      <legend class="field__label">{{ t("filters.language") }}</legend>
      <div class="chips">
        <button
          v-for="code in LANGUAGES"
          :key="code"
          type="button"
          class="chip"
          :class="{ 'chip--on': draft.language === code }"
          :aria-pressed="draft.language === code"
          @click="toggle('language', code)"
        >
          <Check v-if="draft.language === code" :size="16" :stroke-width="2" aria-hidden="true" />
          {{ t(`locale.${code}`) }}
        </button>
      </div>
    </fieldset>

    <button class="cta" type="button" @click="apply">{{ t("filters.apply") }}</button>
    <button v-if="active" class="cta cta--secondary" type="button" @click="clear">
      {{ t("filters.clear") }}
    </button>
  </div>
</template>

<style scoped>
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
  min-height: 56px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.field__hint {
  display: block;
  margin-top: var(--s-2);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
/* the existing chip shape (§11.3 preset row), reused — no new component pattern */
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}
.chip {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 48px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.chip--on {
  border-color: var(--shield-500);
  color: var(--shield-500);
}
.cta {
  display: block;
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-3);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta--secondary {
  margin-top: var(--s-2);
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
}
</style>
