<!-- AI-CONTEXT: Modules — the register_admin_view registry, rendered honestly.

     Thirteen modules register an admin view; NONE of their destinations exist yet.
     Linking them all would create thirteen controls that 404 — the same dead-control
     anti-pattern removed from the driver app's empty state. So a view whose path has
     no route is listed with an explicit "registered, not built yet" marker and is
     NOT a link. The registry's value is knowing what exists; a link to nothing is
     worse than an honest label.

     Future modules slot in automatically: when a destination route appears, the
     entry becomes a link with no change here. -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "../../core/i18n.js";
import { fetchAdminViews } from "../../core/api.js";

const { t } = useI18n();
const router = useRouter();
const views = ref([]);

// a destination is "built" only if the router can actually resolve it
const resolved = computed(() =>
  views.value.map((v) => {
    const match = router.resolve(v.path);
    return { ...v, built: match.matched.length > 0 };
  }),
);

onMounted(async () => {
  views.value = await fetchAdminViews().catch(() => []);
});
</script>

<template>
  <section class="panel">
    <h2 class="panel__title">{{ t("admin.views") }}</h2>
    <table class="table">
      <tbody>
        <tr v-for="v in resolved" :key="v.key">
          <td class="table__name">{{ v.title }}</td>
          <td class="table__muted">{{ v.module }}</td>
          <td>
            <router-link v-if="v.built" :to="v.path" class="link">{{ v.path }}</router-link>
            <span v-else class="table__muted">{{ t("admin.mod.not_built") }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
@import "./admin-shared.css";
.link {
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
</style>
