<!-- AI-CONTEXT: Claim detail (M3-FR5) — the contents of a filed detention claim:
     the money, the terms it's owed under, and the GPS-verified F4 evidence chain
     behind it (arrival, notice, photos). Reached from the Load tab's "Claim filed"
     banner. Shows WHO it's owed to and HOW it settles by claim mode: invoice (own
     authority -> billed to the broker, money owed to the driver) vs evidence_only
     (company driver -> pack handed to their carrier, not the driver's money). The
     shareable PDF is the F4 render seam (deferred). Money is Mono/tabular. -->
<script setup>
import { ref, computed, onMounted } from "vue";
import { ArrowLeft, ShieldCheck, MapPin, Camera, Send, FileText } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { formatMoney, formatClock } from "../core/meter.js";
import { fetchClaim } from "../core/api.js";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const claim = ref(null);
const missing = ref(false);

onMounted(async () => {
  try {
    claim.value = await fetchClaim(route.params.stopId);
  } catch {
    missing.value = true;
  }
});

const owed = computed(() => claim.value?.mode === "invoice");
const rateHr = computed(() => (claim.value ? Math.round(claim.value.rate_cents_per_hour / 100) : 0));

// friendly labels for the evidence timeline record types
const EV = {
  GEOFENCE: { key: "claim.ev_gps", icon: MapPin },
  PHOTO: { key: "claim.ev_photo", icon: Camera },
  DOCUMENT: { key: "claim.ev_doc", icon: FileText },
  NOTIFICATION: { key: "claim.ev_notice", icon: Send },
  USER_ACTION: { key: "claim.ev_action", icon: ShieldCheck },
  SYSTEM: { key: "claim.ev_system", icon: ShieldCheck },
};
function evLabel(type) {
  return t(EV[type]?.key ?? "claim.ev_system");
}
function evIcon(type) {
  return (EV[type] ?? EV.SYSTEM).icon;
}
function evTime(iso) {
  return iso ? iso.slice(11, 16) : "";
}
</script>

<template>
  <div class="claim">
    <header class="claim__head">
      <button class="back" type="button" :aria-label="t('facility.navigate')" @click="router.back()">
        <ArrowLeft :size="22" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="claim__title">{{ t("claim.title") }}</h1>
    </header>

    <p v-if="missing" class="muted">{{ t("claim.none") }}</p>

    <template v-else-if="claim">
      <div class="context">
        <span class="context__name">{{ claim.facility }}</span>
        <span class="context__meta">{{ claim.counterparty }}</span>
      </div>

      <!-- the money + how it settles (by mode) -->
      <section class="hero" :class="owed ? 'hero--owed' : 'hero--export'">
        <span class="hero__amount">{{ formatMoney(claim.amount_cents) }}</span>
        <span class="hero__label">{{ owed ? t("claim.owed") : t("claim.exported") }}</span>
        <p class="hero__hint">{{ owed ? t("claim.owed_hint") : t("claim.exported_hint") }}</p>
      </section>

      <!-- how the number was reached -->
      <section class="card">
        <h2 class="card__title">{{ t("claim.breakdown") }}</h2>
        <dl class="rows">
          <div class="row">
            <dt>{{ t("claim.detention_time") }}</dt>
            <dd class="mono">{{ formatClock(claim.detention_seconds) }}</dd>
          </div>
          <div class="row">
            <dt>{{ t("claim.rate") }}</dt>
            <dd class="mono">${{ rateHr }}/h</dd>
          </div>
          <div class="row">
            <dt>{{ t("claim.free_time") }}</dt>
            <dd class="mono">{{ claim.free_time_minutes }} min</dd>
          </div>
        </dl>
      </section>

      <!-- the GPS-verified evidence chain -->
      <section class="card">
        <div class="card__head">
          <h2 class="card__title">{{ t("claim.evidence") }}</h2>
          <span v-if="claim.chain_valid" class="verified">
            <ShieldCheck :size="15" :stroke-width="2.5" aria-hidden="true" /> {{ t("claim.verified") }}
          </span>
        </div>
        <ul class="timeline">
          <li v-for="(e, i) in claim.timeline" :key="i" class="ev">
            <component :is="evIcon(e.type)" :size="16" :stroke-width="2" class="ev__icon" aria-hidden="true" />
            <span class="ev__label">{{ evLabel(e.type) }}</span>
            <span class="ev__time mono">{{ evTime(e.occurred_at) }}</span>
          </li>
          <li class="ev">
            <Send :size="16" :stroke-width="2" class="ev__icon" :class="{ ok: claim.notice_sent }" aria-hidden="true" />
            <span class="ev__label">{{ claim.notice_sent ? t("claim.notice_sent") : t("claim.notice_not_sent") }}</span>
          </li>
        </ul>
        <p class="records">{{ claim.record_count }} {{ t("claim.records") }} · {{ claim.artifact_count }} {{ t("claim.photos") }}</p>
      </section>

      <p class="doc-note">{{ t("claim.doc_note") }}</p>
    </template>
  </div>
</template>

<style scoped>
.claim {
  padding: var(--s-4);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
.claim__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}
.back {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: var(--text-1);
}
.claim__title {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.context {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.context__name {
  font-size: var(--type-title-size);
  font-weight: var(--type-title-weight);
}
.context__meta {
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-1);
  padding: var(--s-5) var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
  text-align: center;
}
.hero__amount {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-display-size);
}
.hero--owed .hero__amount {
  color: var(--ledger-500);
}
.hero__label {
  font-size: var(--type-label-size);
  color: var(--text-1);
  font-weight: 500;
}
.hero__hint {
  margin: var(--s-1) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  max-width: 40ch;
}
.card {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
}
.card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--s-3);
}
.card__title {
  margin: 0 0 var(--s-3);
  font-size: var(--type-label-size);
  color: var(--text-2);
  font-weight: 500;
}
.card__head .card__title {
  margin: 0;
}
.verified {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--shield-500);
  font-size: var(--type-caption-size);
}
.rows,
.timeline {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-2) 0;
  border-top: 1px solid var(--line-1);
}
.row:first-child {
  border-top: none;
}
.row dt {
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.row dd {
  margin: 0;
}
.ev {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-2) 0;
  border-top: 1px solid var(--line-1);
}
.ev:first-child {
  border-top: none;
}
.ev__icon {
  color: var(--text-3);
  flex: none;
}
.ev__icon.ok {
  color: var(--shield-500);
}
.ev__label {
  flex: 1;
  font-size: var(--type-body-size);
}
.ev__time {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.records {
  margin: var(--s-3) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.doc-note {
  margin: 0;
  padding: var(--s-3) var(--s-4);
  border: 1px dashed var(--line-1);
  border-radius: var(--r-card);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  text-align: center;
}
.mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.muted {
  color: var(--text-3);
  font-size: var(--type-body-size);
}
</style>
