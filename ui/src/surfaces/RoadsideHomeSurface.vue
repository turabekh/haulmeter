<!-- AI-CONTEXT: the Roadside tab root (decision 207). This REPLACED `RoadsideSurface.vue`.

     WHY A HOME AND NOT THE OLD HUB. The old front door offered one button and a drill
     link, which is the right shape for a More row and the wrong shape for a tab. E3.1.1
     describes a PROGRAM with a beginning and an end — check → diagnostic → drill plan →
     reassessment → record — and a tab root that shows only "start" tells a returning
     driver nothing about the program they are already in. The four sections here are that
     arc, in the order a driver meets it.

     THE BAND IS CARRIED, NOT RECOMPUTED. `provisional` comes off the session row (Q-8),
     so this screen can never disagree with the result screen about the same stop.

     WHAT THE PROGRESS STRIP DOES NOT SAY. FR6's prose names "heard / understood /
     answered". `skill_state` has `exposure_count` and `success_count` and nothing
     between them, so the third state has no column and is not drawn. Inventing it would
     put a distinction on screen that no data supports — see `domain/progress.py`.

     A GUEST SEES THIS WHOLE SCREEN. Both reads answer an anonymous caller (FR1: auth is
     never in front of the free check), so the empty state IS the acquisition state and
     draws the CTA rather than a sign-in wall.

     DRIVING: `withdraws` — every action here leads to talking out loud, which Q-4 makes
     the engine refuse anyway; withdrawing is how the refusal arrives as a designed state. -->
<script setup>
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Mic, GraduationCap, History } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import {
  fetchRoadsideScenarios,
  fetchRoadsideProgress,
  fetchRoadsideSessions,
} from "../core/api.js";
import { LoadState, Failure, failureOf } from "../core/load-state.js";
import SkeletonCard from "../core/components/SkeletonCard.vue";

const { t, locale } = useI18n();
const router = useRouter();
const { isDriving } = useDriverState();

const state = ref(LoadState.LOADING);
const failure = ref(null);
const scenarios = ref([]);
const progress = ref(null);
const sessions = ref([]);

// AI-CONTEXT: ONE FAILED READ DOES NOT BLANK THE TAB. The three reads are independent
// questions — what can I start, where do I stand, what have I done — and a driver whose
// history times out can still start a check. `allSettled` keeps the sections that
// answered; the screen only fails whole when the one thing it exists to offer is gone.
async function load() {
  state.value = LoadState.LOADING;
  failure.value = null;
  const [cat, prog, hist] = await Promise.allSettled([
    fetchRoadsideScenarios(),
    fetchRoadsideProgress(),
    fetchRoadsideSessions(),
  ]);
  if (cat.status === "rejected") {
    failure.value = failureOf(cat.reason);
    state.value = LoadState.FAILED;
    return;
  }
  scenarios.value = cat.value?.scenarios || [];
  progress.value = prog.status === "fulfilled" ? prog.value : null;
  sessions.value = hist.status === "fulfilled" ? hist.value?.sessions || [] : [];
  state.value = LoadState.LOADED;
}

onMounted(load);

const bandKey = computed(() => {
  const band = progress.value?.band;
  if (!band) return null;
  return `roadside.band.${band}${progress.value.provisional ? "_provisional" : ""}`;
});

const skills = computed(() => progress.value?.skills || { seen: 0, passed: 0, due: 0 });
const drill = computed(() => progress.value?.drill || { day: null, due: 0, completed: false });
const canStart = computed(() => scenarios.value.length > 0 && !isDriving.value);

function start() {
  router.push({ name: "roadside-consent", params: { scenarioId: scenarios.value[0].id } });
}

function openStop(id) {
  router.push({ name: "roadside-result", params: { sessionId: id } });
}

// `started_at` is an ISO string from the API; the locale formats it, never a template.
function stopDate(iso) {
  return new Date(iso).toLocaleDateString(locale.value, { month: "short", day: "numeric" });
}
</script>

