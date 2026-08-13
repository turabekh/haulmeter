<!-- AI-CONTEXT: a finished load's record, READ before it is downloaded or sent
     (owner request, 2026-08-11 — §23 entry 137).

     Past loads offered a driver exactly two things: open ONE stop's evidence, or
     "Export whole load" — a PDF download, blind. So the only way to see what the
     document held was to put it on the phone first, and there was no way to send it to
     anybody at all. That second gap became load-bearing the moment a driver could
     DISCARD a stop packet (entry 136): declining paperwork is only safe if there is a
     way back to it.

     THE SEND NEEDED NO NEW API. `/protection/load/{id}/share` has accepted
     `kind="load"` since the whole-route pack was written, and the only caller in the
     product passes "stop" — so the whole-load pack could always be emailed and nothing
     ever called it. Eighth built-and-inert mechanism (HANDOFF-122's tally).

     WHY A SUMMARY AND NOT THE PDF (owner's choice of three). A driver who is not
     comfortable with phones cannot audit a pinch-zoomed multi-page PDF at 360 dp. This
     says the same thing in the words they use — how many photos, which paperwork, was
     the GPS trail recorded, what was claimed — and shows the actual captured images. It
     reads from the same source `load_pack` composes from, so what is on this screen is
     what the broker receives; the API test asserts the two counts against each other.

     SEND IS THE PRIMARY (owner's choice). It is the recovery path for a discarded or
     never-sent packet, and it is the action that gets the driver paid. Download is
     Secondary. §8: one Primary per screen. -->
<script setup>
import { ref, computed, onMounted } from "vue";
import { ArrowLeft, Check, Camera, MapPin, FileText, ShieldAlert, ChevronRight } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import {
  fetchLoadRecord,
  exportProtectionPack,
  shareProtectionPack,
  online,
  mediaUrl,
} from "../core/api.js";
import { LoadState, Failure, failureOf } from "../core/load-state.js";
import { formatMoney } from "../core/meter.js";
import BottomSheet from "../core/components/BottomSheet.vue";
import Spinner from "../core/components/Spinner.vue";
import SkeletonCard from "../core/components/SkeletonCard.vue";

const route = useRoute();
const router = useRouter();
const { t, has } = useI18n();
const { isDriving } = useDriverState();

const state = ref(LoadState.LOADING);
const failure = ref(null);
const data = ref(null);

const loadId = computed(() => route.params.loadId);
const stops = computed(() => data.value?.stops ?? []);
// §15.3's empty: a load that captured nothing has no record to send, and saying that
// plainly is better than an "empty" screen with two live buttons on it.
const hasRecord = computed(
  () => !!data.value && (data.value.photo_count > 0 || data.value.gps_events > 0
    || (data.value.document_types || []).length > 0),
);

// AI-CONTEXT: the SAME guarded lookup EvidenceSurface uses (`cond.step.*`, falling
// back to the raw prompt). Written first as `cond.step`'s non-existent twin
// `cond.prompt.*`, which `t()` throws on under test — and because an alt attribute is
// evaluated during render, that threw the WHOLE render function, so the send sheet
// silently never opened. A dynamic key family cannot be checked statically; `has()` is
// what makes it safe, which is why this borrows rather than re-derives.
function photoLabel(prompt) {
  if (!prompt) return t("claim.ev_photo");
  const key = `cond.step.${prompt}`;
  return has(key) ? t(key) : prompt;
}
function docLabel(type) {
  const key = `docs.type.${type}`;
  return has(key) ? t(key) : type.replace(/_/g, " ");
}
const routeLabel = computed(() =>
  data.value?.destination_name
    ? `${data.value.origin_name} → ${data.value.destination_name}`
    : data.value?.origin_name || t("rec.title"),
);
const stopLabel = (s) =>
  `${s.sequence + 1} · ${t(`load.stop.${s.stop_type}`)} · ${s.facility_name ?? ""}`;

onMounted(async () => {
  state.value = LoadState.LOADING;
  try {
    data.value = await fetchLoadRecord(loadId.value);
    state.value = LoadState.LOADED;
  } catch (e) {
    failure.value = failureOf(e);
    state.value = LoadState.FAILED;
    return;
  }
  /* AI-CONTEXT: the image loop that was here is gone, and this was the worst instance of
   * it in the product — a NESTED sequential fetch, stops × photos. A four-stop route with
   * six photographs each fetched twenty-four FULL-SIZE images one after another before
   * the last thumbnail appeared, each one cloning the whole `thumbs` map on arrival.
   *
   * The record now arrives with a signed `thumb_url` per photo, and the browser fetches
   * them in parallel, defers everything below the fold, and caches them itself. The
   * original comment's point still holds and holds better: a photograph that will not
   * load cannot stop the rest of the record rendering, because the record no longer waits
   * for any of them. */
});

// --- send ---
const sending = ref(false);
const sendOpen = ref(false);
const recipient = ref("");
const sendError = ref("");
const sentMsg = ref("");
function openSend() {
  recipient.value = data.value?.counterparty_email || "";
  sendError.value = "";
  sendOpen.value = true;
}
async function onSend() {
  if (sending.value) return;
  sending.value = true;
  sendError.value = "";
  try {
    const res = await shareProtectionPack("load", loadId.value, recipient.value.trim() || null);
    sendOpen.value = false;
    // §15.1: a queued share is not a delivery, and saying "Sent" over one would be the
    // F-03 defect — a row claiming a delivery it never got — rebuilt on a screen.
    sentMsg.value = res && res.queued ? t("rec.send_offline") : t("rec.sent");
    setTimeout(() => (sentMsg.value = ""), 6000);
  } catch {
    sendError.value = online.value ? t("rec.send_failed") : t("rec.send_offline");
  } finally {
    sending.value = false;
  }
}

// --- download ---
const downloading = ref(false);
const downloadError = ref("");
async function onDownload() {
  if (downloading.value) return;
  downloading.value = true;
  downloadError.value = "";
  try {
    const pack = await exportProtectionPack("load", loadId.value);
    if (pack && typeof document !== "undefined") {
      const a = document.createElement("a");
      a.href = pack.url;
      a.download = pack.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(pack.url), 30000);
    }
  } catch {
    // §12.4, and never an empty catch: a control that runs, fails and leaves the screen
    // exactly as it was is the dead-control pattern §23 entry 72 records.
    downloadError.value = t("rec.download_failed");
    setTimeout(() => (downloadError.value = ""), 6000);
  } finally {
    downloading.value = false;
  }
}
</script>

<template>
  <div class="rec">
    <header class="rec__head">
      <button class="rec__back" type="button" :aria-label="t('nav.back')" @click="router.back()">
        <ArrowLeft :size="24" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="rec__title">{{ state === LoadState.LOADED ? routeLabel : t("rec.title") }}</h1>
    </header>

    <!-- §8/§15.2: the skeleton mirrors the real layout rather than spinning -->
    <SkeletonCard v-if="state === LoadState.LOADING" :count="2" />

    <!-- §15.4: inline, specific, and it distinguishes a dead zone from a dead server -->
    <p v-else-if="state === LoadState.FAILED" class="rec__failed" role="status">
      {{ failure === Failure.OFFLINE ? t("system.load_offline") : t("rec.failed") }}
    </p>

    <!-- §15.3: one sentence of what happened. No actions, because there is nothing to
         act on — offering Send here would be a button that can only fail. -->
    <p v-else-if="!hasRecord" class="rec__empty">{{ t("rec.empty") }}</p>

    <template v-else>
      <p class="rec__sub">
        <template v-if="data.reference_number">{{ t("packet.ref", { ref: data.reference_number }) }} · </template
        >{{ data.created_at.slice(0, 10) }}
      </p>

      <!-- the answer to "what am I about to send", in one card, before any action -->
      <section class="card">
        <h2 class="card__title">{{ t("rec.whats_in") }}</h2>
        <ul class="whats">
          <li class="whats__row">
            <Camera :size="20" :stroke-width="2" :class="{ ok: data.photo_count }" aria-hidden="true" />
            {{ data.photo_count ? t("rec.photos", { n: data.photo_count }) : t("rec.photos_none") }}
          </li>
          <li class="whats__row">
            <FileText
              :size="20"
              :stroke-width="2"
              :class="{ ok: data.document_types.length }"
              aria-hidden="true"
            />
            {{ data.document_types.length
              ? data.document_types.map(docLabel).join(" · ")
              : t("rec.docs_none") }}
          </li>
          <li class="whats__row">
            <MapPin :size="20" :stroke-width="2" :class="{ ok: data.gps_events }" aria-hidden="true" />
            {{ data.gps_events ? t("rec.gps") : t("rec.gps_none") }}
          </li>
          <li class="whats__row">
            <Check :size="20" :stroke-width="2" :class="{ ok: data.detention_cents }" aria-hidden="true" />
            {{ data.detention_cents
              ? t("rec.claimed", { money: formatMoney(data.detention_cents) })
              : t("rec.claimed_none") }}
          </li>
        </ul>
      </section>

      <!-- §11.7: a pack that fails its own verification cannot be shared (the evidence-
           integrity session put that gate in `share_pack`), so the driver learns it HERE
           rather than from a refused tap on a Primary. -->
      <p v-if="!data.chain_valid" class="rec__broken" role="status">
        <ShieldAlert :size="18" :stroke-width="2" aria-hidden="true" />
        {{ t("rec.broken") }}
      </p>

      <!-- each dock, with what was actually captured there. The thumbnails are the
           point: "6 photos" is a number, and these are the photographs. -->
      <section v-for="s in stops" :key="s.stop_id" class="stop">
        <h2 class="stop__name">{{ stopLabel(s) }}</h2>
        <ul v-if="s.photos.length" class="shots">
          <li v-for="p in s.photos" :key="p.artifact_id" class="shots__item">
            <img
              v-if="p.thumb_url"
              :src="mediaUrl(p.thumb_url)"
              class="shots__img"
              :alt="photoLabel(p.prompt)"
              loading="lazy"
              decoding="async"
              width="72"
              height="72"
            />
            <span v-else class="shots__pending" aria-hidden="true"></span>
          </li>
        </ul>
        <p class="stop__meta">
          {{ s.photos.length ? t("rec.photos", { n: s.photos.length }) : t("rec.photos_none") }}
          <template v-if="s.document_types.length">
            · {{ s.document_types.map(docLabel).join(" · ") }}</template>
          <template v-if="s.detention_cents">
            · {{ formatMoney(s.detention_cents) }}</template>
        </p>
        <button class="stop__open" type="button" @click="router.push(`/load/${s.stop_id}/evidence`)">
          {{ t("rec.open_stop") }}
          <ChevronRight :size="18" :stroke-width="2" aria-hidden="true" />
        </button>
      </section>

      <p v-if="sentMsg" class="rec__sent" role="status">{{ sentMsg }}</p>
      <p v-if="downloadError" class="rec__failed" role="status">{{ downloadError }}</p>

      <!-- SM-3 / Forbidden #11: sending a document to a broker under the driver's name
           is the least appropriate decision to put in front of someone at 65 mph. The
           record stays READABLE at speed; only the acting controls withdraw. -->
      <p v-if="isDriving" class="rec__driving">{{ t("rec.driving") }}</p>
      <template v-else>
        <button class="cta" type="button" :disabled="!data.chain_valid" @click="openSend">
          {{ t("rec.send") }}
        </button>
        <button class="cta cta--outline" type="button" :disabled="downloading" @click="onDownload">
          <Spinner v-if="downloading" />
          {{ downloading ? t("busy.preparing") : t("rec.download") }}
        </button>
      </template>

      <BottomSheet :open="sendOpen && !isDriving" :title="t('rec.send_title')" @close="sendOpen = false">
        <div class="send">
          <p class="send__body">{{ t("rec.send_body") }}</p>
          <label class="send__to">
            <span class="send__label">{{ t("rec.send_to") }}</span>
            <input
              v-model="recipient"
              class="send__input"
              type="email"
              inputmode="email"
              :placeholder="t('packet.no_recipient')"
            />
          </label>
          <!-- HANDOFF-122 §3: nothing in this product had ever written `contact_email`,
               so on most real loads this is empty. Say what to do, before the tap. -->
          <p v-if="!recipient.trim()" class="send__hint">{{ t("rec.no_email") }}</p>
          <p v-if="sendError" class="send__error" role="status">{{ sendError }}</p>
          <button
            class="cta"
            type="button"
            :disabled="sending || !recipient.trim()"
            @click="onSend"
          >
            <Spinner v-if="sending" />
            {{ sending ? t("busy.sending") : t("rec.send_go") }}
          </button>
        </div>
      </BottomSheet>
    </template>
  </div>
</template>

<style scoped>
.rec {
  padding: var(--s-4);
}
.rec__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-bottom: var(--s-3);
}
/* §6.5 glove spec: a back control is a real target, not the glyph's own box */
.rec__back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 48px;
  min-height: 48px;
  margin-left: calc(var(--s-2) * -1);
  background: transparent;
  color: var(--text-1);
}
.rec__title {
  margin: 0;
  flex: 1 1 auto;
  min-width: 0;
  font-size: var(--type-title-size);
  font-weight: var(--type-title-weight);
  color: var(--text-1);
}
.rec__sub {
  margin: calc(var(--s-2) * -1) 0 var(--s-3);
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.rec__failed,
.rec__empty {
  margin: 0 0 var(--s-3);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.rec__sent {
  margin: 0 0 var(--s-3);
  padding: var(--s-2) var(--s-3);
  border-radius: var(--r-control);
  background: var(--ink-1);
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
/* `flare` because this one blocks the Primary: §16 gives it colour AND icon AND label */
.rec__broken {
  display: flex;
  align-items: flex-start;
  gap: var(--s-2);
  margin: 0 0 var(--s-3);
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-left: 2px solid var(--flare-500);
  border-radius: var(--r-card);
  background: var(--ink-1);
  color: var(--flare-500);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.rec__driving {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
  text-align: center;
}
.card {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
  margin-bottom: var(--s-3);
}
.card__title {
  margin: 0 0 var(--s-3);
  font-size: var(--type-label-size);
  color: var(--text-2);
  font-weight: 500;
}
.whats {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.whats__row {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  color: var(--text-1);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.ok {
  color: var(--ledger-500);
}
.stop {
  margin-bottom: var(--s-3);
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.stop__name {
  margin: 0 0 var(--s-2);
  font-size: var(--type-body-size);
  font-weight: 500;
  color: var(--text-1);
}
.stop__meta {
  margin: var(--s-2) 0 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
/* the photographs, in a wrapping row. LAW 0: a fixed grid at 360 dp would either clip
   or force a horizontal scroll, and Forbidden #5 rules out the second. */
.shots {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}
.shots__item {
  width: 72px;
  height: 72px;
  border-radius: var(--r-control);
  overflow: hidden;
  background: var(--ink-2, var(--line-1));
}
.shots__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
/* a photo whose bytes have not arrived: the SHAPE is honest about what is coming,
   which is §15.2's skeleton rule applied to one tile rather than a spinner per image */
.shots__pending {
  display: block;
  width: 100%;
  height: 100%;
  background: var(--line-1);
}
.stop__open {
  display: flex;
  align-items: center;
  gap: var(--s-1);
  min-height: 48px;
  margin-top: var(--s-1);
  padding: 0;
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
  font-weight: 500;
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
.cta--outline {
  margin-top: var(--s-2);
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--text-1);
}
.send {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.send__body,
.send__hint {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.send__to {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.send__label {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.send__input {
  min-height: 56px;
  min-width: 0;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.send__error {
  margin: 0;
  color: var(--flare-500);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
</style>
