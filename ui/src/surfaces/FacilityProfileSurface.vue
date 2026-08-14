<!-- AI-CONTEXT: Facility profile / scorecard (M2, PRD §8.2). S3 comfortable density
     (§7.4). Objective dwell figures in Mono with sample sizes ALWAYS shown
     (§11.7 / M2-FR2 — never fake precision), driver rating, moderated reviews,
     and a quick-review action. Reached from a map pin (cross-link, NAV-5).
     Fixture-backed pending auth; swaps to the live M2 API behind api.js. -->
<script setup>
import { ref, computed, onMounted } from "vue";
import { ArrowLeft, Star, Clock } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import BottomSheet from "../core/components/BottomSheet.vue";
import ReviewSheet from "../core/components/ReviewSheet.vue";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { formatDwell } from "../core/presentation.js";
import {
  fetchProfile,
  submitReview,
  fetchDetentionRisk,
  fetchAppointmentHours,
  fetchQuestions,
  fetchServiceCenter,
  askQuestion,
  pendingByPath,
  fetchPromptPref,
  mutePrompts,
  unmutePrompts,
} from "../core/api.js";
import { verificationPresentation } from "../core/vendors.js";
import SkeletonCard from "../core/components/SkeletonCard.vue";
import { LoadState, Failure, failureOf } from "../core/load-state.js";
import Spinner from "../core/components/Spinner.vue";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const { isDriving } = useDriverState();

const profile = ref(null);
const intel = ref(null);
const questions = ref([]);
const serviceCenter = ref(null);
const reviewing = ref(false);
const asking = ref(false);
const questionText = ref("");
const profileState = ref(LoadState.LOADING);
const profileFailure = ref(null);
const intelState = ref(LoadState.LOADING);
const intelFailure = ref(null);
const questionsState = ref(LoadState.LOADING);
const questionsFailure = ref(null);

// AI-CONTEXT: §23 entry 131 — THREE fetches, THREE states, which is what the kickoff
// called for on this surface. They fail independently: the dock-time card can be real
// while the Q&A is unreachable, and one state for all three would have hidden a
// perfectly good profile because the community endpoint was down.
async function loadQuestions() {
  try {
    questions.value = await fetchQuestions(route.params.id);
    questionsState.value = LoadState.LOADED;
    questionsFailure.value = null;
  } catch (e) {
    questions.value = [];
    questionsFailure.value = failureOf(e);
    questionsState.value = LoadState.FAILED;
  }
}

async function load() {
  try {
    profile.value = await fetchProfile(route.params.id);
    profileState.value = LoadState.LOADED;
    profileFailure.value = null;
  } catch (e) {
    // this invented a facility — its name, its dock-time median and its sample size —
    // for whatever id was in the URL. A driver reads that median to decide whether to
    // accept the load.
    profile.value = null;
    profileFailure.value = failureOf(e);
    profileState.value = LoadState.FAILED;
  }
  try {
    const [risk, hours] = await Promise.all([
      fetchDetentionRisk(route.params.id),
      fetchAppointmentHours(route.params.id),
    ]);
    intel.value = { risk, best_hour: hours[0] ?? null };
    intelState.value = LoadState.LOADED;
    intelFailure.value = null;
  } catch (e) {
    intel.value = null;
    intelFailure.value = failureOf(e);
    intelState.value = LoadState.FAILED;
  }
  // M13-FR7: an UNCLAIMED facility returns null and stays a plain POI. Claiming
  // adds contact detail and curated services; it never changes what the facility
  // fundamentally is, so this is one more card and never a different screen.
  serviceCenter.value = await fetchServiceCenter(route.params.id).catch(() => null);
  await loadQuestions();
  await loadPromptPref();
}
onMounted(load);

// AI-CONTEXT: "don't ask about this lot" — §13.1's per-subject mute, which F8 has had
// since the vendor class shipped and no surface used (§23 entry 114, owner-chose here).
//
// It lives on the facility because this is the screen the prompt deep-links to, and
// because mute and un-mute are then the SAME control in the same place: a mute a driver
// cannot see is a mute they cannot undo. Without it the only escape from one unwanted
// prompt was the whole class — and that switch sits on the notification permission
// carrying the detention P0, which is one-shot (§23 entry 111).
const promptsMuted = ref(null); // null = unknown; the row renders nothing rather than a guess
const muteBusy = ref(false);

