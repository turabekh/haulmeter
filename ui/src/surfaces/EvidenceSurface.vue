<!-- AI-CONTEXT: Evidence locker (M5 / M3) — everything captured for a load in one
     place: the GPS-verified F4 timeline (arrival, notice), the cargo-condition
     PHOTOS with their guided prompt + capture time + verified hash, and the
     documents on file. Aggregates every evidence log tied to the stop, with a
     chain-integrity badge. Reached from the Load tab's Evidence card. Actual photo
     images are served from F6 at activation — here each is a verified, labeled
     entry (never a fake thumbnail). -->
<script setup>
import { ref, onMounted } from "vue";
import {
  ArrowLeft,
  ShieldCheck,
  MapPin,
  Camera,
  Send,
  FileText,
  ShieldAlert,
  FileDown,
  Share2,
  Clock,
} from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import {
  fetchEvidence,
  exportProtectionPack,
  shareProtectionPack,
  mediaUrl,
} from "../core/api.js";
import { useDriverState } from "../core/state.js";
import BottomSheet from "../core/components/BottomSheet.vue";
import Spinner from "../core/components/Spinner.vue";

const route = useRoute();
const { isDriving } = useDriverState();
const sharing = ref(false);
const recipient = ref("");
const busy = ref(false);
const queued = ref(false);
const shareUrl = ref(null);
const exportFailed = ref(false);

// AI-CONTEXT: this surface serves both pack kinds. Condition packs key on the STOP;
// an incident keys on the incident itself, which is why the id in the path means
// different things and the kind has to come with it rather than be guessed.
// AI-CONTEXT: this surface is a STOP's record, and its export asked for the cargo-
// condition pack — which 404s unless condition photos exist (§23 entry 71). So the
// document that argues a detention claim could not leave the phone, and the button
// swallowed the failure and did nothing at all.
// AI-CONTEXT: reads the route captured in SETUP, and that is the whole bug (§23 entry
// 72). This called `useRoute()` itself — inside a click handler, which is outside the
// setup context where the injection exists — so it returned undefined and the handler
// threw on `.query` before it ever reached the network. Both buttons on this card have
// therefore never worked: Export and Share both start by calling this. The `catch`
// swallowed it, so tapping either did nothing at all, forever.
const packKind = () => (route.query.kind === "incident" ? "incident" : "stop");

const router = useRouter();
const { t, has } = useI18n();

// acronyms stay English inside the locale catalogue, which is where §12.3 wants that
// decision — not derived here from the enum
function docLabel(type) {
  const key = `docs.type.${type}`;
  return has(key) ? t(key) : type.replace(/_/g, " ");
}
const data = ref(null);
const missing = ref(false);

