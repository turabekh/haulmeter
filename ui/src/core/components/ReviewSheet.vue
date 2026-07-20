<!-- AI-CONTEXT: Quick facility review (M2-FR4). One rating (1–5) + optional text —
     glove-friendly targets (§6.5), calm, one decision (S2). Full 10-aspect form
     is a follow-up; this captures an overall (would_return) + note. Server
     moderates before it's visible (PRD §13). -->
<script setup>
import { ref } from "vue";
import { Star } from "lucide-vue-next";
import { useI18n } from "../i18n.js";

const emit = defineEmits(["submit"]);
const { t } = useI18n();
const rating = ref(0);
const text = ref("");

function submit() {
  if (rating.value < 1) return;
  emit("submit", { ratings: { would_return: rating.value }, text: text.value || null });
}
</script>

<template>
  <div class="review">
    <p class="review__label">{{ t("review.overall") }}</p>
    <div class="review__stars" role="radiogroup" :aria-label="t('review.overall')">
      <button
        v-for="n in 5"
        :key="n"
        type="button"
        class="star"
        :class="{ 'star--on': n <= rating }"
        :aria-label="`${n}`"
        :aria-checked="n === rating"
        role="radio"
        @click="rating = n"
      >
        <Star :size="28" :stroke-width="2" aria-hidden="true" />
      </button>
    </div>
    <textarea
      v-model="text"
      class="review__text"
      :placeholder="t('review.placeholder')"
      rows="3"
    />
    <p class="review__note">{{ t("review.pending") }}</p>
    <button class="review__submit" type="button" :disabled="rating < 1" @click="submit">
      {{ t("review.submit") }}
    </button>
  </div>
</template>

<style scoped>
.review__label {
  margin: 0 0 var(--s-2);
  font-size: var(--type-body-size);
  color: var(--text-2);
}
.review__stars {
  display: flex;
  gap: var(--s-2);
}
.star {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
}
.star--on {
  color: var(--marker-500);
}
.review__text {
  width: 100%;
  margin-top: var(--s-3);
  padding: var(--s-3);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  color: var(--text-1);
  font-family: var(--font-sans);
  font-size: var(--type-body-size);
  resize: vertical;
}
.review__note {
  margin: var(--s-2) 0 var(--s-3);
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.review__submit {
  width: 100%;
  min-height: 56px;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.review__submit:disabled {
  opacity: 0.5;
}
</style>
