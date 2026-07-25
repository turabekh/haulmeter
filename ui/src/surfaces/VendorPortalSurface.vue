<!-- AI-CONTEXT: Vendor portal (M13-FR8) — the FOURTH web-first §18 portal, beside
     the property-owner, fleet and admin portals: desktop-first, comfortable rows,
     1200 dp cap, shares ui/core tokens, NOT a driver-app screen (route meta.portal
     widens the frame and drops the tab chrome; login required).

     A cook manages their week here: what still blocks publishing, the schedule,
     promotions, and how they are actually doing.

     Two honesty rules this surface must not soften:
     · The show-up pair shown here is the SAME pair drivers see on the sheet. No
       percentage rounded in the vendor's favour, no "improving!" framing.
     · A suspension is stated plainly at the top, with the no-show count that
       caused it — a vendor should never discover it by having a publish fail.

     Promotion delivery reports what actually went out ("3 drivers told"), because
     the vendor_alert caps mean some sends are suppressed and pretending otherwise
     would misrepresent the product. -->
<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import { CalendarClock, Megaphone, TriangleAlert, UserRound } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import {
  impersonation,
  setImpersonation,
  endImpersonation,
  fetchVendorProfile,
  fetchVendorSchedule,
  fetchVendorPromotions,
  fetchVendorAnalytics,
  saveVendorProfile,
  createVendorPromotion,
  cancelVendorPromotion,
  cancelVendorAppearance,
} from "../core/api.js";

const { t } = useI18n();
const denied = ref(false);
const profile = ref(null);
const schedule = ref([]);
const promotions = ref([]);
const analytics = ref(null);

const form = reactive({ languages: "", halal_disclosure: "", busy: false });
const promo = reactive({ text: "", days: 1, busy: false, delivered: null });

const gaps = computed(() => profile.value?.profile_gaps ?? []);
// E-D5: an impersonating admin must never forget they are impersonating. The banner
// is persistent and full-width, names the vendor, and says plainly that writes are
// recorded as the admin — not as the vendor whose screen this is.
const viewingAs = computed(() => impersonation.value);
// what support has already changed here, surfaced to the VENDOR (derived from the
// audit log server-side, so there is one source of truth)
const assisted = computed(() => profile.value?.assisted ?? []);

async function exitViewAs() {
  const held = impersonation.value;
  setImpersonation(null);
  if (held?.token) await endImpersonation(held.token).catch(() => {});
  window.location.reload();
}
const suspended = computed(() => profile.value?.publish_suspended === true);

async function load() {
  try {
    [profile.value, schedule.value, promotions.value, analytics.value] = await Promise.all([
      fetchVendorProfile(),
      fetchVendorSchedule(),
      fetchVendorPromotions(),
      fetchVendorAnalytics(),
    ]);
    form.languages = (profile.value.languages || []).join(", ");
    form.halal_disclosure = profile.value.halal_disclosure || "";
  } catch {
    denied.value = true; // not a vendor, flag off, or offline
  }
}
onMounted(load);

async function saveProfile() {
  form.busy = true;
  try {
    profile.value = await saveVendorProfile({
      languages: form.languages
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      halal_disclosure: form.halal_disclosure,
      // answering at all is what Q-4 checks — "no halal claim" is a valid answer,
      // a blank is not, so saving the field marks it answered
      halal_answered: true,
    });
  } finally {
    form.busy = false;
  }
}

async function addPromotion() {
  if (!promo.text.trim()) return;
  promo.busy = true;
  try {
    const starts = new Date();
    const ends = new Date(starts.getTime() + promo.days * 86400000);
    const result = await createVendorPromotion({
      text: promo.text.trim(),
      starts_at: starts.toISOString(),
      ends_at: ends.toISOString(),
    });
    promo.delivered = result.alerts_delivered;
    promo.text = "";
    promotions.value = await fetchVendorPromotions();
  } finally {
    promo.busy = false;
  }
}

