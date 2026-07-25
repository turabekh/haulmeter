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

async function openDetail(vendorId) {
  detail.value = await fetchVendorDetail(vendorId).catch(() => null);
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
      <p v-if="detail.profile_gaps.length" class="panel__note">
        {{ t("portal.vendor.gaps") }}: {{ detail.profile_gaps.join(", ") }}
      </p>
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
</style>