async function loadPromptPref() {
  try {
    promptsMuted.value = (await fetchPromptPref(route.params.id)).muted;
  } catch {
    promptsMuted.value = null; // unauthenticated / offline — say nothing
  }
}

async function toggleMute() {
  muteBusy.value = true;
  const next = !promptsMuted.value;
  try {
    await (next ? mutePrompts(route.params.id) : unmutePrompts(route.params.id));
    promptsMuted.value = next;
  } catch {
    /* queuedPost already stored it for replay; leave the row alone rather than claim
       a state that has not landed (§11.7) */
  } finally {
    muteBusy.value = false;
  }
}

async function onAsk() {
  const text = questionText.value.trim();
  asking.value = false;
  questionText.value = "";
  if (!text) return;
  try {
    await askQuestion(route.params.id, text);
    await loadQuestions();
  } catch {
    /* queued/offline in a later pass (F12) */
  }
}

// C-1: only `verified` earns the positive token. `documents_on_file` is a
// statement about paperwork, not an endorsement, and renders neutral here exactly
// as it does on the food sheet.
const claimTier = computed(() =>
  serviceCenter.value ? verificationPresentation(serviceCenter.value.verify_status) : null,
);

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
    /* the queued row below is what says so now (§23 entry 151) */
  }
}

/* AI-CONTEXT: §15.1's pending glyph on the two things a driver TYPES here, and entry 150's
 * lesson applied rather than repeated.
 *
 * Both writes queue safely; neither appeared anywhere. `onAsk` clears the input, closes the
 * sheet and re-reads the SERVER — offline the question is not there, and the read that
 * would have shown it fails too, so a driver who has just written a question is looking at
 * "No connection. This loads when you have signal." The text exists in exactly one place
 * on earth at that moment, and the app was the thing not admitting it.
 *
 * FILTERED BY FACILITY, which a path check alone cannot do: `/community/questions` carries
 * its facility in the BODY, so every facility page would otherwise show a question written
 * about a lot 600 miles away — on the screen a driver is using to decide whether to pull in
 * HERE. The review path carries the id in the URL instead, so the two are matched
 * differently on purpose.
 *
 * Both render OUTSIDE their section's load-state chain (entry 150): offline is exactly when
 * that chain is in its failed branch and exactly when the queued item exists. The COLD case
 * — offline on a facility never opened, where `apiGet` has no cache to serve — is
 * deliberately not covered: there is no facility on the screen to attach anything to. */
const pendingQuestions = computed(() =>
  pendingByPath("/community/questions")
    .filter((i) => i.body.facility_id === route.params.id && i.body.text)
    .map((i) => ({ opId: i.opId, text: i.body.text })),
);
const pendingReviews = computed(() =>
  pendingByPath(`/facility/${route.params.id}/review`)
    .filter((i) => i.body.text)
    .map((i) => ({ opId: i.opId, text: i.body.text })),
);
</script>