<template>
  <div class="home">
    <header class="home__head">
      <h1 class="home__title">{{ t("roadside.home.title") }}</h1>
      <p class="home__sub">{{ t("roadside.subtitle") }}</p>
    </header>

    <SkeletonCard v-if="state === LoadState.LOADING" :count="3" />

    <p v-else-if="state === LoadState.FAILED" class="home__note" role="alert">
      {{ failure === Failure.OFFLINE ? t("system.load_offline") : t("roadside.failed") }}
      <button class="home__retry" type="button" @click="load">{{ t("roadside.retry") }}</button>
    </p>

    <template v-else>
      <!-- 1. where the driver stands -->
      <section class="card">
        <h2 class="card__label">{{ t("roadside.home.readiness") }}</h2>
        <p v-if="bandKey" class="card__band" :data-band="progress.band">{{ t(bandKey) }}</p>
        <p v-else class="home__note">{{ t("roadside.home.no_check") }}</p>

        <p v-if="isDriving" class="home__note">
          {{ t("roadside.session.paused_driving") }}
          <span class="home__hint">{{ t("roadside.session.paused_driving_hint") }}</span>
        </p>
        <!-- the catalogue's empty state is the expected one today: nothing released -->
        <p v-else-if="!scenarios.length" class="home__note">{{ t("roadside.empty") }}</p>
        <button v-else class="card__cta" type="button" @click="start">
          <Mic :size="20" aria-hidden="true" />
          <span>{{ bandKey ? t("roadside.home.check_again") : t("roadside.start") }}</span>
        </button>
      </section>

      <!-- 2. today's practice -->
      <section class="card">
        <h2 class="card__label">{{ t("roadside.home.practice") }}</h2>
        <p class="home__note">
          {{ drill.completed
            ? t("roadside.drill.done")
            : drill.due
              ? t("roadside.drill.left", { n: drill.due })
              : t("roadside.drill.none") }}
        </p>
        <button
          class="card__row"
          type="button"
          @click="router.push({ name: 'roadside-drill' })"
        >
          <GraduationCap :size="20" aria-hidden="true" />
          <span>{{ t("roadside.drill.cta") }}</span>
        </button>
      </section>

      <!-- 3. progress. Three counters, each of which is a column. -->
      <section v-if="skills.seen" class="card">
        <h2 class="card__label">{{ t("roadside.home.progress") }}</h2>
        <ul class="strip">
          <li class="strip__cell">
            <span class="strip__n">{{ skills.seen }}</span>
            <span class="strip__k">{{ t("roadside.home.seen") }}</span>
          </li>
          <li class="strip__cell">
            <span class="strip__n">{{ skills.passed }}</span>
            <span class="strip__k">{{ t("roadside.home.passed") }}</span>
          </li>
          <li class="strip__cell">
            <span class="strip__n">{{ skills.due }}</span>
            <span class="strip__k">{{ t("roadside.home.due") }}</span>
          </li>
        </ul>
      </section>

      <!-- 4. past stops. An abandoned stop is listed: it still happened. -->
      <section class="card">
        <h2 class="card__label">{{ t("roadside.home.history") }}</h2>
        <p v-if="!sessions.length" class="home__note">{{ t("roadside.home.no_history") }}</p>
        <ul v-else class="stops">
          <li v-for="stop in sessions" :key="stop.id">
            <button class="card__row" type="button" @click="openStop(stop.id)">
              <History :size="20" aria-hidden="true" />
              <span class="stops__date">{{ stopDate(stop.started_at) }}</span>
              <span class="stops__band" :data-band="stop.band || 'none'">
                {{ stop.band
                  ? t(`roadside.band.${stop.band}${stop.provisional ? "_provisional" : ""}`)
                  : t("roadside.home.unfinished") }}
              </span>
            </button>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  padding: var(--s-4);
}
.home__head {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.home__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.home__sub,
.home__note {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.home__note {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.home__hint {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.card {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  padding: var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.card__label {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  font-weight: var(--type-label-weight);
}
/* the band is the figure on this card — §11.1's Meter treatment, as the result screen */
.card__band {
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  color: var(--text-1);
}
.card__band[data-band="green"] {
  color: var(--ledger-500);
}
.card__band[data-band="yellow"] {
  color: var(--marker-500);
}
.card__band[data-band="red"] {
  color: var(--flare-500);
}
.card__cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  min-height: var(--touch-primary);
  padding: var(--s-3) var(--s-4);
  border: 0;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-family: var(--font-sans);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
  font-weight: var(--type-label-weight);
}
.card__row {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  width: 100%;
  min-height: var(--touch-min);
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-2);
  color: var(--text-1);
  font-family: var(--font-sans);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
  text-align: start;
}
.strip {
  display: flex;
  gap: var(--s-3);
  margin: 0;
  padding: 0;
  list-style: none;
}
.strip__cell {
  display: flex;
  flex: 1 1 0;
  flex-direction: column;
  gap: var(--s-1);
  align-items: flex-start;
}
.strip__n {
  font-family: var(--font-mono);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  color: var(--text-1);
}
.strip__k {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-caption-line);
}
.stops {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.stops__date {
  flex: 0 0 auto;
  font-family: var(--font-mono);
}
.stops__band {
  flex: 1 1 auto;
  text-align: end;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-caption-line);
}
.home__retry {
  min-height: var(--touch-min);
  align-self: flex-start;
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-2);
  color: var(--text-1);
  font-family: var(--font-sans);
  font-size: var(--type-label-size);
  line-height: var(--type-label-line);
}
</style>
