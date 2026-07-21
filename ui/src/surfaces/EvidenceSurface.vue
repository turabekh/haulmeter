<!-- AI-CONTEXT: Evidence locker (M5 / M3) — everything captured for a load in one
     place: the GPS-verified F4 timeline (arrival, notice), the cargo-condition
     PHOTOS with their guided prompt + capture time + verified hash, and the
     documents on file. Aggregates every evidence log tied to the stop, with a
     chain-integrity badge. Reached from the Load tab's Evidence card. Actual photo
     images are served from F6 at activation — here each is a verified, labeled
     entry (never a fake thumbnail). -->
<script setup>
import { ref, onMounted } from "vue";
import { ArrowLeft, ShieldCheck, MapPin, Camera, Send, FileText, ShieldAlert } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { fetchEvidence } from "../core/api.js";

const route = useRoute();
const router = useRouter();
const { t } = useI18n();
const data = ref(null);
const missing = ref(false);

onMounted(async () => {
  try {
    data.value = await fetchEvidence(route.params.stopId);
  } catch {
    missing.value = true;
  }
});

const EV = {
  GEOFENCE: { key: "claim.ev_gps", icon: MapPin },
  PHOTO: { key: "claim.ev_photo", icon: Camera },
  DOCUMENT: { key: "claim.ev_doc", icon: FileText },
  NOTIFICATION: { key: "claim.ev_notice", icon: Send },
  USER_ACTION: { key: "claim.ev_action", icon: ShieldAlert },
  SYSTEM: { key: "claim.ev_system", icon: ShieldCheck },
};
const evLabel = (type) => t(EV[type]?.key ?? "claim.ev_system");
const evIcon = (type) => (EV[type] ?? EV.SYSTEM).icon;
const time = (iso) => (iso ? iso.slice(11, 16) : "");
// guided prompts have friendly names; fall back to the raw prompt
function photoLabel(prompt) {
  if (!prompt) return t("claim.ev_photo");
  const key = `cond.step.${prompt}`;
  const label = t(key);
  return label === key ? prompt : label;
}
</script>

<template>
  <div class="ev">
    <header class="ev__head">
      <button class="back" type="button" :aria-label="t('facility.navigate')" @click="router.back()">
        <ArrowLeft :size="22" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="ev__title">{{ t("evidence.title") }}</h1>
    </header>

    <p v-if="missing" class="muted">{{ t("claim.none") }}</p>

    <template v-else-if="data">
      <div class="context">
        <span class="context__name">{{ data.facility }}</span>
        <span v-if="data.chain_valid" class="verified">
          <ShieldCheck :size="14" :stroke-width="2.5" aria-hidden="true" /> {{ t("claim.verified") }}
        </span>
      </div>

      <!-- cargo-condition photos -->
      <section class="card">
        <h2 class="card__title">{{ t("evidence.photos") }} · {{ data.photo_count }}</h2>
        <p v-if="!data.photos.length" class="muted">{{ t("evidence.no_photos") }}</p>
        <ul v-else class="photos">
          <li v-for="(p, i) in data.photos" :key="i" class="photo">
            <div class="photo__thumb" aria-hidden="true"><Camera :size="22" :stroke-width="2" /></div>
            <div class="photo__meta">
              <span class="photo__label">{{ photoLabel(p.prompt) }}</span>
              <span class="photo__sub mono">{{ time(p.captured_at) }} · #{{ p.content_hash }}</span>
            </div>
            <ShieldCheck :size="16" :stroke-width="2.5" class="photo__ok" aria-hidden="true" />
          </li>
        </ul>
      </section>

      <!-- the full verified timeline -->
      <section class="card">
        <h2 class="card__title">{{ t("evidence.timeline") }}</h2>
        <p v-if="!data.timeline.length" class="muted">{{ t("evidence.no_events") }}</p>
        <ul v-else class="tl">
          <li v-for="(e, i) in data.timeline" :key="i" class="tl__item">
            <component :is="evIcon(e.type)" :size="16" :stroke-width="2" class="tl__icon" aria-hidden="true" />
            <span class="tl__label">{{ evLabel(e.type) }}</span>
            <span class="tl__time mono">{{ time(e.occurred_at) }}</span>
          </li>
        </ul>
      </section>

      <!-- documents on file -->
      <section v-if="data.documents.length" class="card">
        <h2 class="card__title">{{ t("evidence.documents") }}</h2>
        <ul class="docs">
          <li v-for="(d, i) in data.documents" :key="i" class="doc">
            <FileText :size="16" :stroke-width="2" class="doc__icon" aria-hidden="true" />
            <span class="doc__name">{{ d.doc_type.toUpperCase() }}</span>
            <span class="doc__status" :class="d.status !== 'ok' ? 'doc__status--warn' : ''">{{ d.status }}</span>
          </li>
        </ul>
      </section>

      <p class="doc-note">{{ t("evidence.images_note") }}</p>
    </template>
  </div>
</template>

<style scoped>
.ev {
  padding: var(--s-4);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
.ev__head {
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
.ev__title {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.context {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.context__name {
  font-size: var(--type-title-size);
  font-weight: var(--type-title-weight);
}
.verified {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--shield-500);
  font-size: var(--type-caption-size);
}
.card {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
}
.card__title {
  margin: 0 0 var(--s-3);
  font-size: var(--type-label-size);
  color: var(--text-2);
  font-weight: 500;
}
.photos,
.tl,
.docs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.photo {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-2) 0;
  border-top: 1px solid var(--line-1);
}
.photo:first-child {
  border-top: none;
}
.photo__thumb {
  width: 44px;
  height: 44px;
  border-radius: var(--r-control);
  background: var(--ink-2, var(--line-1));
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
  flex: none;
}
.photo__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.photo__label {
  font-size: var(--type-body-size);
}
.photo__sub {
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.photo__ok {
  color: var(--shield-500);
  flex: none;
}
.tl__item,
.doc {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-2) 0;
  border-top: 1px solid var(--line-1);
}
.tl__item:first-child,
.doc:first-child {
  border-top: none;
}
.tl__icon,
.doc__icon {
  color: var(--text-3);
  flex: none;
}
.tl__label,
.doc__name {
  flex: 1;
  font-size: var(--type-body-size);
}
.tl__time {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.doc__status {
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.doc__status--warn {
  color: var(--flare-500);
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
  margin: 0;
}
</style>