<template>
  <!-- the whole screen is one facility, so its loading and failed states are the
       screen's, not a card's (§15.4) -->
  <div v-if="profileState === LoadState.LOADING" class="profile">
    <SkeletonCard :count="3" />
  </div>
  <div v-else-if="profileState === LoadState.FAILED" class="profile">
    <p class="profile__failed">
      {{ profileFailure === Failure.OFFLINE ? t("system.load_offline") : t("facility.load_failed") }}
      <button class="profile__retry" type="button" @click="load">{{ t("system.retry") }}</button>
    </p>
  </div>
  <div v-else-if="profile" class="profile">
    <header class="profile__head">
      <button class="back" type="button" :aria-label="'Back'" @click="router.back()">
        <ArrowLeft :size="24" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="profile__name">{{ profile.name }}</h1>
    </header>

    <!-- M13-FR7: only a CLAIMED service centre renders this. The business's own
         name and rung are stated together, so a driver reading the hours knows
         who is telling them and how far that has been checked (§11.7). -->
    <section v-if="serviceCenter" class="card">
      <h2 class="card__title">{{ t("profile.service_center") }}</h2>
      <p class="sc__who">
        {{ serviceCenter.vendor_name }}
        <span class="sc__tier" :style="{ color: `var(${claimTier.token})` }">
          {{ t(claimTier.labelKey) }}
        </span>
      </p>
      <p v-if="serviceCenter.services.length" class="sc__services">
        {{ serviceCenter.services.map((s) => t(`facility.service.${s}`)).join(" · ") }}
      </p>
      <p v-if="serviceCenter.hours" class="sc__line">
        {{ t("profile.sc_hours") }}: {{ serviceCenter.hours }}
      </p>
      <p v-if="serviceCenter.phone" class="sc__line">
        {{ t("profile.sc_phone") }}: <span class="sc__phone">{{ serviceCenter.phone }}</span>
      </p>
      <!-- who said it, said once, at the bottom: hours and phone are the
           business's own words, not something the platform verified -->
      <p class="sc__source">{{ t("profile.sc_source") }}</p>
    </section>

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
    <!-- the intel card is a SECOND fetch and says so when it is the one that failed —
         a driver who can see the dock time must not be told the whole place is
         unavailable because the risk model was unreachable -->
    <section v-if="intelState === LoadState.FAILED" class="card">
      <h2 class="card__title">{{ t("profile.risk") }}</h2>
      <p class="profile__failed">
        {{ intelFailure === Failure.OFFLINE ? t("system.load_offline") : t("facility.intel_failed") }}
      </p>
    </section>
    <section v-else-if="intel" class="card">
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
      <!-- §15.1: the driver's own, waiting. Above the landed ones because it is the one
           they just wrote, and outside the `v-else` so an empty list still shows it. -->
      <ul v-if="pendingReviews.length" class="reviews">
        <li v-for="r in pendingReviews" :key="r.opId" class="reviews__item reviews__item--pending">
          {{ r.text }}
          <span class="queued__glyph" :title="t('docs.cap_queued')">
            <Clock :size="14" :stroke-width="2" aria-hidden="true" />
          </span>
        </li>
      </ul>
      <ul v-if="profile.reviews.length" class="reviews">
        <li v-for="r in profile.reviews" :key="r.id" class="reviews__item">{{ r.text }}</li>
      </ul>
      <p v-else-if="!pendingReviews.length" class="muted">{{ t("profile.no_reviews") }}</p>
    </section>

    <!-- M10-FR4: moderated driver Q&A pinned to the facility page -->
    <section class="card">
      <h2 class="card__title">{{ t("qa.title") }}</h2>
      <!-- AI-CONTEXT: OUTSIDE the three-state chain below, which is the whole lesson of
           entry 150. Inside it, a queued question would render in every case except the
           one it exists for: offline `fetchQuestions` fails, §15.4's line takes the
           section, and the question the driver just typed — the only copy of that text
           anywhere — would vanish with it. -->
      <ul v-if="pendingQuestions.length" class="qa">
        <li v-for="q in pendingQuestions" :key="q.opId" class="qa__item qa__item--pending">
          <p class="qa__q">
            {{ q.text }}
            <span class="queued__glyph" :title="t('docs.cap_queued')">
              <Clock :size="14" :stroke-width="2" aria-hidden="true" />
            </span>
          </p>
        </li>
      </ul>
      <p v-if="questionsState === LoadState.FAILED" class="profile__failed">
        {{ questionsFailure === Failure.OFFLINE ? t("system.load_offline") : t("facility.questions_failed") }}
      </p>
      <ul v-else-if="questions.length" class="qa">
        <li v-for="q in questions" :key="q.question_id" class="qa__item">
          <p class="qa__q">{{ q.text }}</p>
          <p v-for="(a, i) in q.answers" :key="i" class="qa__a">
            {{ a.text }}
            <span v-if="a.presence_proven" class="qa__badge">{{ t("qa.onsite") }}</span>
          </p>
        </li>
      </ul>
      <p v-else-if="questionsState === LoadState.LOADED && !pendingQuestions.length"
         class="muted">{{ t("qa.empty") }}</p>
      <!-- SM-3: the intel stays readable at speed — that is the point of it — but
           writing a question or a review is composition, and Forbidden #11 rules out
           interactive prompts in motion. -->
      <button v-if="!isDriving" class="cta cta--ghost" type="button" @click="asking = true">
        {{ t("qa.ask") }}
      </button>
    </section>

    <!-- The prompt's own off switch, at the lot it is about. Muting is not composition
         and could survive at speed, but it is still an interactive control on a screen
         that withdraws while DRIVING, so it follows the same gate as everything else
         here rather than being the one exception a driver has to discover. -->
    <!-- `prompt-mute` exists for the §22.3 harness to aim at: a state it cannot select
         is a state that ships unmeasured, and this row only renders once the server has
         answered — so the harness needs a selector to wait for. -->
    <section v-if="!isDriving && promptsMuted !== null" class="card prompt-mute">
      <h2 class="card__title">{{ t("prompts.lot_title") }}</h2>
      <p class="muted">
        {{ promptsMuted ? t("prompts.lot_muted") : t("prompts.lot_elsewhere") }}
      </p>
      <button class="cta cta--ghost" type="button" :disabled="muteBusy" @click="toggleMute">
        <Spinner v-if="muteBusy" />
        {{ muteBusy
          ? t("busy.saving")
          : promptsMuted ? t("prompts.lot_unmute") : t("prompts.lot_mute") }}
      </button>
    </section>

    <button v-if="!isDriving" class="add-review" type="button" @click="reviewing = true">
      {{ t("profile.add_review") }}
    </button>
    <p v-else class="driving-note">{{ t("driving.paused") }}</p>

    <BottomSheet :open="reviewing && !isDriving" :title="t('profile.add_review')" @close="reviewing = false">
      <ReviewSheet @submit="onReview" />
    </BottomSheet>

    <BottomSheet :open="asking && !isDriving" :title="t('qa.ask')" @close="asking = false">
      <div class="ask">
        <textarea
          v-model="questionText"
          class="ask__input"
          :placeholder="t('qa.placeholder')"
          rows="3"
        ></textarea>
        <button class="cta" type="button" :disabled="asking" @click="onAsk">
          <Spinner v-if="asking" />
          {{ asking ? t("busy.sending") : t("qa.submit") }}
        </button>
      </div>
    </BottomSheet>
  </div>
