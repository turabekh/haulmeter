<!-- AI-CONTEXT: Vendors — the verification queue, the roster, and claim disputes.
     Reliability and strikes are shown as the raw pairs a vendor and a driver both
     see; there is no operator-only variant of a number that exists elsewhere. -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import {
  fetchAdminVendors,
  fetchVendorDetail,
  startImpersonation,
  setImpersonation,
  registerVendorAsAdmin,
  editVendorProfile,
  assistCancelAppearance,
  assistCreatePromotion,
  assistCancelPromotion,
  fetchAccounts,
  decideVendor,
  fetchAdminClaims,
  decideClaim,
} from "../../core/api.js";

const { t } = useI18n();
const vendors = ref([]);
const claims = ref([]);

const awaiting = computed(() =>
  vendors.value.filter((v) => v.verify_status === "documents_on_file"),
);

const TIER_TOKEN = {
  verified: "--ledger-500",
  documents_on_file: "--text-2", // paperwork on file is not an endorsement (§23)
  unverified: "--text-3",
};

async function load() {
  [vendors.value, claims.value] = await Promise.all([fetchAdminVendors(), fetchAdminClaims()]);
}

async function verify(vendor) {
  await decideVendor(vendor.vendor_id, { verify_status: "verified" });
  await load();
}

async function suspend(vendor, suspended) {
  await decideVendor(vendor.vendor_id, { suspended });
  await load();
}

const detail = ref(null);
const edit = ref({});
const error = ref("");
const promoDraft = ref({ text: "", days: 1 });
// E-D5 mode (a): registering a vendor with the fields that make them PUBLISHABLE.
// A form that captures only a name creates a vendor blocked by the Q-4 floor the
// moment they try to publish, which is a worse outcome than no form at all.
const newVendor = ref({
  owner_email: "",
  name: "",
  vendor_type: "food_mobile",
  metro: "",
  contact_phone: "",
  languages: "",
  halal_disclosure: "",
});

async function openDetail(vendorId) {
  error.value = "";
  detail.value = await fetchVendorDetail(vendorId).catch(() => null);
  if (detail.value) {
    edit.value = {
      name: detail.value.name,
      metro: detail.value.metro,
      contact_phone: detail.value.contact_phone,
      languages: (detail.value.languages || []).join(", "),
      halal_disclosure: detail.value.halal_disclosure || "",
    };
  }
}

