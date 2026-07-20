<!-- AI-CONTEXT: F14 Admin Console — a web-first operator portal (design-prd §18,
     like the Fleet Workspace): desktop-first, comfortable tables, 1200 dp cap,
     shares ui/core tokens, NOT a driver-app screen (no tab chrome; meta.portal
     widens the frame). platform_admin only — a 403 shows the no-access notice.
     Feature flags (with activation gates) toggle here; module admin views and
     the moderation queue are listed. Reached at /admin. -->
<script setup>
import { ref, onMounted } from "vue";
import { useI18n } from "../core/i18n.js";
import {
  fetchAdminFlags,
  fetchAdminViews,
  fetchModeration,
  toggleFlag,
  decideModeration,
} from "../core/api.js";

const { t } = useI18n();
const denied = ref(false);
const flags = ref([]);
const views = ref([]);
const moderation = ref([]);

async function load() {
  try {
    [flags.value, views.value, moderation.value] = await Promise.all([
      fetchAdminFlags(),
      fetchAdminViews(),
      fetchModeration(),
    ]);
  } catch {
    denied.value = true; // 403 (not a platform admin) or offline
  }
}
onMounted(load);

async function onToggle(f) {
  try {
    const res = await toggleFlag(f.key, !f.enabled);
    f.enabled = res.enabled;
  } catch {
    /* gated flag can't enable (409) — the gates column shows why */
  }
}
async function onDecide(item, approve) {
  try {
    await decideModeration(item.id, approve);
    moderation.value = moderation.value.filter((m) => m.id !== item.id);
  } catch {
    /* offline */
  }
}
</script>

<template>
  <div class="admin">
    <h1 class="admin__title">{{ t("admin.title") }}</h1>

    <p v-if="denied" class="muted">{{ t("admin.no_access") }}</p>

    <template v-else>
      <!-- Feature flags (F13) -->
      <section class="panel">
        <h2 class="panel__title">{{ t("admin.flags") }}</h2>
        <table class="table">
          <tbody>
            <tr v-for="f in flags" :key="f.key">
              <td>
                <span class="flag__key">{{ f.key }}</span>
                <span v-if="f.gates.length" class="flag__gates">
                  {{ f.gates.filter((g) => g.satisfied).length }}/{{ f.gates.length }}
                  {{ t("admin.gates") }}
                </span>
              </td>
              <td class="num">
                <button
                  class="toggle"
                  :class="f.enabled ? 'toggle--on' : ''"
                  type="button"
                  :disabled="!f.enabled && !f.can_activate"
                  @click="onToggle(f)"
                >
                  {{ f.enabled ? t("admin.disable") : t("admin.enable") }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <div class="grid">
        <!-- Module admin views (F14 registrations) -->
        <section class="panel">
          <h2 class="panel__title">{{ t("admin.views") }}</h2>
          <table class="table">
            <thead>
              <tr>
                <th>{{ t("admin.module") }}</th>
                <th>{{ t("admin.title") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in views" :key="v.key">
                <td class="mono">{{ v.module }}</td>
                <td>{{ v.title }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <!-- Moderation queue (F14) -->
        <section class="panel">
          <h2 class="panel__title">{{ t("admin.moderation") }}</h2>
          <ul v-if="moderation.length" class="mod">
            <li v-for="m in moderation" :key="m.id" class="mod__row">
              <span class="mono">{{ m.content_kind }}</span>
              <span class="mod__actions">
                <button class="mini mini--ok" type="button" @click="onDecide(m, true)">
                  {{ t("admin.approve") }}
                </button>
                <button class="mini mini--no" type="button" @click="onDecide(m, false)">
                  {{ t("admin.reject") }}
                </button>
              </span>
            </li>
          </ul>
          <p v-else class="muted">{{ t("admin.mod_empty") }}</p>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.admin {
  padding: var(--s-5);
}
.admin__title {
  margin: 0 0 var(--s-4);
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
.panel {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
  margin-bottom: var(--s-4);
  overflow-x: auto;
}
.panel__title {
  margin: 0 0 var(--s-3);
  font-size: var(--type-label-size);
  color: var(--text-2);
  font-weight: 500;
}
.grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--s-4);
}
@media (min-width: 720px) {
  .grid {
    grid-template-columns: 1fr 1fr;
  }
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--type-body-size);
}
.table th,
.table td {
  text-align: left;
  padding: var(--s-2) var(--s-3);
  border-bottom: 1px solid var(--line-1);
}
.table th {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  font-weight: 500;
}
.table .num {
  text-align: right;
}
.mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.flag__key {
  font-weight: 500;
}
.flag__gates {
  margin-left: var(--s-2);
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.toggle {
  min-height: 40px;
  padding: 0 var(--s-4);
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: transparent;
  color: var(--text-1);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.toggle--on {
  background: var(--ledger-500);
  color: var(--on-accent);
  border-color: var(--ledger-500);
}
.toggle:disabled {
  opacity: 0.5;
}
.mod {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.mod__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  padding: var(--s-2) 0;
  border-bottom: 1px solid var(--line-1);
}
.mod__actions {
  display: flex;
  gap: var(--s-2);
}
.mini {
  min-height: 36px;
  padding: 0 var(--s-3);
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: transparent;
  font-size: var(--type-caption-size);
  font-weight: 500;
}
.mini--ok {
  color: var(--ledger-500);
}
.mini--no {
  color: var(--flare-500);
}
.muted {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
</style>