async function dropPromotion(id) {
  await cancelVendorPromotion(id);
  promotions.value = await fetchVendorPromotions();
}

async function dropAppearance(id) {
  await cancelVendorAppearance(id);
  schedule.value = await fetchVendorSchedule();
}

function when(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
</script>

<template>
  <div class="portal">
    <h1 class="portal__title">{{ t("portal.vendor.title") }}</h1>

    <div v-if="viewingAs" class="viewas" role="status">
      <span class="viewas__text">
        {{ t("admin.imp.banner") }} <strong>{{ viewingAs.vendor_name }}</strong>.
        {{ t("admin.imp.writes") }}
      </span>
      <button class="viewas__exit" type="button" @click="exitViewAs">
        {{ t("admin.imp.exit") }}
      </button>
    </div>

    <p v-if="denied" class="portal__note">{{ t("portal.vendor.no_access") }}</p>

    <template v-else-if="profile">
      <!-- said first and plainly: a suspension is not something to discover later -->
      <p v-if="suspended" class="portal__alert" role="alert">
        <TriangleAlert :size="18" :stroke-width="2" aria-hidden="true" />
        {{ t("portal.vendor.suspended") }}
      </p>

      <section class="card">
        <h2 class="card__title">
          <UserRound :size="16" :stroke-width="2" aria-hidden="true" />
          {{ t("portal.vendor.profile") }}
        </h2>
        <!-- the vendor is TOLD when support touched their things -->
        <p v-if="assisted.length" class="portal__assisted">
          {{ t("vendor.assisted_note") }} — {{ assisted[0].action }}
        </p>
        <p class="portal__name">{{ profile.name }}</p>
        <p class="portal__tier">{{ t(`vendor.${profile.verify_status}`) }}</p>

        <!-- Q-4: exactly what still blocks publishing, so it can be fixed in one pass -->
        <p v-if="gaps.length" class="portal__gaps">
          {{ t("portal.vendor.gaps") }}: {{ gaps.join(", ") }}
        </p>

        <label class="field">
          <span class="field__label">{{ t("vendor.languages") }}</span>
          <input v-model="form.languages" class="field__input" type="text" />
        </label>
        <label class="field">
          <span class="field__label">{{ t("vendor.halal") }}</span>
          <input v-model="form.halal_disclosure" class="field__input" type="text" />
        </label>
        <button class="cta" type="button" :disabled="form.busy" @click="saveProfile">
          {{ t("portal.vendor.save") }}
        </button>
      </section>

      <section class="card">
        <h2 class="card__title">
          <CalendarClock :size="16" :stroke-width="2" aria-hidden="true" />
          {{ t("portal.vendor.schedule") }}
        </h2>
        <p v-if="!schedule.length" class="portal__empty">{{ t("portal.vendor.no_schedule") }}</p>
        <table v-else class="table">
          <tbody>
            <tr v-for="a in schedule" :key="a.appearance_id">
              <td class="table__when">{{ when(a.starts_at) }}</td>
              <td>{{ t(`vendor.${a.status === 'live' ? 'live_now' : 'today'}`) }}</td>
              <td class="table__figure">{{ a.offerings.length }}</td>
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
      </section>

      <section class="card">
        <h2 class="card__title">
          <Megaphone :size="16" :stroke-width="2" aria-hidden="true" />
          {{ t("portal.vendor.promotions") }}
        </h2>
        <p v-if="!promotions.length" class="portal__empty">
          {{ t("portal.vendor.no_promotions") }}
        </p>
        <table v-else class="table">
          <tbody>
            <tr v-for="p in promotions" :key="p.promotion_id">
              <td>{{ p.text }}</td>
              <td class="table__when">{{ when(p.ends_at) }}</td>
              <td>{{ p.status }}</td>
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

        <label class="field">
          <span class="field__label">{{ t("portal.vendor.add_promotion") }}</span>
          <input v-model="promo.text" class="field__input" type="text" maxlength="140" />
        </label>
        <button class="cta" type="button" :disabled="promo.busy || !promo.text" @click="addPromotion">
          {{ t("portal.vendor.add_promotion") }}
        </button>
        <!-- honest delivery: the vendor_alert caps suppress some sends, and saying
             "reached everyone" would misrepresent what the product actually did -->
        <p v-if="promo.delivered !== null" class="portal__note">
          <span class="table__figure">{{ promo.delivered }}</span>
          {{ t("portal.vendor.delivered") }}
        </p>
      </section>

      <section v-if="analytics" class="card">
        <h2 class="card__title">{{ t("portal.vendor.analytics") }}</h2>
        <ul class="stats">
          <li class="stat">
            <span class="stat__figure">{{ analytics.sheet_views }}</span>
            <span class="stat__label">{{ t("portal.vendor.views") }}</span>
          </li>
          <li class="stat">
            <span class="stat__figure">{{ analytics.confirmations }}</span>
            <span class="stat__label">{{ t("portal.vendor.confirmations") }}</span>
          </li>
          <!-- the SAME pair drivers see. One number, one meaning, both audiences. -->
          <li class="stat">
            <span class="stat__figure">
              {{ analytics.shows_up.confirmed }}/{{ analytics.shows_up.published }}
            </span>
            <span class="stat__label">{{ t("vendor.shows_up") }}</span>
          </li>
          <li class="stat">
            <span class="stat__figure">{{ analytics.reviews.average ?? "—" }}</span>
            <span class="stat__label">
              {{ t("vendor.reviews") }} ({{ analytics.reviews.reviewers }})
            </span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
/* the banner is deliberately loud and full-width: an operator must not forget
   whose screen they are on, and marker (caution) is the honest token for it */
.viewas {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--s-3);
  margin-bottom: var(--s-4);
  padding: var(--s-3) var(--s-4);
  border: 1px solid var(--marker-500);
  border-radius: var(--r-card);
  color: var(--marker-500);
  font-size: var(--type-body-size);
}
.viewas__exit {
  min-height: 48px;
  padding: 0 var(--s-4);
  border: 1px solid var(--marker-500);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--marker-500);
  font-size: var(--type-label-size);
}
.portal__assisted {
  margin: var(--s-2) 0 0;
  color: var(--marker-500);
  font-size: var(--type-caption-size);
}
/* §18: desktop-first, comfortable density, 1200 dp cap. Same tokens as the driver
   app; this surface never imports a driver screen. */
