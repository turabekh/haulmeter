<!-- AI-CONTEXT: Facility profile / scorecard (M2, PRD §8.2). S3 comfortable density
     (§7.4). Objective dwell figures in Mono with sample sizes ALWAYS shown
     (§11.7 / M2-FR2 — never fake precision), driver rating, moderated reviews,
     and a quick-review action. Reached from a map pin (cross-link, NAV-5).
     Fixture-backed pending auth; swaps to the live M2 API behind api.js. -->
<script setup>
import { ref, computed, onMounted } from "vue";
import { ArrowLeft, Star } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import BottomSheet from "../core/components/BottomSheet.vue";
import ReviewSheet from "../core/components/ReviewSheet.vue";
import { useI18n } from "../core/i18n.js";
import { formatDwell } from "../core/presentation.js";
import {
  fetchProfile,
  submitReview,
  fetchDetentionRisk,
  fetchAppointmentHours,
} from "../core/api.js";
import { sampleProfile, sampleFacilityIntel } from "../core/fixtures.js";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();

const profile = ref(null);
const intel = ref(null);
const reviewing = ref(false);

async function load() {
  try {
    profile.value = await fetchProfile(route.params.id);
  } catch {
    profile.value = sampleProfile(route.params.id); // unauthenticated / offline
  }
  try {
    const [risk, hours] = await Promise.all([
      fetchDetentionRisk(route.params.id),
      fetchAppointmentHours(route.params.id),
    ]);
    intel.value = { risk, best_hour: hours[0] ?? null };
  } catch {
    intel.value = sampleFacilityIntel(); // unauthenticated / offline
  }
}
onMounted(load);

// M8-FR6/FR2 presentation: percentage + a readable "06:00" hour label
const riskPct = computed(() =>
  intel.value?.risk?.exceed_rate != null ? Math.round(intel.value.risk.exceed_rate * 100) : null,
);
function hourLabel(h) {
  return `${String(h).padStart(2, "0")}:00`;
}

async function onReview(payload) {
  reviewing.value = false;
  try {
    await submitReview(route.params.id, payload.ratings, payload.text);
    await load();
  } catch {
    /* queued/offline in a later pass */
  }
}
</script>

<template>
  <div v-if="profile" class="profile">
    <header class="profile__head">
      <button class="back" type="button" :aria-label="'Back'" @click="router.back()">
        <ArrowLeft :size="24" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="profile__name">{{ profile.name }}</h1>
    </header>

    <section class="card">
      <h2 class="card__title">{{ t("profile.dock_time") }}</h2>
      <div v-if="profile.dwell.overall.sample_size > 0" class="dwell">
        <span class="dwell__figure">{{ formatDwell(profile.dwell.overall.median_seconds) }}</span>
        <span class="dwell__meta">
          {{ t("profile.median") }} · {{ profile.dwell.overall.sample_size }} {{ t("profile.stops") }}
        </span>
      </div>
      <p v-else class="muted">{{ t("profile.no_dwell") }}</p>
    </section>

    <!-- M8 decision intel: detention-risk pre-acceptance flag + fastest hour -->
    <section v-if="intel" class="card">
      <h2 class="card__title">{{ t("profile.risk") }}</h2>
      <p v-if="riskPct !== null" class="risk">
        <span class="risk__figure" :class="{ hot: riskPct >= 40 }">{{ riskPct }}%</span>
        <span class="dwell__meta">· {{ intel.risk.sample_size }} {{ t("profile.stops_basis") }}</span>
      </p>
      <p v-else class="muted">{{ t("profile.risk_none") }}</p>
      <p v-if="intel.best_hour" class="best-hour">
        <span class="best-hour__label">{{ t("profile.best_hour") }}</span>
        <span class="best-hour__figure">{{ hourLabel(intel.best_hour.hour) }}</span>
        <span class="dwell__meta">
          · {{ formatDwell(intel.best_hour.median_seconds) }} · {{ intel.best_hour.sample_size }}
          {{ t("profile.stops_basis") }}
        </span>
      </p>
    </section>

    <section class="card">
      <h2 class="card__title">{{ t("profile.rating") }}</h2>
      <div class="rating">
        <Star :size="20" :stroke-width="2" class="rating__star" aria-hidden="true" />
        <span class="rating__figure">{{ profile.ratings.overall ?? "—" }}</span>
        <span class="dwell__meta">· {{ profile.ratings.review_count }} {{ t("profile.reviews") }}</span>
      </div>
    </section>

    <section class="card">
      <h2 class="card__title">{{ t("profile.reviews") }}</h2>
      <ul v-if="profile.reviews.length" class="reviews">
        <li v-for="r in profile.reviews" :key="r.id" class="reviews__item">{{ r.text }}</li>
      </ul>
      <p v-else class="muted">{{ t("profile.no_reviews") }}</p>
    </section>

    <button class="add-review" type="button" @click="reviewing = true">
      {{ t("profile.add_review") }}
    </button>

    <BottomSheet :open="reviewing" :title="t('profile.add_review')" @close="reviewing = false">
      <ReviewSheet @submit="onReview" />
    </BottomSheet>
  </div>
</template>

<style scoped>
.profile {
  padding: var(--s-4);
}
.profile__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-bottom: var(--s-4);
}
.back {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-1);
}
.profile__name {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.card {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
  margin-bottom: var(--s-3);
}
.card__title {
  margin: 0 0 var(--s-2);
  font-size: var(--type-label-size);
  color: var(--text-2);
  font-weight: 500;
}
.dwell {
  display: flex;
  align-items: baseline;
  gap: var(--s-3);
}
.dwell__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-display-size);
}
.dwell__meta {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.rating {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}
.rating__star {
  color: var(--marker-500);
}
.rating__figure {
  font-family: var(--font-mono);
  font-size: var(--type-title-size);
}
.risk {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  margin: 0;
}
.risk__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-display-size);
  color: var(--text-1);
}
.risk__figure.hot {
  color: var(--flare-500);
}
.best-hour {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  margin: var(--s-3) 0 0;
}
.best-hour__label {
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.best-hour__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
}
.reviews {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.reviews__item {
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.muted {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.add-review {
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-2);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
</style>
