<!-- AI-CONTEXT: Accounts (§23 E-D6) — the operator's user directory.

     Built for the phone case: someone rings, the operator finds them by whatever
     fact they have to hand (email, name, MC/DOT, plate), and fixes the thing.

     Three rules this surface must not soften:
     · **A temporary password is shown once, and the copy says so.** Nothing here
       ever reads a permanent password, because support that can read a password can
       be social-engineered into surrendering one.
     · **There is no delete.** The section says why, in place, rather than leaving an
       operator hunting for a button that will never exist.
     · **Granting platform admin confirms first and names the consequence** — it
       hands over every power in this console, including granting it onward. -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import {
  fetchAccounts,
  fetchAccount,
  createAccount,
  editAccount,
  resetCredential,
  deactivateAccount,
  reactivateAccount,
  changeRole,
  registerVendorAsAdmin,
} from "../../core/api.js";

const { t } = useI18n();
const search = ref("");
const accounts = ref([]);
const selected = ref(null);
const draft = ref({});
const newAccount = ref({ email: "", display_name: "", role: "driver" });
// shown exactly once, then dropped from memory on the next action
const temporary = ref(null);
const confirmAdmin = ref(false);
const error = ref("");
const busy = ref(false);

const ROLES = ["driver", "vendor", "fleet_admin", "property_owner"];

const isAdmin = computed(() => selected.value?.roles?.includes("platform_admin"));

function stamp(iso) {
  // never localized: an operator correlating with logs needs one stable format
  return iso ? iso.replace("T", " ").slice(0, 16) : "";
}

async function load() {
  accounts.value = await fetchAccounts({ q: search.value || undefined }).catch(() => []);
}

async function open(id) {
  temporary.value = null;
  confirmAdmin.value = false;
  selected.value = await fetchAccount(id);
  draft.value = {
    display_name: selected.value.display_name || "",
    legal_name: selected.value.profile?.legal_name || "",
    mc_number: selected.value.profile?.mc_number || "",
    dot_number: selected.value.profile?.dot_number || "",
    plate_state: selected.value.profile?.plate_state || "",
    plate_number: selected.value.profile?.plate_number || "",
    unit_number: selected.value.profile?.unit_number || "",
  };
}

async function act(fn) {
  error.value = "";
  busy.value = true;
  try {
    return await fn();
  } catch (e) {
    error.value = e.detail?.error || e.message;
    return null;
  } finally {
    busy.value = false;
  }
}

async function submitNew() {
  const created = await act(() => createAccount(newAccount.value));
  if (!created) return;
  temporary.value = created.temporary_password;
  newAccount.value = { email: "", display_name: "", role: "driver" };
  await load();
  await open(created.account_id);
  // re-set after open() clears it: the operator still has to read it out
  temporary.value = created.temporary_password;
}

async function save() {
  const updated = await act(() => editAccount(selected.value.account_id, draft.value));
  if (updated) selected.value = { ...selected.value, ...updated };
  await load();
}

async function reset() {
  const body = await act(() => resetCredential(selected.value.account_id));
  if (body) {
    temporary.value = body.temporary_password;
    selected.value = await fetchAccount(selected.value.account_id);
  }
}

async function toggleActive() {
  const id = selected.value.account_id;
  const updated = await act(() =>
    selected.value.active ? deactivateAccount(id) : reactivateAccount(id),
  );
  if (updated) selected.value = { ...selected.value, ...updated };
  await load();
}

async function role(name, grant, confirm = false) {
  const updated = await act(() =>
    changeRole(selected.value.account_id, { role: name, grant, confirm }),
  );
  if (updated) {
    selected.value = { ...selected.value, ...updated };
    confirmAdmin.value = false;
  }
}

async function makeVendor() {
  const created = await act(() =>
    registerVendorAsAdmin({
      owner_account_id: selected.value.account_id,
      name: selected.value.display_name || selected.value.email,
    }),
  );
  if (created) await open(selected.value.account_id);
}

onMounted(load);
</script>

