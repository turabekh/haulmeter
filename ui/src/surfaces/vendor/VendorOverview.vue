<!-- AI-CONTEXT: the portal's landing section — what a cook needs to know before
     deciding what to do today, and nothing else.

     Every figure here is the SAME figure a driver sees. The show-up pair is the raw
     fraction ("19 of 20"), never a percentage: a fraction carries its own sample
     size, and "95%" over two appearances would overstate what anyone knows. An
     unreviewed vendor reads "no reviews yet", never 0.0, because a zero average
     reads as "rated badly" when it means "nobody has said".

     Sheet views are this vendor's own. They were platform-wide until this session —
     every cook was shown the same inflated number as their own traffic. -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import { fetchVendorAnalytics, fetchVendorProfile, fetchVendorSchedule } from "../../core/api.js";
import { formatMoney } from "../../core/meter.js";

const { t } = useI18n();
const analytics = ref(null);
const profile = ref(null);
const schedule = ref([]);

const next = computed(() =>
  schedule.value
    .filter((a) => ["scheduled", "live"].includes(a.status))
    .sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at))
    .slice(0, 3),
);
const assisted = computed(() => profile.value?.assisted ?? []);
const rating = computed(() => analytics.value?.reviews ?? null);

function when(iso) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

onMounted(async () => {
  [profile.value, analytics.value, schedule.value] = await Promise.all([
    fetchVendorProfile().catch(() => null),
    fetchVendorAnalytics().catch(() => null),
    fetchVendorSchedule().catch(() => []),
  ]);
});
</script>

<template>
  <div class="ov">
    <!-- E-D5: the vendor is TOLD when support touched their things. An action a
         user cannot see is indistinguishable, to them, from a bug. -->
    <p v-if="assisted.length" class="ov__assisted">
      {{ t("vendor.assisted_note") }} — {{ t(`vendor.assisted.${assisted[0].action}`) }}
    </p>

    <section v-if="analytics" class="cards">
      <div class="stat">
        <span class="stat__figure">{{ analytics.sheet_views }}</span>
        <span class="stat__label">{{ t("vendor.stat.views") }}</span>
      </div>
      <div class="stat">
        <!-- the raw pair, exactly as drivers read it -->
        <span class="stat__figure">
          {{ analytics.shows_up.confirmed }} / {{ analytics.shows_up.published }}
        </span>
        <span class="stat__label">{{ t("vendor.stat.shows_up") }}</span>
      </div>
      <div class="stat">
        <span v-if="rating && rating.reviewers" class="stat__figure">
          {{ rating.average.toFixed(1) }}
        </span>
        <span v-else class="stat__none">{{ t("vendor.no_reviews") }}</span>
        <span v-if="rating && rating.reviewers" class="stat__label">
          {{ rating.reviewers }} {{ t("vendor.reviewers") }}
        </span>
      </div>
    </section>

    <section class="card">
      <h2 class="card__title">{{ t("vendor.next_up") }}</h2>
      <p v-if="!next.length" class="card__empty">{{ t("portal.vendor.no_schedule") }}</p>
      <ul v-else class="next">
        <li v-for="a in next" :key="a.appearance_id" class="next__row">
          <span class="next__when">{{ when(a.starts_at) }}</span>
          <span class="next__where">{{ a.facility_name || t("vendor.a_stop") }}</span>
          <span class="next__count">
            {{ a.offerings.length }} {{ t("vendor.items") }}
            <template v-if="a.offerings.length">
              · {{ formatMoney(Math.min(...a.offerings.map((o) => o.price_cents))) }}+
            </template>
          </span>
        </li>
      </ul>
      <router-link class="link" to="/vendor-portal/week">{{ t("vendor.manage_week") }}</router-link>
    </section>
  </div>
</template>

<style scoped>
.ov__assisted {
  margin: 0 0 var(--s-4);
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--s-3);
  margin-bottom: var(--s-4);
}
.stat {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  padding: var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.stat__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
}
.stat__none {
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.stat__label {
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.card {
  padding: var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.card__title {
  margin: 0 0 var(--s-3);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.card__empty {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.next {
  list-style: none;
  margin: 0;
  padding: 0;
}
.next__row {
  display: flex;
  align-items: baseline;
  gap: var(--s-3);
  padding: var(--s-2) 0;
  border-bottom: 1px solid var(--line-1);
}
.next__when {
  flex: 0 0 auto;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-body-size);
}
.next__where {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.next__count {
  flex: 0 0 auto;
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.link {
  display: inline-block;
  margin-top: var(--s-3);
  color: var(--shield-500);
  font-size: var(--type-label-size);
  text-decoration: none;
}
</style>
