<!-- AI-CONTEXT: "the broker paid this" (M9, §23 entry 108). Until this existed nothing
     in the product could mark a receivable recovered — the state and F7's transition
     had no caller — so the Money tab's own Recovered figure was zero by construction.

     Composed, not invented (§22): BottomSheet is the shell, the candidate list follows
     PlaceSheet's offer-every-candidate shape (§23 entry 99), and the figure + single
     confirm follow PriceReportSheet. Fifteen tokens, all pre-existing.

     The confirm is a SECOND tap on purpose. `recovered` is terminal in F7's transition
     table — there is no "actually, they didn't" — so a one-tap list row would make an
     irreversible money statement out of a mis-tap in a moving truck.

     It records a FACT and moves no money: the broker pays the driver's own invoice into
     the driver's own bank, and saying otherwise would be the app claiming credit for a
     transfer it never handled. The note says so rather than leaving it implied. -->
<script setup>
import { ref, computed } from "vue";
import { useI18n } from "../i18n.js";
import { formatMoney } from "../meter.js";

const props = defineProps({
  rows: { type: Array, default: () => [] },
});
const emit = defineEmits(["submit"]);
const { t } = useI18n();

const selectedId = ref(null);
const selected = computed(() =>
  props.rows.find((r) => r.receivable_id === selectedId.value) ?? null,
);

function kindLabel(kind) {
  return t(`money.kind.${kind}`);
}
function pick(id) {
  selectedId.value = selectedId.value === id ? null : id;
}
</script>

<template>
  <div class="paid">
    <p class="paid__q">{{ t("money.paid.question") }}</p>

    <ul class="paid__list">
      <li v-for="r in rows" :key="r.receivable_id">
        <button
          type="button"
          class="paid__row"
          :class="{ 'paid__row--on': r.receivable_id === selectedId }"
          :aria-pressed="r.receivable_id === selectedId"
          @click="pick(r.receivable_id)"
        >
          <span class="paid__kind">{{ kindLabel(r.kind) }}</span>
          <span class="paid__amount">{{ formatMoney(r.amount_cents) }}</span>
        </button>
      </li>
    </ul>

    <p class="paid__note">{{ t("money.paid.note") }}</p>

    <button
      type="button"
      class="paid__submit"
      :disabled="!selected"
      @click="selected && emit('submit', selected.receivable_id)"
    >
      {{ t("money.paid.submit") }}
    </button>
  </div>
</template>

<style scoped>
.paid__q {
  margin: 0 0 var(--s-4);
  font-size: var(--type-body-size);
  color: var(--text-2);
}
.paid__list {
  list-style: none;
  margin: 0 0 var(--s-4);
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.paid__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  width: 100%;
  min-height: 56px;
  padding: var(--s-3) var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--text-1);
  font-size: var(--type-body-size);
  text-align: left;
}
/* selection is a FILL — shape and weight, never hue alone (§16 C-1) */
.paid__row--on {
  background: var(--ink-1);
  border-color: var(--text-1);
  font-weight: 600;
}
.paid__amount {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.paid__note {
  margin: 0 0 var(--s-4);
  font-size: var(--type-caption-size);
  color: var(--text-2);
}
.paid__submit {
  width: 100%;
  min-height: 56px;
  border: 0;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-body-size);
  font-weight: 600;
}
/* the established disabled treatment on this codebase's sheet CTAs */
.paid__submit:disabled {
  opacity: 0.5;
}
</style>