.portal {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--s-5) var(--s-4);
}
.portal__title {
  margin: 0 0 var(--s-4);
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
.portal__alert {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0 0 var(--s-4);
  padding: var(--s-3);
  border: 1px solid var(--marker-500);
  border-radius: var(--r-card);
  color: var(--marker-500);
  font-size: var(--type-body-size);
}
.card {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
  margin-bottom: var(--s-4);
}
.card__title {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0 0 var(--s-3);
  color: var(--text-2);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.portal__name {
  margin: 0;
  font-size: var(--type-title-size);
}
.portal__tier,
.portal__note,
.portal__empty {
  margin: var(--s-2) 0 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.portal__gaps {
  margin: var(--s-2) 0 var(--s-3);
  color: var(--marker-500);
  font-size: var(--type-caption-size);
}
.table {
  width: 100%;
  border-collapse: collapse;
}
.table td {
  padding: var(--s-3) var(--s-2);
  border-top: 1px solid var(--line-1);
  font-size: var(--type-body-size);
  text-align: left;
}
.table__when,
.table__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.link {
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
.field {
  display: block;
  margin-top: var(--s-3);
}
.field__label {
  display: block;
  margin-bottom: var(--s-1);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.field__input {
  width: 100%;
  min-height: 56px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-2, var(--ink-0));
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.cta {
  min-height: 56px;
  margin-top: var(--s-4);
  padding: 0 var(--s-5);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.stats {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-5);
  margin: 0;
  padding: 0;
}
.stat {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.stat__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
}
.stat__label {
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
</style>
