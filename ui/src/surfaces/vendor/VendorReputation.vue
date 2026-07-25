<!-- AI-CONTEXT: what drivers actually said, in the numbers drivers actually see.

     This is the screen most likely to be softened, because its reader is the person
     being described. It is not softened:
     · The show-up figure is the raw pair ("19 of 20"), never a percentage. A fraction
       carries its own sample size; "95%" over two appearances overstates what anyone
       knows.
     · A rating never appears without its reviewer count, and no reviews reads as
       "no reviews yet", never 0.0 — a zero average reads as "rated badly" when it
       means "nobody has said".
     · Upheld reports and consecutive no-shows are shown with the threshold that acts
       on them, because a suspension that arrives unannounced is the failure this
       whole portal exists to prevent.
     · Review text is shown as written. There is no reply box and no takedown button —
       a vendor disputing a review goes through the same moderation queue as anyone
       else, and the author's words survive the verdict either way (§23 settability). -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { Star, TriangleAlert } from "lucide-vue-next";
import { useI18n } from "../../core/i18n.js";
import { fetchVendorReputation } from "../../core/api.js";

const { t } = useI18n();
const rep = ref(null);

const hasRating = computed(() => (rep.value?.rating?.reviewers ?? 0) > 0);

function when(iso) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";
}

onMounted(async () => {
  rep.value = await fetchVendorReputation().catch(() => null);
});
</script>

<template>
  <div v-if="rep" class="rep">
    <h2 class="rep__title">{{ t("vendor.nav.reputation") }}</h2>

    <section class="cards">
      <div class="stat">
        <span class="stat__figure">
          {{ rep.shows_up.confirmed }} / {{ rep.shows_up.published }}
        </span>
        <span class="stat__label">{{ t("vendor.stat.shows_up") }}</span>
        <span class="stat__note">{{ t("vendor.shows_up_note") }}</span>
      </div>
      <div class="stat">
        <span v-if="hasRating" class="stat__figure">
          <Star :size="20" :stroke-width="2" aria-hidden="true" />
          {{ rep.rating.average.toFixed(1) }}
        </span>
        <span v-else class="stat__none">{{ t("vendor.no_reviews") }}</span>
        <span v-if="hasRating" class="stat__label">
          {{ rep.rating.reviewers }} {{ t("vendor.reviewers") }}
        </span>
      </div>
    </section>

    <!-- the count and the consequence in one place -->
    <p v-if="rep.publish_suspended" class="alert" role="alert">
      <TriangleAlert :size="18" :stroke-width="2" aria-hidden="true" />
      {{ t("portal.vendor.suspended") }}
    </p>
    <p v-else-if="rep.consecutive_no_shows > 0" class="warn">
      {{ t("vendor.no_shows_warning", { n: rep.consecutive_no_shows }) }}
    </p>

    <section v-if="rep.upheld_reports > 0" class="card">
      <h3 class="card__title">{{ t("vendor.upheld_reports") }}</h3>
      <p class="card__body">
        <span class="figure">{{ rep.upheld_reports }}</span>
        {{ t("vendor.upheld_note") }}
      </p>
    </section>

    <section class="card">
      <h3 class="card__title">{{ t("vendor.what_drivers_said") }}</h3>
      <p v-if="!rep.reviews.length" class="card__empty">{{ t("vendor.no_reviews") }}</p>
      <ul v-else class="reviews">
        <li v-for="r in rep.reviews" :key="r.review_id" class="review">
          <div class="review__head">
            <span class="review__rating">{{ r.rating }}</span>
            <span class="review__when">{{ when(r.at) }}</span>
          </div>
          <!-- as written. No edit, no reply, no takedown from here. -->
          <p v-if="r.text" class="review__text">{{ r.text }}</p>
        </li>
      </ul>
      <p class="card__note">{{ t("vendor.review_policy") }}</p>
    </section>
  </div>
</template>

<style scoped>
.rep__title {
  margin: 0 0 var(--s-4);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
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
  display: flex;
  align-items: center;
  gap: var(--s-2);
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
.stat__note {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.alert {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0 0 var(--s-4);
  padding: var(--s-3);
  border: 1px solid var(--flare-500);
  border-radius: var(--r-control);
  color: var(--flare-500);
  font-size: var(--type-body-size);
}
.warn {
  margin: 0 0 var(--s-4);
  padding: var(--s-3);
  border: 1px solid var(--marker-500);
  border-radius: var(--r-control);
  color: var(--marker-500);
  font-size: var(--type-body-size);
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
.card__body {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.card__empty {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.card__note {
  margin: var(--s-3) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.reviews {
  list-style: none;
  margin: 0;
  padding: 0;
}
.review {
  padding: var(--s-3) 0;
  border-bottom: 1px solid var(--line-1);
}
.review__head {
  display: flex;
  align-items: baseline;
  gap: var(--s-3);
}
.review__rating {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-title-size);
}
.review__when {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.review__text {
  margin: var(--s-2) 0 0;
  color: var(--text-1);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
</style>
