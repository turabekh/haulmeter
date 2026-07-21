<!-- AI-CONTEXT: Public Scorecard — a web-first PUBLIC portal (design-prd §18): no
     login (route meta.public), desktop-first, comfortable layout, 1200 dp cap,
     shares ui/core tokens, NOT a driver-app screen. The public face of the M2
     facility data: search a facility, see its objective dock time (Mono, with
     sample size ALWAYS shown, §11.7) and driver rating. Aggregate-only, min-
     sample suppressed server-side (§13). Fixture-backed demo when the API is
     unreachable. -->
<script setup>
import { ref, onMounted } from "vue";
import { Search, Star } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { formatDwell } from "../core/presentation.js";
import { searchFacilities, fetchScorecard } from "../core/api.js";
import { sampleFacilities, sampleScorecard } from "../core/fixtures.js";

const { t } = useI18n();
const q = ref("");
const results = ref([]);
const selected = ref(null);

async function runSearch() {
  try {
    results.value = await searchFacilities(q.value);
  } catch {
    results.value = sampleFacilities(); // offline / demo
  }
}
onMounted(runSearch);

async function open(fac) {
  try {
    selected.value = await fetchScorecard(fac.id);
  } catch {
    selected.value = sampleScorecard(fac.id); // offline / demo
  }
}
</script>

<template>
  <div class="score">
    <h1 class="score__title">{{ t("score.title") }}</h1>

    <form class="search" @submit.prevent="runSearch">
      <Search :size="18" :stroke-width="2" class="search__icon" aria-hidden="true" />
      <input
        v-model="q"
        class="search__input"
        type="search"
        :placeholder="t('score.search')"
        :aria-label="t('score.search')"
        @input="runSearch"
      />
    </form>

    <div class="cols">
      <ul class="list">
        <li v-for="f in results" :key="f.id">
          <button
            class="list__row"
            :class="{ 'list__row--on': selected && selected.id === f.id }"
            type="button"
            @click="open(f)"
          >
            {{ f.name }}
          </button>
        </li>
      </ul>

      <section v-if="selected" class="card">
        <h2 class="card__name">{{ selected.name }}</h2>

        <div class="stat">
          <span class="stat__label">{{ t("score.dock") }}</span>
          <template v-if="selected.dwell">
            <span class="stat__figure">{{ formatDwell(selected.dwell.median_seconds) }}</span>
            <span class="stat__meta">
              {{ t("score.median") }} · {{ selected.dwell.sample_size }} {{ t("score.stops") }}
            </span>
          </template>
          <span v-else class="muted">{{ t("score.no_dwell") }}</span>
        </div>

        <div class="stat">
          <span class="stat__label">{{ t("score.rating") }}</span>
          <span class="rating">
            <Star :size="18" :stroke-width="2" class="rating__star" aria-hidden="true" />
            <span class="stat__figure">{{ selected.rating.overall ?? "—" }}</span>
            <span class="stat__meta">· {{ selected.rating.review_count }} {{ t("score.reviews") }}</span>
          </span>
        </div>

        <div v-if="selected.reviews && selected.reviews.length" class="stat">
          <span class="stat__label">{{ t("score.what_drivers_say") }}</span>
          <ul class="snips">
            <li v-for="(r, i) in selected.reviews" :key="i" class="snip">“{{ r }}”</li>
          </ul>
        </div>
      </section>
      <p v-else class="muted hint">{{ t("score.search_hint") }}</p>
    </div>
  </div>
</template>

<style scoped>
.score {
  padding: var(--s-5);
}
.score__title {
  margin: 0 0 var(--s-4);
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
.search {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  max-width: 560px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-1);
  margin-bottom: var(--s-4);
}
.search__icon {
  color: var(--text-3);
  flex: none;
}
.search__input {
  flex: 1 1 auto;
  min-height: 52px;
  border: none;
  background: transparent;
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.cols {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--s-4);
}
@media (min-width: 720px) {
  .cols {
    grid-template-columns: 320px 1fr;
    align-items: start;
  }
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.list__row {
  width: 100%;
  text-align: left;
  min-height: 48px;
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.list__row--on {
  border-color: var(--shield-500);
  color: var(--shield-500);
}
.card {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
}
.card__name {
  margin: 0 0 var(--s-3);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.stat {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  padding: var(--s-3) 0;
  border-top: 1px solid var(--line-1);
}
.stat__label {
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.stat__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
}
.stat__meta {
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
.snips {
  list-style: none;
  margin: var(--s-1) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.snip {
  color: var(--text-2);
  font-size: var(--type-body-size);
  font-style: italic;
  line-height: 1.4;
}
.muted {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.hint {
  padding: var(--s-3) 0;
}
</style>