function splitList(value) {
  return (value || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

async function saveVendor() {
  error.value = "";
  try {
    await editVendorProfile(detail.value.vendor_id, {
      name: edit.value.name,
      metro: edit.value.metro,
      contact_phone: edit.value.contact_phone,
      languages: splitList(edit.value.languages),
      halal_disclosure: edit.value.halal_disclosure,
      // answering at all is what the Q-4 floor checks; "none" is a valid answer
      halal_answered: Boolean(edit.value.halal_disclosure.trim()),
    });
    await openDetail(detail.value.vendor_id);
    await load();
  } catch (e) {
    error.value = e.detail?.error || e.message;
  }
}

async function addVendor() {
  error.value = "";
  const match = (await fetchAccounts({ q: newVendor.value.owner_email }).catch(() => []))[0];
  if (!match) {
    error.value = "no account with that email — create it in Accounts first";
    return;
  }
  try {
    const created = await registerVendorAsAdmin({
      owner_account_id: match.account_id,
      name: newVendor.value.name,
      vendor_type: newVendor.value.vendor_type,
      metro: newVendor.value.metro,
      contact_phone: newVendor.value.contact_phone || null,
      languages: splitList(newVendor.value.languages),
      halal_disclosure: newVendor.value.halal_disclosure || null,
      halal_answered: Boolean(newVendor.value.halal_disclosure.trim()),
    });
    newVendor.value = {
      owner_email: "", name: "", vendor_type: "food_mobile",
      metro: "", contact_phone: "", languages: "", halal_disclosure: "",
    };
    await load();
    await openDetail(created.vendor_id);
  } catch (e) {
    error.value = e.detail?.existing_vendor_id
      ? "that cook is already registered"
      : e.detail?.error || e.message;
  }
}

async function dropAppearance(id) {
  await assistCancelAppearance(detail.value.vendor_id, id);
  await openDetail(detail.value.vendor_id);
}

async function addPromotion() {
  if (!promoDraft.value.text.trim()) return;
  const starts = new Date();
  await assistCreatePromotion(detail.value.vendor_id, {
    text: promoDraft.value.text.trim(),
    starts_at: starts.toISOString(),
    ends_at: new Date(starts.getTime() + promoDraft.value.days * 86400000).toISOString(),
  });
  promoDraft.value = { text: "", days: 1 };
  await openDetail(detail.value.vendor_id);
}

async function dropPromotion(id) {
  await assistCancelPromotion(detail.value.vendor_id, id);
  await openDetail(detail.value.vendor_id);
}

async function viewAs(vendor) {
  // hands the operator a time-boxed vendor-portal session. Writes made inside it
  // attribute to the admin, and the portal shows a persistent banner saying so.
  const body = await startImpersonation(vendor.vendor_id);
  setImpersonation(body);
  window.location.assign("/vendor-portal");
}

async function judgeClaim(claim, approve) {
  await decideClaim(claim.claim_id, approve);
  await load();
}

onMounted(load);
</script>

<template>
  <div>
    <section v-if="awaiting.length" class="panel">
      <h2 class="panel__title">{{ t("admin.ov.verification") }}</h2>
      <table class="table">
        <tbody>
          <tr v-for="v in awaiting" :key="v.vendor_id">
            <td class="table__name">{{ v.name }}</td>
            <td class="table__muted">
              <span v-for="d in v.documents" :key="d.kind">{{ d.kind }} ({{ d.review_status }})</span>
            </td>
            <td>
              <button class="btn btn--accent" type="button" @click="verify(v)">
                {{ t("admin.vendor.verify") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel">
      <h2 class="panel__title">{{ t("admin.nav.vendors") }}</h2>
      <p v-if="!vendors.length" class="panel__empty">{{ t("admin.vendor.empty") }}</p>
      <table v-else class="table">
        <tbody>
          <tr v-for="v in vendors" :key="v.vendor_id">
            <td class="table__name">
              {{ v.name }}
              <div class="table__muted">{{ v.metro }}</div>
            </td>
            <td>
              <span class="pill" :style="{ color: `var(${TIER_TOKEN[v.verify_status]})` }">
                {{ t(`vendor.${v.verify_status}`) }}
              </span>
            </td>
            <td class="table__figure">
              {{ v.shows_up.confirmed }}/{{ v.shows_up.published }}
            </td>
            <td class="table__figure">
              <span v-if="v.consecutive_no_shows">×{{ v.consecutive_no_shows }}</span>
            </td>
            <td>
              <button class="btn" type="button" @click="openDetail(v.vendor_id)">
                {{ t("admin.vendor.detail") }}
              </button>
              <button class="btn" type="button" @click="viewAs(v)">
                {{ t("admin.imp.view_as") }}
              </button>
              <button
                v-if="v.status === 'active'"
                class="btn btn--danger"
                type="button"
                @click="suspend(v, true)"
              >
                {{ t("admin.vendor.suspend") }}
              </button>
              <button v-else class="btn" type="button" @click="suspend(v, false)">
                {{ t("admin.vendor.reinstate") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel">
      <h2 class="panel__title">{{ t("admin.vendor.new") }}</h2>
      <p v-if="error" class="vendor__error" role="alert">{{ error }}</p>
      <div class="vendor__form">
        <input v-model="newVendor.owner_email" class="field__input" type="email" :placeholder="t('admin.vendor.owner')" />
        <input v-model="newVendor.name" class="field__input" type="text" :placeholder="t('admin.acct.name')" />
        <select v-model="newVendor.vendor_type" class="field__input">
          <option value="food_mobile">food_mobile</option>
          <option value="service_center">service_center</option>
        </select>
        <input v-model="newVendor.metro" class="field__input" type="text" :placeholder="t('admin.vendor.metro')" />
        <input v-model="newVendor.contact_phone" class="field__input" type="tel" :placeholder="t('admin.vendor.phone')" />
        <input v-model="newVendor.languages" class="field__input" type="text" :placeholder="t('admin.vendor.languages_hint')" />
        <input v-model="newVendor.halal_disclosure" class="field__input" type="text" :placeholder="t('admin.vendor.halal_hint')" />
        <button
          class="btn btn--accent"
          type="button"
          :disabled="!newVendor.owner_email || !newVendor.name"
          @click="addVendor"
        >
          {{ t("admin.vendor.new") }}
        </button>
      </div>
    </section>

    <section v-if="detail" class="panel">
      <h2 class="panel__title">{{ detail.name }}</h2>
      <ul class="stats">
        <li class="stat">
          <span class="stat__figure">{{ detail.shows_up.confirmed }}/{{ detail.shows_up.published }}</span>
          <span class="stat__label">{{ t("vendor.shows_up") }}</span>
        </li>
        <li class="stat">
          <span class="stat__figure">{{ detail.reviews.average ?? "—" }}</span>
          <span class="stat__label">{{ t("vendor.reviews") }} ({{ detail.reviews.reviewers }})</span>
        </li>
        <li class="stat">
          <span class="stat__figure">{{ detail.upheld_reports }}</span>
          <span class="stat__label">{{ t("admin.vendor.reports") }}</span>
        </li>
        <li class="stat">
          <span class="stat__figure">{{ detail.consecutive_no_shows }}</span>
          <span class="stat__label">{{ t("admin.vendor.strikes") }}</span>
        </li>
      </ul>
      <!-- whether this vendor can actually publish, said plainly — an operator
           fixing a profile by phone should know when they are done -->
      <p v-if="detail.profile_gaps.length" class="vendor__blocked">
        {{ t("admin.vendor.blocked") }}: {{ detail.profile_gaps.join(", ") }}
      </p>
      <p v-else class="vendor__ready">{{ t("admin.vendor.ready") }}</p>

      <!-- E-D5 mode (a): edit directly, attributed, no impersonation needed -->
      <p class="panel__note">{{ t("admin.vendor.edit_note") }}</p>
      <div class="vendor__form vendor__form--edit">
        <input v-model="edit.name" class="field__input" type="text" :placeholder="t('admin.acct.name')" />
        <input v-model="edit.metro" class="field__input" type="text" :placeholder="t('admin.vendor.metro')" />
        <input v-model="edit.contact_phone" class="field__input" type="tel" :placeholder="t('admin.vendor.phone')" />
        <input v-model="edit.languages" class="field__input" type="text" :placeholder="t('admin.vendor.languages_hint')" />
        <input v-model="edit.halal_disclosure" class="field__input" type="text" :placeholder="t('admin.vendor.halal_hint')" />
        <button class="btn btn--accent" type="button" @click="saveVendor">
          {{ t("admin.vendor.save") }}
        </button>
      </div>

      <table v-if="detail.appearances.length" class="table">
        <tbody>
          <tr v-for="a in detail.appearances" :key="a.appearance_id">
            <td class="table__figure">{{ a.starts_at.replace("T", " ").slice(0, 16) }}</td>
            <td class="table__muted">{{ a.status }}</td>
            <td>
              <button
                v-if="['scheduled', 'live'].includes(a.status)"
                class="link"
                type="button"
                @click="dropAppearance(a.appearance_id)"
              >
                {{ t("portal.vendor.cancel") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="vendor__form">
        <input v-model="promoDraft.text" class="field__input" type="text" maxlength="140" :placeholder="t('portal.vendor.add_promotion')" />
        <button class="btn" type="button" :disabled="!promoDraft.text" @click="addPromotion">
          {{ t("portal.vendor.add_promotion") }}
        </button>
      </div>
      <table v-if="detail.promotions.length" class="table">
        <tbody>
          <tr v-for="p in detail.promotions" :key="p.promotion_id">
            <td class="table__name">{{ p.text }}</td>
            <td class="table__muted">{{ p.status }}</td>
            <td>
              <button
                v-if="p.status === 'active'"
                class="link"
                type="button"
                @click="dropPromotion(p.promotion_id)"
              >
                {{ t("portal.vendor.cancel") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <table class="table">
        <tbody>
          <tr v-for="a in detail.audit" :key="a.created_at + a.action">
            <td class="table__figure">{{ (a.created_at || "").replace("T", " ").slice(0, 16) }}</td>
            <td class="table__name">{{ a.action }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="claims.length" class="panel">
      <h2 class="panel__title">{{ t("admin.vendor.disputes") }}</h2>
      <table class="table">
        <tbody>
          <tr v-for="c in claims" :key="c.claim_id">
            <td class="table__name">
              {{ c.claimed_name }}
              <div class="table__muted">{{ c.vendor_name }} · {{ c.status }}</div>
            </td>
            <td class="table__figure">{{ c.name_match_score }}</td>
            <td>
              <button class="btn btn--accent" type="button" @click="judgeClaim(c, true)">
                {{ t("admin.approve") }}
              </button>
              <button class="btn" type="button" @click="judgeClaim(c, false)">
                {{ t("admin.reject") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
@import "./admin-shared.css";
.vendor__form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: var(--s-3) 0;
}
.vendor__error {
  margin: 0 0 var(--s-2);
  color: var(--flare-500);
  font-size: var(--type-caption-size);
}
.vendor__blocked {
  margin: var(--s-2) 0 0;
  color: var(--marker-500);
  font-size: var(--type-caption-size);
}
.vendor__ready {
  margin: var(--s-2) 0 0;
  color: var(--ledger-500);
  font-size: var(--type-caption-size);
}
.link {
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
</style>
