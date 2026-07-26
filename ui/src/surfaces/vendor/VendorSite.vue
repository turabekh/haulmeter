<!-- AI-CONTEXT: M13-FR7 — a service centre claims its own site (design-prd §18).

     Four things this screen is careful about, each of them a way the flow can
     quietly lie to the person using it:

     · **Never a UUID.** Every other facility lookup in the product is geographic;
       a claimant sits at a desk with a business name. They search by name and
       recognise their site by its name and address, never by an id.
     · **A dispute is disclosed BEFORE the form, not after.** A rival claim on a
       claimed site becomes a dispute an operator decides (never a silent loss), so
       the search row says so up front.
     · **The name check compares the VENDOR's business name to the site on file**,
       which is why the field is prefilled from the profile and not from the
       facility — prefilling it from the facility would score 1.00 every time and
       make the check theatre. A mismatch names the site we hold rather than
       printing a similarity score, which means nothing to a cook.
     · **Curation ADDS.** Services ingestion already knows render checked and
       disabled, because a claim edit cannot erase an ingested fact (E3.2) — the
       union is the screen, not a footnote. -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { Building2, Search, Upload } from "lucide-vue-next";
import { useI18n } from "../../core/i18n.js";
import {
  curateFacilityClaim,
  fetchClaimableFacilities,
  fetchVendorClaims,
  fetchVendorProfile,
  submitFacilityClaim,
} from "../../core/api.js";

const { t } = useI18n();

const profile = ref(null);
const claims = ref([]);
const serviceKinds = ref([]);
const loaded = ref(false);

const q = ref("");
const results = ref(null);
const searching = ref(false);
const picked = ref(null);
const claimedName = ref("");
const file = ref(null);
const submitting = ref(false);
const mismatch = ref(false);
const error = ref(null);
// per-claim curation drafts, keyed by claim id
const drafts = ref({});

// a food vendor has no site to claim. The rail hides this section for them; anyone
// arriving by URL is told plainly rather than shown a search that returns 403.
const eligible = computed(() => profile.value?.vendor_type === "service_center");

async function load() {
  const body = await fetchVendorClaims().catch(() => null);
  claims.value = body?.claims ?? [];
  serviceKinds.value = body?.service_kinds ?? [];
  // drafts are seeded HERE rather than lazily from the template: creating them
  // during render would mutate state mid-render for no gain
  for (const c of claims.value) {
    if (c.status !== "approved") continue;
    drafts.value[c.claim_id] = {
      hours: c.hours ?? "",
      phone: c.phone ?? "",
      adding: [],
      saving: false,
      saved: drafts.value[c.claim_id]?.saved ?? false,
    };
  }
  loaded.value = true;
}

onMounted(async () => {
  profile.value = await fetchVendorProfile().catch(() => null);
  claimedName.value = profile.value?.name ?? "";
  if (profile.value?.vendor_type === "service_center") await load();
  else loaded.value = true;
});

async function search() {
  if (q.value.trim().length < 2) return;
  searching.value = true;
  error.value = null;
  try {
    results.value = await fetchClaimableFacilities(q.value.trim());
  } catch {
    results.value = [];
    error.value = t("vendor.site.search_error");
  } finally {
    searching.value = false;
  }
}

function pick(row) {
  picked.value = row;
  mismatch.value = false;
  error.value = null;
  if (!claimedName.value) claimedName.value = profile.value?.name ?? "";
}

function onFile(event) {
  file.value = event.target.files?.[0] ?? null;
}

function readBase64(f) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(f);
  });
}

async function submit() {
  if (!picked.value || !claimedName.value.trim()) return;
  submitting.value = true;
  mismatch.value = false;
  error.value = null;
  try {
    const body = { facility_id: picked.value.facility_id, claimed_name: claimedName.value.trim() };
    if (file.value) {
      body.content_b64 = await readBase64(file.value);
      body.filename = file.value.name;
    }
    await submitFacilityClaim(body);
    picked.value = null;
    results.value = null;
    q.value = "";
    file.value = null;
    await load();
  } catch (e) {
    // the score is deliberately not rendered: "0.42" tells a business owner
    // nothing. The site's own name does.
    if (e?.detail?.error === "name_mismatch") mismatch.value = true;
    else error.value = t("vendor.site.submit_error");
  } finally {
    submitting.value = false;
  }
}

function toggleService(claim, kind) {
  const d = drafts.value[claim.claim_id];
  if (!d) return;
  const at = d.adding.indexOf(kind);
  if (at >= 0) d.adding.splice(at, 1);
  else d.adding.push(kind);
}

