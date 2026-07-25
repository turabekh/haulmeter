<!-- AI-CONTEXT: Audit — who did what, and what it changed FROM.

     Timestamps are ISO-trimmed and never localized: an operator correlating the log
     with container output needs one stable format, and a locale-shifted time is a
     different string in every reader's browser. -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import { fetchAuditFiltered } from "../../core/api.js";

const { t } = useI18n();
const entries = ref([]);
const filter = ref("");

const actions = computed(() => [...new Set(entries.value.map((e) => e.action))].sort());
const shown = computed(() =>
  filter.value ? entries.value.filter((e) => e.action === filter.value) : entries.value,
);

function stamp(iso) {
  return iso ? iso.replace("T", " ").slice(0, 16) : "";
}

function summarize(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([k, v]) => `${k}=${v}`)
      .join(" ");
  }
  return String(value);
}

onMounted(async () => {
  entries.value = await fetchAuditFiltered({ limit: 200 }).catch(() => []);
});
</script>

<template>
  <section class="panel">
    <h2 class="panel__title">{{ t("admin.audit_title") }}</h2>
    <label class="field">
      <span class="table__muted">{{ t("admin.audit.filter_actor") }}</span>
      <select v-model="filter" class="field__input">
        <option value="">—</option>
        <option v-for="a in actions" :key="a" :value="a">{{ a }}</option>
      </select>
    </label>
    <p v-if="!shown.length" class="panel__empty">{{ t("admin.audit_empty") }}</p>
    <table v-else class="table">
      <thead>
        <tr>
          <th class="table__muted">{{ t("admin.audit_when") }}</th>
          <th class="table__muted">{{ t("admin.audit_who") }}</th>
          <th class="table__muted">{{ t("admin.audit_what") }}</th>
          <th class="table__muted">{{ t("admin.audit.changed") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="e in shown" :key="e.id">
          <td class="table__figure">{{ stamp(e.created_at) }}</td>
          <td class="table__muted">{{ e.actor || "—" }}</td>
          <td class="table__name">
            {{ e.action }}
            <div class="table__muted">{{ e.target_key || e.target_kind || "" }}</div>
          </td>
          <!-- what it was -> what it became: the question actually asked afterwards -->
          <td class="table__muted">
            <span v-if="e.before || e.after">
              {{ summarize(e.before) }} → {{ summarize(e.after) }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
@import "./admin-shared.css";
.field {
  display: block;
  margin-bottom: var(--s-3);
}
</style>