</template>

<style scoped>
.profile {
  padding: var(--s-4);
}
.profile__failed {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.profile__retry {
  min-height: 48px;
  padding: 0 var(--s-2);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
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
/* §15.1's queued contribution, wearing the same treatment as the landed ones — the glyph
   is the whole difference, and `--text-3` on a dashed left rule is the calm the status
   strip already sets ("Offline — everything saves to your phone"). Same Clock the wallet
   and the condition sheet use (§22.2: compose, never invent). */
.reviews__item--pending,
.qa__item--pending {
  padding-left: var(--s-3);
  border-left: 1px dashed var(--line-1);
}
.queued__glyph {
  display: inline-flex;
  vertical-align: middle;
  margin-left: var(--s-2);
  color: var(--text-3);
}
.muted {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.sc__who {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: 0;
  font-size: var(--type-body-size);
  font-weight: 500;
}
.sc__tier {
  font-size: var(--type-caption-size);
  font-weight: 400;
}
.sc__services {
  margin: var(--s-2) 0 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.sc__line {
  margin: var(--s-2) 0 0;
  font-size: var(--type-body-size);
}
.sc__phone {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.sc__source {
  margin: var(--s-3) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
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
.qa {
  list-style: none;
  margin: 0 0 var(--s-3);
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.qa__q {
  margin: 0;
  font-size: var(--type-body-size);
  font-weight: 500;
  color: var(--text-1);
}
.qa__a {
  margin: var(--s-1) 0 0;
  font-size: var(--type-body-size);
  color: var(--text-2);
}
.qa__badge {
  margin-left: var(--s-2);
  padding: 1px var(--s-2);
  border-radius: var(--r-pill);
  background: var(--ledger-500);
  color: var(--on-accent);
  font-size: var(--type-caption-size);
}
.cta {
  width: 100%;
  min-height: 56px;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta--ghost {
  min-height: 48px;
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
}
.ask {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.ask__input {
  width: 100%;
  padding: var(--s-3);
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
  font-family: inherit;
  resize: vertical;
}
</style>
