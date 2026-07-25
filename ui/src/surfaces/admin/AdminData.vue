<!-- AI-CONTEXT: Data & ingest — where the map's facts come from and when they last
     arrived. Source URLs are shown because a wrong endpoint is the commonest cause
     of a silently stale layer, and it is invisible on every other surface. -->
<script setup>
import { onMounted, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import { fetchAdminIngest } from "../../core/api.js";

const { t } = useI18n();
const data = ref(null);

function stamp(iso) {
  // never localized: an operator correlating with logs needs one stable format
  return iso ? iso.replace("T", " ").slice(0, 16) : null;
}

onMounted(async () => {
  data.value = await fetchAdminIngest().catch(() => null);
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
</style>