<template>
  <div>
    <section class="panel">
      <h2 class="panel__title">{{ t("admin.nav.accounts") }}</h2>
      <input
        v-model="search"
        class="field__input acct__search"
        type="search"
        :placeholder="t('admin.acct.search')"
        @keyup.enter="load"
      />
      <p v-if="!accounts.length" class="panel__empty">{{ t("admin.acct.empty") }}</p>
      <table v-else class="table">
        <tbody>
          <tr v-for="a in accounts" :key="a.account_id">
            <td class="table__name">
              <button class="link" type="button" @click="open(a.account_id)">{{ a.email }}</button>
              <div class="table__muted">{{ a.display_name }}</div>
            </td>
            <td class="table__muted">{{ a.roles.join(", ") }}</td>
            <td>
              <!-- state is colour + label, never colour alone (§16 C-1) -->
              <span
                class="pill"
                :style="{ color: a.active ? 'var(--ledger-500)' : 'var(--text-3)' }"
              >{{ a.active ? t("admin.acct.active") : t("admin.acct.inactive") }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <!-- the absence of a delete button is explained where it would have been -->
      <p class="panel__note">{{ t("admin.acct.no_delete") }}</p>
    </section>

    <section class="panel">
      <h2 class="panel__title">{{ t("admin.acct.create") }}</h2>
      <div class="acct__form">
        <input v-model="newAccount.email" class="field__input" type="email" :placeholder="t('admin.acct.email')" />
        <input v-model="newAccount.display_name" class="field__input" type="text" :placeholder="t('admin.acct.name')" />
        <select v-model="newAccount.role" class="field__input">
          <option v-for="r in ROLES" :key="r" :value="r">{{ r }}</option>
        </select>
        <button class="btn btn--accent" type="button" :disabled="busy || !newAccount.email" @click="submitNew">
          {{ t("admin.acct.create") }}
        </button>
      </div>
    </section>

    <section v-if="selected" class="panel">
      <h2 class="panel__title">{{ selected.email }}</h2>
      <p v-if="error" class="acct__error" role="alert">{{ error }}</p>

      <!-- shown ONCE; the copy says so rather than letting an operator assume they
           can come back for it -->
      <p v-if="temporary" class="acct__temp" role="status">
        <span class="table__figure">{{ temporary }}</span>
        — {{ t("admin.acct.temp_password") }}
      </p>
      <p v-if="selected.must_change_credential" class="table__muted">
        {{ t("admin.acct.must_change") }}
      </p>

      <div class="acct__form">
        <input v-model="draft.display_name" class="field__input" type="text" :placeholder="t('admin.acct.name')" />
        <input v-model="draft.legal_name" class="field__input" type="text" placeholder="legal name" />
        <input v-model="draft.mc_number" class="field__input" type="text" placeholder="MC" />
        <input v-model="draft.dot_number" class="field__input" type="text" placeholder="DOT" />
        <input v-model="draft.plate_state" class="field__input" type="text" maxlength="2" placeholder="ST" />
        <input v-model="draft.plate_number" class="field__input" type="text" placeholder="plate" />
        <input v-model="draft.unit_number" class="field__input" type="text" placeholder="unit" />
        <button class="btn btn--accent" type="button" :disabled="busy" @click="save">
          {{ t("portal.vendor.save") }}
        </button>
      </div>

      <div class="acct__actions">
        <button class="btn" type="button" :disabled="busy" @click="reset">
          {{ t("admin.acct.reset") }}
        </button>
        <button
          class="btn"
          :class="{ 'btn--danger': selected.active }"
          type="button"
          :disabled="busy"
          @click="toggleActive"
        >
          {{ selected.active ? t("admin.acct.deactivate") : t("admin.acct.reactivate") }}
        </button>
        <button
          v-if="selected.roles.includes('vendor')"
          class="btn"
          type="button"
          :disabled="busy"
          @click="makeVendor"
        >
          {{ t("admin.acct.register_vendor") }}
        </button>
      </div>

      <div class="acct__roles">
        <span class="table__muted">{{ t("admin.acct.role") }}: {{ selected.roles.join(", ") }}</span>
        <button
          v-for="r in ROLES.filter((r) => !selected.roles.includes(r))"
          :key="r"
          class="btn"
          type="button"
          :disabled="busy"
          @click="role(r, true)"
        >
          + {{ r }}
        </button>
        <!-- the loudest control on the page: it hands over every power here -->
        <button
          v-if="!isAdmin"
          class="btn btn--danger"
          type="button"
          :disabled="busy"
          @click="confirmAdmin = true"
        >
          {{ t("admin.acct.grant_admin") }}
        </button>
      </div>

      <div v-if="confirmAdmin" class="confirm" role="alertdialog">
        <p class="confirm__body">{{ t("admin.acct.admin_confirm") }}</p>
        <button class="btn btn--danger" type="button" @click="role('platform_admin', true, true)">
          {{ t("admin.confirm") }}
        </button>
        <button class="btn" type="button" @click="confirmAdmin = false">
          {{ t("admin.cancel") }}
        </button>
      </div>

      <h3 class="acct__sub">{{ t("admin.acct.history") }}</h3>
      <table class="table">
        <tbody>
          <tr v-for="(a, i) in selected.audit" :key="i">
            <td class="table__figure">{{ stamp(a.created_at) }}</td>
            <td class="table__name">{{ a.action }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
@import "./admin-shared.css";
.acct__search {
  width: 100%;
  margin-bottom: var(--s-3);
}
.acct__form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin-bottom: var(--s-3);
}
.acct__actions,
.acct__roles {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-3);
}
.acct__sub {
  margin: var(--s-4) 0 0;
  color: var(--text-2);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.acct__temp {
  margin: var(--s-2) 0;
  padding: var(--s-3);
  border: 1px solid var(--marker-500);
  border-radius: var(--r-control);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.acct__error {
  margin: 0 0 var(--s-2);
  color: var(--flare-500);
  font-size: var(--type-caption-size);
}
.confirm {
  margin-top: var(--s-3);
  padding: var(--s-3);
  border: 1px solid var(--flare-500);
  border-radius: var(--r-card);
}
.confirm__body {
  margin: 0 0 var(--s-3);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.link {
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-body-size);
}
</style>