/* AI-CONTEXT: the photographs are `<img src>` now, and this whole block is what that
 * removed.
 *
 * It used to fetch each one with an Authorization header, read a Blob, build an object
 * URL, and store it in a map that was CLONED on every arrival — so N photos did N
 * re-renders over a growing object. Worse, the fetches were `await`ed inside a `for`
 * loop: one full-size photograph at a time, in series, before the next even started.
 * And "thumbs" was a lie — every one of them was the original at camera resolution.
 *
 * The server hands over a signed, expiring URL per photo (`thumb_url`), so the browser
 * does the work it is good at: it fetches them in parallel on its own connection budget,
 * defers the ones below the fold via `loading="lazy"`, decodes off the main thread with
 * `decoding="async"`, and keeps them in its own HTTP cache instead of in JS memory. No
 * object URLs means nothing to revoke and nothing to leak. */
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
// AI-CONTEXT: label by WHAT HAPPENED, falling back to the record type (§23 entry 70).
//
// This read the RecordType alone, so a driver disputing detention was handed a pack
// whose timeline said "Event recorded 03:14" — the record's payload named the event
// and the API dropped it. Both halves are fixed: the API carries `event`, and a known
// event gets its own words. An unknown one still falls back rather than showing a raw
// key, because an evidence pack is read by brokers, not developers.
const evLabel = (e) => {
  const known = e.event ? t(`evidence.ev.${e.event}`) : null;
  if (known && known !== `evidence.ev.${e.event}`) return known;
  return t(EV[e.type]?.key ?? "claim.ev_system");
};
const evIcon = (type) => (EV[type] ?? EV.SYSTEM).icon;
const time = (iso) => (iso ? iso.slice(11, 16) : "");
// guided prompts have friendly names; fall back to the raw prompt
async function openExport() {
  busy.value = true;
  try {
    // AI-CONTEXT: NOT `window.open` (§23 entry 72).
    //
    // It sat behind two awaits — the fetch and the blob — and a browser only honours
    // a popup while it can still see the user's gesture. After an await that gesture
    // is gone, so `window.open` was blocked and returned null, silently: the driver
    // tapped Export and the app did nothing at all. An anchor with `download` needs
    // no popup permission, and carries the server's filename.
    const pack = await exportProtectionPack(packKind(), route.params.stopId);
    if (pack && typeof document !== "undefined") {
      const a = document.createElement("a");
      a.href = pack.url;
      a.download = pack.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // the blob is held only long enough for the download to start
      setTimeout(() => URL.revokeObjectURL(pack.url), 30000);
    }
  } catch {
    // §12.4: what happened and what to do. This used to swallow the error entirely,
    // so a driver tapped Export and the app did nothing whatsoever — the dead-control
    // pattern, on the one button that produces the artifact this product exists for.
    // Nothing is queued: the driver's own copy is not a promise to anyone, so a
    // failure is stated rather than deferred.
    exportFailed.value = true;
    setTimeout(() => (exportFailed.value = false), 6000);
  } finally {
    busy.value = false;
  }
}

async function doShare() {
  busy.value = true;
  try {
    const res = await shareProtectionPack(packKind(), route.params.stopId, recipient.value || null);
    // §15.1: a queued share is stated once, quietly, and its completion is silent
    queued.value = res?.queued === true;
    shareUrl.value = res?.url ?? null;
    sharing.value = false;
  } catch {
    sharing.value = false;
  } finally {
    busy.value = false;
  }
}

function photoLabel(prompt) {
  if (!prompt) return t("claim.ev_photo");
  const key = `cond.step.${prompt}`;
  return has(key) ? t(key) : prompt;
}
</script>

