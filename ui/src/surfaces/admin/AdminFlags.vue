<!-- AI-CONTEXT: Flags & config (§23 E-D4, decision 3).

     The fix this section exists for: the old row showed one button whose LABEL was
     the action, so an operator read "Disable" and had to infer the flag was on. Now
     colour communicates STATE (a pill) and the button communicates the ACTION —
     two different jobs that were previously doing one badly.

     Disabling a module flag switches off a whole surface for every driver, so it
     gets a confirm step that names what it gates. Enabling does not: turning
     something on is recoverable by turning it off. -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import {
  fetchAdminFlags,
  toggleFlag,
  fetchConfig,
  fetchConfigScopes,
  saveConfig,
  setFlagGate,
} from "../../core/api.js";

const { t } = useI18n();
const flags = ref([]);
const search = ref("");
const confirming = ref(null);
const scopes = ref([]);
const scope = ref("global");
const config = ref({});
const declarations = ref({});
const errors = ref({});
const provenance = ref({});
const draft = ref({});

const FAMILY_ORDER = ["foundation", "ingest", "modules", "other"];

const grouped = computed(() => {
  const term = search.value.trim().toLowerCase();
  const match = flags.value.filter(
    (f) => !term || f.key.includes(term) || (f.description || "").toLowerCase().includes(term),
  );
  return FAMILY_ORDER.map((family) => ({
    family,
    items: match.filter((f) => f.family === family),
  })).filter((g) => g.items.length);
});

function state(flag) {
  if (flag.enabled) return { key: "admin.flag.on", token: "--ledger-500" };
  // a flag that CANNOT be enabled is a different fact from one merely switched off
  if (!flag.can_activate) return { key: "admin.flag.blocked", token: "--marker-500" };
  return { key: "admin.flag.off", token: "--text-3" };
}

async function load() {
  flags.value = await fetchAdminFlags();
}

async function apply(flag, enable) {
  await toggleFlag(flag.key, enable);
  confirming.value = null;
  await load();
}

function request(flag) {
  // decision 3: the confirm step is for the change that reaches every driver
  if (flag.enabled && flag.gates_a_module) {
    confirming.value = flag;
    return;
  }
  apply(flag, !flag.enabled);
}

async function toggleGate(flag, gate) {
  await setFlagGate(flag.key, { name: gate.name, satisfied: !gate.satisfied });
  await load();
}

// AI-CONTEXT: DECLARED keys as well as set ones. This panel rendered `body.entries` —
// rows that EXIST — so a key nobody had configured yet appeared nowhere, and A1 req 1's
// capture checklist is the first config any component in the product reads. "It is
// configuration, not code" is only true if an operator can find it.
async function loadConfig() {
  const body = await fetchConfig(scope.value);
  const declared = body.declared || {};
  const merged = {};
  for (const [key, row] of Object.entries(declared)) merged[key] = row.value;
  Object.assign(merged, body.entries || {});
  config.value = merged;
  declarations.value = declared;
  provenance.value = body.provenance || {};
  draft.value = Object.fromEntries(Object.entries(merged).map(([k, v]) => [k, asText(v)]));
  errors.value = {};
}

// an object rendered into a text input is "[object Object]", and saving that writes the
// string back — the operator destroys the config they opened the page to adjust.
function asText(value) {
  return value !== null && typeof value === "object" ? JSON.stringify(value) : value;
}

async function save(key) {
  const raw = draft.value[key];
  let value;
  const text = String(raw).trim();
  if (text.startsWith("{") || text.startsWith("[")) {
    // structured config (the capture checklist is a dict of stop type -> items).
    // A malformed edit must NOT be saved as its own broken text: `capture_checklist`
    // would read a quoted blob as a list of characters and ask for nothing coherent.
    try {
      value = JSON.parse(text);
    } catch {
      errors.value = { ...errors.value, [key]: true };
      return;
    }
  } else {
    // numbers stay numbers: a config read as "28" where 28 was meant is a silent
    // type change that only shows up as odd behaviour later
    value = raw !== "" && !isNaN(Number(raw)) ? Number(raw) : raw;
  }
  errors.value = { ...errors.value, [key]: false };
  await saveConfig(key, value, scope.value);
  await loadConfig();
}

onMounted(async () => {
  await load();
  scopes.value = await fetchConfigScopes().catch(() => []);
  if (scopes.value.length && !scopes.value.includes(scope.value)) scope.value = scopes.value[0];
  await loadConfig().catch(() => {});
});
</script>

