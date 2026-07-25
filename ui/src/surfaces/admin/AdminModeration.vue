<!-- AI-CONTEXT: Moderation — one queue for every reported kind, with the 72h SLA
     made visible. Q-8's promise is only real if a moderator can SEE what is late.

     Three verdicts, not two (decision 4c): uphold (content stays down), dismiss (it
     comes back), and frivolous (it comes back AND the strike lands on the reporter).
     Without the third a moderator can only ever penalise the reported party, which
     makes the report button a free weapon. -->
<script setup>
import { onMounted, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import { fetchModeration, resolveReport } from "../../core/api.js";

const { t } = useI18n();
const items = ref([]);
const busy = ref(null);

async function load() {
  items.value = await fetchModeration();
}

async function resolve(item, { approve, frivolous = false }) {
  busy.value = item.id;
  try {
    await resolveReport(item.content_kind, item.content_ref, { approve, frivolous });
    await load();
  } finally {
    busy.value = null;
  }
}

onMounted(load);
</script>

<template>
  <section class="panel">
    <h2 class="panel__title">{{ t("admin.moderation") }}</h2>
    <p v-if="!items.length" class="panel__empty">{{ t("admin.mod.empty") }}</p>
    <table v-else class="table">
      <tbody>
        <tr v-for="item in items" :key="item.id" :class="{ 'row--late': item.overdue }">
          <td class="table__name">{{ item.content_kind }}</td>
          <td class="table__figure">{{ item.reports }}</td>
          <td class="table__figure">
            {{ item.age_hours }}h
            <!-- overdue is colour + label, never colour alone (§16 C-1) -->
            <span v-if="item.overdue" class="pill pill--late">{{ t("admin.ov.overdue") }}</span>
          </td>
          <td class="mod__actions">
            <button class="btn" type="button" :disabled="busy === item.id" @click="resolve(item, { approve: true })">
              {{ t("admin.mod.uphold") }}
            </button>
            <button class="btn" type="button" :disabled="busy === item.id" @click="resolve(item, { approve: false })">
              {{ t("admin.mod.dismiss") }}
            </button>
            <button
              class="btn btn--danger"
              type="button"
              :disabled="busy === item.id"
              @click="resolve(item, { approve: false, frivolous: true })"
            >
              {{ t("admin.mod.frivolous") }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
@import "./admin-shared.css";
.pill--late {
  color: var(--flare-500);
  margin-left: var(--s-2);
}
.row--late .table__figure {
  color: var(--flare-500);
}
.mod__actions {
  display: flex;
  gap: var(--s-2);
  flex-wrap: wrap;
}
</style>