<template>
  <div class="ev">
    <header class="ev__head">
      <button class="back" type="button" :aria-label="t('nav.back')" @click="router.back()">
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
            <div class="photo__thumb" aria-hidden="true">
              <!-- `lazy` + `async` are the two attributes that were missing from every
                   image in this product. Below the fold on a long stop, a photograph is
                   never fetched at all until it is scrolled to. -->
              <img
                v-if="p.thumb_url"
                :src="mediaUrl(p.thumb_url)"
                class="photo__img"
                :alt="photoLabel(p.prompt)"
                loading="lazy"
                decoding="async"
                width="44"
                height="44"
              />
              <Camera v-else :size="22" :stroke-width="2" />
            </div>
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
            <span class="tl__label">{{ evLabel(e) }}</span>
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
            <!-- AI-CONTEXT: TRANSLATED, and not shouted. This rendered the raw enum
                 upper-cased — "RATE_CON", "MED_CARD" — which is ALL-CAPS text
                 (Forbidden #5), untranslated in all six locales, and beside a
                 `docs.type.*` catalogue that has carried proper labels since the
                 capture sheet was built. The same drift the Docs grid was caught by.
                 The status column went with the wallet: a BOL does not expire, so
                 flagging paperwork as "expiring" in flare was answering a question
                 this list does not ask. -->
            <span class="doc__name">{{ docLabel(d.doc_type) }}</span>
            <span class="doc__when">{{ (d.uploaded_at || "").slice(0, 10) }}</span>
          </li>
        </ul>
      </section>

      <p class="doc-note">{{ t("evidence.images_note") }}</p>
      <!-- AI-CONTEXT: FR2's "one-tap export" and FR4's "shareable pack", which have
           had a server since session 2 and no button at all.

           EXPORT is the driver's own copy and regenerates from the chain, so it is
           always current. SHARE pins what is sent and hands a counterparty one link
           (§17) — a different act, and the copy says so rather than offering two
           buttons that look alike.

           DRIVING (SM-3): neither renders. Sharing sends a document to a
           counterparty and Forbidden #11 bans interactive prompts at speed; export
           opens a viewer, which is the same problem. The evidence stays READABLE at
           speed — nothing above this point is hidden — but nothing here acts. -->
      <section v-if="!isDriving" class="card">
        <h2 class="card__title">{{ t("evidence.send") }}</h2>
        <button class="cta" type="button" :disabled="busy" @click="openExport">
          <Spinner v-if="busy" />
          <FileDown v-else :size="18" :stroke-width="2" aria-hidden="true" />
          {{ busy ? t("busy.preparing") : t("evidence.export") }}
        </button>
        <button class="cta cta--secondary" type="button" :disabled="busy" @click="sharing = true">
          <Share2 :size="18" :stroke-width="2" aria-hidden="true" />
          {{ t("evidence.share") }}
        </button>
        <p v-if="exportFailed" class="pending" role="alert">{{ t("evidence.export_failed") }}</p>
        <!-- §15.1: queued work carries a subtle pending glyph and completion is
             SILENT. No toast parade when the link finally goes out. -->
        <p v-if="queued" class="pending">
          <Clock :size="14" :stroke-width="2" aria-hidden="true" />
          {{ t("evidence.share_queued") }}
        </p>
        <p v-else-if="shareUrl" class="shared">
          <ShieldCheck :size="14" :stroke-width="2.5" aria-hidden="true" />
          {{ t("evidence.shared") }}
        </p>
      </section>
    </template>

    <BottomSheet :open="sharing" :title="t('evidence.share')" @close="sharing = false">
      <p class="sheet__lead">{{ t("evidence.share_lead") }}</p>
      <label class="field">
        <span class="field__label">{{ t("evidence.share_to") }}</span>
        <input v-model="recipient" class="field__input" type="email" inputmode="email" />
      </label>
      <p class="field__hint">{{ t("evidence.share_note") }}</p>
      <button class="cta" type="button" :disabled="busy" @click="doShare">
        <Spinner v-if="busy" />
        <Share2 v-else :size="18" :stroke-width="2" aria-hidden="true" />
        {{ busy ? t("busy.sending") : t("evidence.share_send") }}
      </button>
    </BottomSheet>
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
  /* §6.5 glove spec: 40 was under the floor. Found by the harness on its first run
     over this surface — the newest UI in the project and, until now, the least
     verified. */
  width: 48px;
  height: 48px;
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
  overflow: hidden;
}
.photo__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
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
.doc__when {
  margin-left: auto;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
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
  margin: 0;
}

/* AI-CONTEXT: these nine rules did not exist. The template names `.cta`,
   `.cta--secondary`, `.field*`, `.pending`, `.shared` and `.sheet__lead`, and this
   block styled none of them — and `scoped` means no other component's `.cta` could
   reach in. So Export PDF, Share, the recipient field and Create link all rendered
   as bare 24 dp text with no fill, no border and no target, on the surface that
   produces the pack a driver hands a broker.

   It survived because the harness only ever loaded this route at an id with no
   evidence, where `v-if="!isDriving"` sits inside a `<template>` that never renders
   — the measured state was not the state with the bug. Same shape as the Load tab.

   §8 grades: Primary filled `shield`, Secondary hairline outline, inputs 56 dp,
   labels above fields. Tokens only. */
.cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-2);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta:disabled {
  opacity: 0.6;
}
.cta--secondary {
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
}
.sheet__lead {
  margin: 0 0 var(--s-3);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.field {
  display: block;
  margin-bottom: var(--s-2);
}
.field__label {
  display: block;
  margin-bottom: var(--s-1);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.field__input {
  width: 100%;
  min-height: 56px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.field__hint {
  margin: 0 0 var(--s-3);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-caption-line);
}
.pending,
.shared {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: var(--s-2) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.shared {
  color: var(--ledger-500);
}
</style>
