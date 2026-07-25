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
import { computed } from "vue";
import { Check, Languages, MapPin } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { useDriverState } from "../state.js";
import {
  bucketLabelKey,
  presenceLabel,
  priceLabel,
  untilLabel,
  verificationPresentation,
} from "../vendors.js";

const props = defineProps({
  sheet: { type: Object, required: true },
});
const emit = defineEmits(["confirm", "not-here", "sold-out", "mute"]);
const { t } = useI18n();
const { isDriving } = useDriverState();

const now = Date.now();
const tier = computed(() => verificationPresentation(props.sheet.verify_status));
const showsUp = computed(() =>
  props.sheet.shows_up?.published ? props.sheet.shows_up : null,
);
const next = computed(() => props.sheet.appearances?.[0] ?? null);
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

    <!-- schedule: the one time fact that matters, figure first (§12.2) -->
    <ul class="vs__schedule">
      <li v-for="a in sheet.appearances" :key="a.starts_at" class="vs__slot">
        <MapPin :size="16" :stroke-width="2" aria-hidden="true" />
        <span class="vs__when">{{ t(bucketLabelKey(a.bucket)) }}</span>
        <span class="vs__until">{{ t("vendor.until") }} {{ untilLabel(a.ends_at) }}</span>
        <span v-if="a.sold_out" class="vs__soldout">{{ t("vendor.sold_out") }}</span>
      </li>
    </ul>

    <!-- menu: prices are Mono figures like every other money figure (T-2) -->
    <ul v-if="next?.offerings?.length" class="vs__menu">
      <li v-for="o in next.offerings" :key="o.name" class="vs__item">
        <span class="vs__dish">{{ o.name }}</span>
        <span class="vs__price">{{ priceLabel(o.price_cents) }}</span>
      </li>
    </ul>

    <p v-if="sheet.languages?.length" class="vs__meta">
      <Languages :size="16" :stroke-width="2" aria-hidden="true" />
      {{ t("vendor.languages") }}: {{ sheet.languages.join(" · ") }}
    </p>

    <!-- the vendor's own words, verbatim — we make no halal claim of our own -->
    <p class="vs__meta">
      {{ t("vendor.halal") }}:
      {{ sheet.halal_disclosure || t("vendor.halal_none") }}
    </p>

    <!-- DRIVING: read-only. No interactive prompt while moving (Forbidden #11). -->
    <template v-if="!isDriving">
      <button class="cta" type="button" @click="emit('confirm')">
        {{ t("vendor.here_now") }}
      </button>
      <button class="cta cta--secondary" type="button" @click="emit('not-here')">
        {{ t("vendor.not_here") }}
      </button>
      <button class="cta cta--secondary" type="button" @click="emit('sold-out')">
        {{ t("vendor.report_sold_out") }}
      </button>
      <button class="cta cta--tertiary" type="button" @click="emit('mute')">
        {{ t("vendor.mute") }}
      </button>
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
  gap: var(--s-2);
  min-height: 48px;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.vs__when {
  color: var(--text-1);
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