<template>
  <div>
    <section class="panel">
      <h2 class="panel__title">{{ t("admin.flags") }}</h2>
      <input
        v-model="search"
        class="field__input flags__search"
        type="search"
        :placeholder="t('admin.flag.search')"
      />

      <div v-for="group in grouped" :key="group.family" class="flags__group">
        <h3 class="flags__family">{{ t(`admin.flag.family.${group.family}`) }}</h3>
        <table class="table">
          <tbody>
            <tr v-for="f in group.items" :key="f.key">
              <td class="table__name">
                {{ f.key }}
                <div class="table__muted">{{ f.description }}</div>
                <div v-if="f.last_changed_by" class="table__muted">
                  {{ t("admin.flag.last_changed") }}: {{ f.last_changed_by }}
                </div>
              </td>
              <td>
                <!-- STATE: colour + label, independent of the action button -->
                <span class="pill" :style="{ color: `var(${state(f).token})` }">
                  {{ t(state(f).key) }}
                </span>
              </td>
              <td class="table__muted">
                <!-- a gate can be WITHDRAWN as well as met: an activation
                     precondition that only ever ticks is a one-way ratchet -->
                <div v-for="g in f.gates" :key="g.name" class="gate">
                  <span :style="{ color: g.satisfied ? 'var(--ledger-500)' : 'var(--marker-500)' }">
                    {{ g.name }}{{ g.satisfied ? " ✓" : " ✗" }}
                  </span>
                  <button class="link" type="button" @click="toggleGate(f, g)">
                    {{ g.satisfied ? t("admin.gate.withdraw") : t("admin.gate.satisfy") }}
                  </button>
                </div>
              </td>
              <td>
                <!-- ACTION: what pressing it does, never doubling as the state -->
                <button
                  class="btn"
                  :class="{ 'btn--danger': f.enabled && f.gates_a_module }"
                  type="button"
                  :disabled="!f.enabled && !f.can_activate"
                  @click="request(f)"
                >
                  {{ f.enabled ? t("admin.disable") : t("admin.enable") }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- confirm names WHAT is being switched off, not just "are you sure" -->
    <div v-if="confirming" class="confirm" role="alertdialog">
      <p class="confirm__title">{{ t("admin.flag.confirm_title") }}</p>
      <p class="confirm__key">{{ confirming.key }} — {{ confirming.description }}</p>
      <p class="confirm__body">{{ t("admin.flag.confirm_body") }}</p>
      <button class="btn btn--danger" type="button" @click="apply(confirming, false)">
        {{ t("admin.confirm") }}
      </button>
      <button class="btn" type="button" @click="confirming = null">{{ t("admin.cancel") }}</button>
    </div>

    <section class="panel">
      <h2 class="panel__title">{{ t("admin.config_title") }}</h2>
      <label class="field">
        <span class="table__muted">{{ t("admin.scope") }}</span>
        <select v-model="scope" class="field__input" @change="loadConfig">
          <option v-for="s in scopes" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <table class="table">
        <tbody>
          <tr v-for="(value, key) in config" :key="key">
            <td class="table__name">
              {{ key }}
              <!-- what is tunable but untouched: an operator comparing what they
                   changed against what shipped needs to see which is which -->
              <div v-if="declarations[key] && !declarations[key].set" class="table__muted">
                {{ t("admin.cfg.default") }}
              </div>
              <div v-if="declarations[key]?.description" class="table__muted">
                {{ declarations[key].description }}
              </div>
              <!-- provenance: who set this, when, and what it replaced -->
              <div v-if="provenance[key]?.set_by" class="table__muted">
                {{ t("admin.cfg.set_by") }} {{ provenance[key].set_by }}
                <span v-if="provenance[key].previous !== null">
                  · {{ t("admin.cfg.was") }} {{ provenance[key].previous }}
                </span>
              </div>
            </td>
            <td>
              <input v-model="draft[key]" class="field__input" type="text" />
              <div v-if="errors[key]" class="table__muted">{{ t("admin.cfg.bad_json") }}</div>
            </td>
            <td>
              <button class="btn" type="button" @click="save(key)">{{ t("admin.add") }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
@import "./admin-shared.css";
.flags__search {
  width: 100%;
  margin-bottom: var(--s-3);
}
.flags__group {
  margin-top: var(--s-4);
}
.gate {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}
.link {
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-caption-size);
}
.flags__family {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  font-weight: 500;
}
.confirm {
  border: 1px solid var(--flare-500);
  border-radius: var(--r-card);
  padding: var(--s-4);
  margin-bottom: var(--s-4);
}
.confirm__title {
  margin: 0;
  font-size: var(--type-title-size);
}
.confirm__key {
  margin: var(--s-2) 0 0;
  font-family: var(--font-mono);
  font-size: var(--type-caption-size);
}
.confirm__body {
  margin: var(--s-2) 0 var(--s-3);
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.field {
  display: block;
  margin-bottom: var(--s-3);
}
</style>
