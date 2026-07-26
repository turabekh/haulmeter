<!-- AI-CONTEXT: Vendor sheet (M13-FR3) — an instance of the §8 bottom-sheet pattern,
     like SleepSheet/HandoffSheet. Everything a driver needs to decide on a detour:
     what's cooking and what it costs, when he's there, what languages he speaks,
     the halal disclosure in his own words, the verification tier, and — the part
     that makes a detour trustworthy — how often he actually shows up.

     Two honesty rules govern this sheet:
     · §11.7 — a CROWD confirmation reads "3 drivers · 20m"; the vendor's own claim
       reads "vendor says here". `presenceLabel` cannot produce a driver count for a
       vendor-sourced belief, so the two can never blur.
     · Q-2 — reliability shows as the raw pair "shows up 19 of 20", never a
       percentage: the fraction carries its own sample size.

     DRIVING (§13.4, Forbidden #11): the confirm buttons DO NOT RENDER. Reading is
     fine at a glance; tapping "he's here" at 65 mph is not. -->
<script setup>
import { computed, ref } from "vue";
import { Check, Languages, MapPin, Navigation, Star } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { useDriverState } from "../state.js";
import { formatMiles } from "../presentation.js";
import {
  bucketLabelKey,
  presenceLabel,
  priceLabel,
  reasonLabelKey,
  reviewSummary,
  verificationPresentation,
  windowLabel,
  REPORT_REASONS,
} from "../vendors.js";

const props = defineProps({
  sheet: { type: Object, required: true },
  // the appearance the driver actually tapped. The sheet may list several, at
  // different lots — navigation has to mean THIS one, not "somewhere this cook
  // works this week".
  target: { type: Object, default: null },
});
const emit = defineEmits([
  "confirm",
  "not-here",
  "sold-out",
  "mute",
  "review",
  "report",
  "navigate",
  "follow",
  "unfollow",
]);
const { t } = useI18n();
const { isDriving } = useDriverState();

const now = Date.now();
const tier = computed(() => verificationPresentation(props.sheet.verify_status));
const showsUp = computed(() =>
  props.sheet.shows_up?.published ? props.sheet.shows_up : null,
);
const next = computed(() => props.sheet.appearances?.[0] ?? null);
// what Navigate will open: the tapped appearance, falling back to the next one the
// sheet is showing. Rendered only when we actually hold coordinates — a button that
// might not go anywhere is worse than no button.
const going = computed(() => {
  const t = props.target?.lat != null ? props.target : null;
  return t ?? (next.value?.lat != null ? next.value : null);
});
const goingMiles = computed(() => formatMiles(going.value?.distance_m));
const following = computed(() => props.sheet.following === true);
const anyDistance = computed(() =>
  (props.sheet.appearances ?? []).some((a) => a.distance_m != null),
);
function whenLabel(appearance) {
  return windowLabel(appearance?.starts_at, appearance?.ends_at, now);
}
const reviews = computed(() => reviewSummary(props.sheet.reviews));
const reviewItems = computed(() => props.sheet.reviews?.items ?? []);
// FR6 / Q-3: promoted content arrives in its OWN key and renders in its own
// labelled container. It is never concatenated into the schedule or the menu.
const promotions = computed(() => props.sheet.promotions ?? []);
const reporting = ref(false);
const rating = ref(0);
const reviewText = ref("");

function sendReview() {
  if (!rating.value) return;
  emit("review", { rating: rating.value, text: reviewText.value || null });
  rating.value = 0;
  reviewText.value = "";
}
const presence = computed(() =>
  presenceLabel(next.value?.presence, now, { vendorSays: t("vendor.says_here") }),
);
</script>

<template>
  <div class="vs">
    <h3 class="vs__name">{{ sheet.name }}</h3>

    <!-- tier is colour + icon + label (C-1); "license on file" stays neutral
         because paperwork is not an endorsement -->
    <div class="vs__row">
      <span class="vs__tier" :style="{ color: `var(${tier.token})` }">
        <Check v-if="sheet.verify_status === 'verified'" :size="16" :stroke-width="2.5" aria-hidden="true" />
        {{ t(tier.labelKey) }}
      </span>
      <span v-if="presence" class="vs__fresh">{{ presence }}</span>
    </div>

    <!-- Q-2: the number that makes a pre-driving detour trustworthy -->
    <p v-if="showsUp" class="vs__reliability">
      {{ t("vendor.shows_up") }}
      <span class="vs__figure">{{ showsUp.confirmed }}</span>
      {{ t("vendor.of") }}
      <span class="vs__figure">{{ showsUp.published }}</span>
    </p>

    <!-- schedule: WHERE, then when. The lot was named on the card and used to be
         dropped here, which left "Today · until 9pm" attached to no place at all —
         ambiguous the moment a cook works more than one lot. -->
    <ul class="vs__schedule">
      <li v-for="a in sheet.appearances" :key="a.starts_at" class="vs__slot">
        <MapPin :size="16" :stroke-width="2" aria-hidden="true" />
        <span class="vs__lot">{{ a.facility_name || t("vendor.lot_unknown") }}</span>
        <span class="vs__when">{{ t(bucketLabelKey(a.bucket)) }}</span>
        <!-- the WINDOW, not only its end: "opens 5pm" before, "5–9pm" once open -->
        <span class="vs__until">
          <template v-if="whenLabel(a).key">{{ t(whenLabel(a).key) }} </template>
          {{ whenLabel(a).value }}
        </span>
        <span v-if="a.distance_m != null" class="vs__miles">
          {{ formatMiles(a.distance_m) }} {{ t("unit.mi") }}
        </span>
        <span v-if="a.sold_out" class="vs__soldout">{{ t("vendor.sold_out") }}</span>
      </li>
    </ul>
    <!-- said ONCE, not on every row: these are straight lines, not driving
         distances, and no arrival time is derived from them (§11.7; truck routing
         is §17 Q9 and open) -->
    <p v-if="anyDistance" class="vs__direct">{{ t("vendor.distance_direct") }}</p>

    <!-- menu: prices are Mono figures like every other money figure (T-2) -->
    <ul v-if="next?.offerings?.length" class="vs__menu">
      <li v-for="o in next.offerings" :key="o.name" class="vs__item">
        <span class="vs__dish">{{ o.name }}</span>
        <span class="vs__price">{{ priceLabel(o.price_cents) }}</span>
      </li>
    </ul>

    <!-- FR6 / Q-3: the LABELLED slot. It sits in its own container with its own
         "Promoted" label, below the organic content, and is never blended into the
         schedule or the menu above. §21.3 forbids ads; this is vendor-supplied text
         a driver can see the provenance of, not platform promotion. -->
    <div v-for="p in promotions" :key="p.promotion_id" class="vs__promo">
      <span class="vs__promo-label">{{ t("vendor.promoted") }}</span>
      <span class="vs__promo-text">{{ p.text }}</span>
    </div>

    <p v-if="sheet.languages?.length" class="vs__meta">
      <Languages :size="16" :stroke-width="2" aria-hidden="true" />
      {{ t("vendor.languages") }}: {{ sheet.languages.join(" · ") }}
    </p>

    <!-- the RUNG names who is speaking; the sentence beneath is the vendor's own
         words, verbatim. Neither is the platform claiming anything (§23). -->
    <p v-if="sheet.halal_claim && sheet.halal_claim !== 'not_claimed'" class="vs__meta">
      {{ t(`vendor.halal_claim.${sheet.halal_claim}`) }}
    </p>
    <p class="vs__meta">
      {{ t("vendor.halal") }}:
      {{ sheet.halal_disclosure || t("vendor.halal_none") }}
    </p>

    <!-- FR5: the pair, never a bare average — a "4.6" with no denominator invites
         overreading three opinions (§11.7) -->
    <section class="vs__reviews">
      <h4 class="vs__reviews-title">
        {{ t("vendor.reviews") }}
        <span v-if="reviews" class="vs__figure">{{ reviews.average }}</span>
        <span v-if="reviews" class="vs__reviewers">
          · {{ reviews.reviewers }} {{ reviews.reviewers === 1 ? "driver" : "drivers" }}
        </span>
        <span v-else class="vs__reviewers">· {{ t("vendor.no_reviews") }}</span>
      </h4>
      <ul v-if="reviewItems.length" class="vs__review-list">
        <li v-for="(r, i) in reviewItems" :key="i" class="vs__review">
          <span class="vs__figure">{{ r.rating }}/5</span>
          <span v-if="r.text" class="vs__review-text">{{ r.text }}</span>
        </li>
      </ul>
    </section>

    <!-- DRIVING: read-only. No interactive prompt while moving (Forbidden #11). -->
    <template v-if="!isDriving">
      <!-- FR5 rating: chips, not a dropdown (§8 forms — chips when <=5 options) -->
      <div v-if="sheet.can_review" class="vs__rate">
        <span class="vs__rate-label">{{ t("vendor.rate") }}</span>
        <div class="vs__stars">
          <button
            v-for="n in 5"
            :key="n"
            type="button"
            class="vs__star"
            :class="{ 'vs__star--on': rating >= n }"
            :aria-label="`${n}`"
            :aria-pressed="rating === n"
            @click="rating = n"
          >
            {{ n }}
          </button>
        </div>
        <input
          v-model="reviewText"
          class="vs__review-input"
          type="text"
          maxlength="500"
          :placeholder="t('vendor.review_placeholder')"
        />
        <button class="cta cta--secondary" type="button" :disabled="!rating" @click="sendReview">
          {{ t("vendor.review_send") }}
        </button>
      </div>
      <p v-else-if="reviews" class="vs__meta">{{ t("vendor.review_too_soon") }}</p>

      <!-- §23: the PRIMARY action is Navigate. This sheet is read while deciding
           whether to go; a crowd-contribution affordance must not outrank the one
           action the whole flow exists to produce. "Here now" stays one tap away
           for the driver who has already arrived.
           The distance rides the button so the cost of the decision sits on the
           control that acts on it. -->
      <button v-if="going" class="cta" type="button" @click="emit('navigate', going)">
        <Navigation :size="18" :stroke-width="2" aria-hidden="true" />
        {{ t("vendor.navigate") }}
        <span v-if="goingMiles" class="cta__miles">{{ goingMiles }} {{ t("unit.mi") }}</span>
      </button>
      <button class="cta cta--secondary" type="button" @click="emit('confirm')">
        {{ t("vendor.here_now") }}
      </button>
      <button class="cta cta--secondary" type="button" @click="emit('not-here')">
        {{ t("vendor.not_here") }}
      </button>
      <button class="cta cta--secondary" type="button" @click="emit('sold-out')">
        {{ t("vendor.report_sold_out") }}
      </button>
      <!-- following. The button states what one tap does BEFORE it is tapped:
           §23 E-D1 makes silence never consent, so the control that supplies the
           consent has to say what it is turning on, and name the caps in the same
           breath so "we will tell you" cannot be read as "we will pester you". -->
      <button
        class="cta cta--secondary"
        type="button"
        :aria-pressed="following"
        @click="emit(following ? 'unfollow' : 'follow')"
      >
        <Star :size="18" :stroke-width="2" aria-hidden="true" />
        {{ following ? t("vendor.following") : t("vendor.follow") }}
      </button>
      <p class="vs__follow-note">
        {{ following ? t("vendor.follow_on_note") : t("vendor.follow_note") }}
      </p>

      <button class="cta cta--tertiary" type="button" @click="emit('mute')">
        {{ t("vendor.mute") }}
      </button>

      <!-- Q-8: the report affordance. Deliberately a tertiary text button at the
           very bottom — reporting must be available without being suggestive. -->
      <button class="cta cta--tertiary" type="button" @click="reporting = !reporting">
        {{ t("vendor.report") }}
      </button>
      <div v-if="reporting" class="vs__reasons">
        <span class="vs__rate-label">{{ t("vendor.report_title") }}</span>
        <button
          v-for="reason in REPORT_REASONS"
          :key="reason"
          type="button"
          class="vs__reason"
          @click="emit('report', reason); reporting = false"
        >
          {{ t(reasonLabelKey(reason)) }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.vs__name {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.vs__row {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-2);
}
.vs__tier {
  display: flex;
  align-items: center;
  gap: var(--s-1);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.vs__fresh {
  margin-left: auto;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.vs__reliability {
  margin: var(--s-3) 0 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.vs__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-1);
}
.vs__schedule,
.vs__menu {
  list-style: none;
  margin: var(--s-3) 0 0;
  padding: 0;
}
.vs__slot {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-2);
  min-height: 48px;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.vs__lot {
  color: var(--text-1);
  font-weight: 500;
}
.vs__when {
  color: var(--text-1);
}
/* every distance is a Mono figure, like every other figure in the product (T-2) */
.vs__miles {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-2);
}
.vs__follow-note {
  margin: var(--s-2) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.vs__direct {
  margin: 0 0 var(--s-3);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.vs__until {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.vs__soldout {
  margin-left: auto;
  padding: 2px var(--s-2);
  border-radius: var(--r-pill);
  background: var(--ink-2, var(--line-1));
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.vs__item {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
  min-height: 48px;
  border-top: 1px solid var(--line-1);
}
.vs__dish {
  font-size: var(--type-body-size);
}
.vs__price {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-body-size);
}
.vs__meta {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: var(--s-3) 0 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
/* the promoted slot: its own container, its own label, visually quieter than the
   organic content above it. Marker amber is the caution/attention token already in
   the system — no new colour was introduced (§6 / §23 E-D2 discipline). */
.vs__promo {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  margin-top: var(--s-3);
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
}
.vs__promo-label {
  flex: 0 0 auto;
  padding: 2px var(--s-2);
  border-radius: var(--r-pill);
  background: var(--ink-2, var(--line-1));
  color: var(--marker-500);
  font-size: var(--type-caption-size);
  font-weight: 500;
}
.vs__promo-text {
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.vs__reviews {
  margin-top: var(--s-4);
  padding-top: var(--s-3);
  border-top: 1px solid var(--line-1);
}
.vs__reviews-title {
  display: flex;
  align-items: baseline;
  gap: var(--s-1);
  margin: 0 0 var(--s-2);
  color: var(--text-2);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.vs__reviewers {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.vs__review-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.vs__review {
  display: flex;
  align-items: baseline;
  gap: var(--s-2);
  min-height: 48px;
  font-size: var(--type-caption-size);
}
.vs__review-text {
  color: var(--text-2);
  line-height: var(--type-body-line);
}
.vs__rate {
  margin-top: var(--s-4);
}
.vs__rate-label {
  display: block;
  margin-bottom: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.vs__stars {
  display: flex;
  gap: var(--s-2);
}
.vs__star {
  flex: 1;
  min-height: 48px;
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--text-2);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.vs__star--on {
  border-color: var(--shield-500);
  color: var(--shield-500);
}
.vs__review-input {
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-3);
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.vs__reasons {
  margin-top: var(--s-3);
}
.vs__reason {
  display: block;
  width: 100%;
  min-height: 48px;
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  margin-top: var(--s-2);
  background: transparent;
  color: var(--text-1);
  font-size: var(--type-label-size);
  text-align: left;
  padding: 0 var(--s-3);
}
.cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-4);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta__miles {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  opacity: 0.85;
}
.cta--secondary {
  margin-top: var(--s-2);
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
}
.cta--tertiary {
  margin-top: var(--s-2);
  min-height: 48px;
  background: transparent;
  color: var(--shield-500);
}
</style>