async function saveCuration(claim) {
  const d = drafts.value[claim.claim_id];
  if (!d) return;
  d.saving = true;
  d.saved = false;
  try {
    await curateFacilityClaim(claim.claim_id, {
      services_added: d.adding.length ? d.adding : null,
      hours: d.hours.trim() || null,
      phone: d.phone.trim() || null,
    });
    d.adding = [];
    d.saved = true;
    await load();
  } catch {
    error.value = t("vendor.site.save_error");
  } finally {
    d.saving = false;
  }
}
</script>

<template>
  <div class="site">
    <h2 class="site__title">{{ t("vendor.nav.site") }}</h2>

    <p v-if="loaded && !eligible" class="site__note">{{ t("vendor.site.food_vendor") }}</p>

    <template v-else-if="loaded">
      <!-- what is already claimed, and what state each claim is in -->
      <section v-for="c in claims" :key="c.claim_id" class="card">
        <h3 class="card__site">
          <Building2 :size="18" :stroke-width="2" aria-hidden="true" />
          {{ c.facility_name }}
        </h3>
        <p v-if="c.facility_address" class="card__where">{{ c.facility_address }}</p>

        <p class="state" :class="`state--${c.status}`">{{ t(`vendor.site.status.${c.status}`) }}</p>
        <p class="state__means">{{ t(`vendor.site.means.${c.status}`) }}</p>

        <template v-if="c.status === 'approved' && drafts[c.claim_id]">
          <p class="union">{{ t("vendor.site.union_note") }}</p>
          <ul class="services">
            <li v-for="s in serviceKinds" :key="s" class="service">
              <label class="service__label">
                <input
                  type="checkbox"
                  :checked="c.services.includes(s) || drafts[c.claim_id].adding.includes(s)"
                  :disabled="c.services.includes(s)"
                  @change="toggleService(c, s)"
                />
                <span>{{ t(`facility.service.${s}`) }}</span>
              </label>
              <!-- each locked tick says WHOSE fact it is, so a claimant knows why
                   it cannot be unticked: ours came from ingestion, theirs from a
                   previous save. Neither can be taken back here (E3.2). -->
              <span v-if="c.services_ingested.includes(s)" class="service__from">
                {{ t("vendor.site.from_records") }}
              </span>
              <span v-else-if="c.services_added.includes(s)" class="service__from">
                {{ t("vendor.site.from_you") }}
              </span>
            </li>
          </ul>

          <label class="field">
            <span class="field__label">{{ t("vendor.site.hours") }}</span>
            <input v-model="drafts[c.claim_id].hours" class="field__input" type="text" />
          </label>
          <label class="field">
            <span class="field__label">{{ t("vendor.site.phone") }}</span>
            <input v-model="drafts[c.claim_id].phone" class="field__input" type="tel" />
          </label>
          <button
            class="cta"
            type="button"
            :disabled="drafts[c.claim_id].saving"
            @click="saveCuration(c)"
          >
            {{ t("portal.vendor.save") }}
          </button>
          <p v-if="drafts[c.claim_id].saved" class="saved" role="status">
            {{ t("vendor.site.saved") }}
          </p>
        </template>
      </section>

      <!-- and the way to claim another one. A service business may hold several -->
      <section class="card">
        <h3 class="card__title">{{ t("vendor.site.find") }}</h3>
        <p class="field__hint">{{ t("vendor.site.find_note") }}</p>
        <div class="search">
          <input
            v-model="q"
            class="field__input"
            type="search"
            :placeholder="t('vendor.site.search_placeholder')"
            @keyup.enter="search"
          />
          <button class="cta cta--ghost" type="button" :disabled="searching" @click="search">
            <Search :size="18" :stroke-width="2" aria-hidden="true" />
            {{ t("vendor.site.search") }}
          </button>
        </div>

        <p v-if="results && !results.length" class="card__empty">{{ t("vendor.site.no_results") }}</p>
        <ul v-else-if="results" class="hits">
          <li v-for="r in results" :key="r.facility_id" class="hit">
            <button class="hit__pick" type="button" @click="pick(r)">
              <span class="hit__name">{{ r.name }}</span>
              <span v-if="r.address" class="hit__where">{{ r.address }}</span>
              <span class="hit__services">
                {{ r.services.map((s) => t(`facility.service.${s}`)).join(" · ") }}
              </span>
            </button>
            <!-- said BEFORE the form: a second claim is a dispute an operator
                 decides, and a claimant is entitled to know that in advance -->
            <p v-if="r.claimed_by_me" class="hit__flag">{{ t("vendor.site.yours") }}</p>
            <p v-else-if="r.already_claimed" class="hit__flag">{{ t("vendor.site.taken") }}</p>
          </li>
        </ul>

        <template v-if="picked">
          <h3 class="card__title card__title--step">{{ t("vendor.site.claim_step") }}</h3>
          <p class="picked">{{ picked.name }}</p>
          <label class="field">
            <span class="field__label">{{ t("vendor.site.business_name") }}</span>
            <input v-model="claimedName" class="field__input" type="text" />
            <span class="field__hint">{{ t("vendor.site.business_name_note") }}</span>
          </label>

          <div v-if="mismatch" class="mismatch" role="alert">
            <p class="mismatch__lead">{{ t("vendor.site.mismatch") }}</p>
            <p class="mismatch__name">{{ picked.name }}</p>
            <p class="mismatch__next">{{ t("vendor.site.mismatch_next") }}</p>
          </div>

          <label class="field">
            <span class="field__label">{{ t("vendor.site.proof") }}</span>
            <input class="field__input" type="file" @change="onFile" />
            <!-- optional, and honest about what that costs: an operator with no
                 document has only the name to go on -->
            <span class="field__hint">{{ t("vendor.site.proof_note") }}</span>
          </label>

          <button class="cta" type="button" :disabled="submitting" @click="submit">
            <Upload :size="18" :stroke-width="2" aria-hidden="true" />
            {{ t("vendor.site.submit") }}
          </button>
        </template>

        <p v-if="error" class="error" role="alert">{{ error }}</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.site__title {
  margin: 0 0 var(--s-4);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.site__note {
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.card {
  margin-bottom: var(--s-4);
  padding: var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.card__title {
  margin: 0 0 var(--s-3);
  color: var(--text-2);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.card__title--step {
  margin-top: var(--s-4);
}
.card__site {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0;
  font-size: var(--type-body-size);
  font-weight: 500;
}
.card__where {
  margin: var(--s-1) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.card__empty {
  margin: var(--s-3) 0 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.state {
  margin: var(--s-3) 0 0;
  font-size: var(--type-body-size);
  font-weight: 500;
  color: var(--text-2);
}
/* only an approved claim earns the positive token. Pending is not a small
   approval, and a dispute is not a failure — each says exactly what it is. */
.state--approved {
  color: var(--ledger-500);
}
.state--disputed {
  color: var(--marker-500);
}
.state--rejected {
  color: var(--flare-500);
}
.state__means {
  margin: var(--s-1) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.union {
  margin: var(--s-4) 0 var(--s-2);
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.services {
  list-style: none;
  margin: 0 0 var(--s-3);
  padding: 0;
}
.service {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 44px;
}
.service__label {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--type-body-size);
}
.service__from {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.search {
  display: flex;
  gap: var(--s-2);
  margin-bottom: var(--s-3);
}
.hits {
  list-style: none;
  margin: 0;
  padding: 0;
}
.hit {
  border-bottom: 1px solid var(--line-1);
  padding: var(--s-2) 0;
}
.hit__pick {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  width: 100%;
  min-height: 48px;
  text-align: left;
  color: var(--text-1);
}
.hit__name {
  font-size: var(--type-body-size);
  font-weight: 500;
}
.hit__where,
.hit__services {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.hit__flag {
  margin: var(--s-1) 0 0;
  color: var(--marker-500);
  font-size: var(--type-caption-size);
}
.picked {
  margin: 0 0 var(--s-3);
  font-size: var(--type-body-size);
  font-weight: 500;
}
.field {
  display: block;
  margin-bottom: var(--s-3);
}
.field__label {
  display: block;
  margin-bottom: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.field__input {
  width: 100%;
  min-height: 48px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.field__hint {
  display: block;
  margin-top: var(--s-2);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.mismatch {
  margin-bottom: var(--s-3);
  padding: var(--s-3);
  border: 1px solid var(--marker-500);
  border-radius: var(--r-control);
}
.mismatch__lead,
.mismatch__next {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.mismatch__name {
  margin: var(--s-2) 0;
  font-size: var(--type-body-size);
  font-weight: 500;
}
.cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  min-height: 48px;
  padding: 0 var(--s-4);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta--ghost {
  flex: 0 0 auto;
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
}
.cta:disabled {
  opacity: 0.5;
}
.saved {
  margin: var(--s-2) 0 0;
  color: var(--ledger-500);
  font-size: var(--type-caption-size);
}
.error {
  margin: var(--s-3) 0 0;
  color: var(--flare-500);
  font-size: var(--type-body-size);
}
</style>
