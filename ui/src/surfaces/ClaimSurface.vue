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
import {
  fetchClaim,
  fetchMe,
  fetchShares,
  revokeShare,
  extendShare,
  sendDetentionNotice,
} from "../core/api.js";
import BrokerEmailField from "../core/components/BrokerEmailField.vue";
import Spinner from "../core/components/Spinner.vue";

const route = useRoute();
const router = useRouter();
const { t, has } = useI18n();
const claim = ref(null);
const missing = ref(false);
const me = ref(null); // F1: verified authority, shown on the invoice it backs

// extracted from onMounted so saving the broker's address can re-read: `notice_delivery`
// is DERIVED server-side from the linked message and the address on file, so the only
// honest way to show the new state is to ask again
async function reload() {
  try {
    claim.value = await fetchClaim(route.params.stopId);
  } catch {
    missing.value = true;
  }
}

onMounted(async () => {
  await reload();
  await loadShares();
  try {
    me.value = await fetchMe();
  } catch {
    me.value = null;
  }
});

// finding F5: the server derives this from the F8 message row — `sent` only when that
// row carries `sent_at`. An older payload without the field reads as "not sent", which
// is the honest fallback: never claim a delivery this client cannot see evidence of.
// AI-CONTEXT: the links this driver has handed out for this claim's evidence (D8).
// Extend and revoke have existed since sharing shipped and no screen could list what
// there was to extend or revoke, so a driver could send a broker a link to their own
// evidence and then have no way to see that they had — or to close it.
const shares = ref([]);

async function loadShares() {
  const logRef = claim.value?.evidence_log_ref;
  if (!logRef) return;
  try {
    shares.value = await fetchShares(logRef);
  } catch {
    shares.value = [];
  }
}

// AI-CONTEXT: which share is working, not merely that one is. These render per ROW, so
// a single boolean would spin every share's buttons at once — and revoking is the act a
// driver most needs to see land, because it takes a document away from a broker.
const shareBusy = ref("");
async function onRevoke(share) {
  if (shareBusy.value) return;
  shareBusy.value = `revoke:${share.share_id}`;
  try {
    await revokeShare(share.share_id);
    await loadShares();
  } catch {
    /* leave the list as it was; the next open re-reads */
  } finally {
    shareBusy.value = "";
  }
}

async function onExtend(share) {
  if (shareBusy.value) return;
  shareBusy.value = `extend:${share.share_id}`;
  try {
    await extendShare(share.share_id);
    await loadShares();
  } catch {
    /* as above */
  } finally {
    shareBusy.value = "";
  }
}

function shareDate(iso) {
  return iso ? iso.slice(0, 10) : "—";
}

const noticeDelivery = computed(() => claim.value?.notice_delivery ?? "not_sent");

/* AI-CONTEXT: the only place a delivered notice can be sent again, and the reason it
 * lives here rather than on the Load tab.
 *
 * §23's five-case rule refuses to re-send a DELIVERED notice — the broker has it and
 * `start_notice_sent_at` is the timestamp a detention dispute turns on — so the Load tab
 * correctly retires the rung once `notice_sent`. That left the product with no answer at
 * all to "the broker says they never got it", which is a real thing that happens.
 *
 * A forced re-send delivers a copy and leaves the anchor pointing at the FIRST real
 * delivery, so the pack still argues from when the broker was actually told. Two steps,
 * never one tap: the driver reads what they are about to do before the control that does
 * it appears (§22.1 step 4, the resolution entry 136 used for the packet discard). */
const resendOpen = ref(false);
const resending = ref(false);
const resentMsg = ref("");

async function onResend() {
  if (resending.value) return;
  resending.value = true;
  try {
    await sendDetentionNotice(route.params.stopId, true);
    resendOpen.value = false;
    resentMsg.value = t("claim.notice_resent");
    await reload();
  } catch {
    resentMsg.value = t("rec.send_failed");
  } finally {
    resending.value = false;
  }
}
const noticeDelivered = computed(() => noticeDelivery.value === "sent");
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
// AI-CONTEXT: WHAT HAPPENED, falling back to the record type — the same rule
// EvidenceSurface uses (§23 entry 70). This screen labelled by RecordType alone, so a
// driver reading the evidence behind their own claim saw "Action recorded" where the
// record itself names the event. `has()` guards it because the event vocabulary is
// dynamic and cannot be checked statically.
function evLabel(e) {
  const event = typeof e === "string" ? null : e?.event;
  const key = event ? `evidence.ev.${event}` : null;
  if (key && has(key)) return t(key);
  const type = typeof e === "string" ? e : e?.type;
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
        <!-- F1: the verified MC# this invoice is billed under -->
        <span v-if="owed && me && me.verified" class="authpill">
          MC# {{ me.mc_number }} · {{ t("authority.verified") }}
        </span>
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
            <span class="ev__label">{{ evLabel(e) }}</span>
            <span class="ev__time mono">{{ evTime(e.occurred_at) }}</span>
          </li>
          <!-- AI-CONTEXT: finding F5 — this was one bit, and delivery has five states.
               A driver whose notice bounced saw exactly what a driver who never tapped
               Send saw: "Broker not notified", with nothing to say the difference between
               "you have not done this yet" and "this was attempted and failed". The
               server derives the state from the F8 message row; this only renders it. -->
          <li class="ev">
            <Send :size="16" :stroke-width="2" class="ev__icon" :class="{ ok: noticeDelivered }" aria-hidden="true" />
            <span class="ev__label">{{ t(`notice.delivery.${noticeDelivery}`) }}</span>
          </li>
          <!-- AI-CONTEXT: the fix lives WHERE THE COMPLAINT IS. The line above says "No
               broker email — add one to notify", and a copy that names a remedy the driver
               then has to go and find somewhere else is only half a sentence. Saving
               re-reads the claim, so the delivery state re-derives and Send becomes
               available without leaving this screen. -->
          <!-- AI-CONTEXT: its OWN modifier, not `ev--fix`. That class means "the broker
               address is the problem and here is the field that fixes it", and a test
               asserts it is absent when the address is fine. Reusing it would have made
               the selector stop standing for its idea the moment this row arrived —
               HANDOFF-123's lesson, caught by that test.

               The second copy, and it is deliberately not one tap from the first. -->
          <li v-if="noticeDelivery === 'sent'" class="ev ev--resend">
            <template v-if="resentMsg">
              <span class="ev__label">{{ resentMsg }}</span>
            </template>
            <template v-else-if="resendOpen">
              <span class="ev__label">{{ t("send.again_lead") }}</span>
              <button class="ev__resend" type="button" :disabled="resending" @click="onResend">
                {{ resending ? t("busy.sending") : t("send.again_confirm") }}
              </button>
            </template>
            <button v-else class="ev__resend" type="button" @click="resendOpen = true">
              {{ t("send.again") }}
            </button>
          </li>

          <li v-if="noticeDelivery === 'no_email'" class="ev ev--fix">
            <BrokerEmailField
              variant="inline"
              :load-id="claim.load_id"
              :email="claim.counterparty_email"
              @saved="reload"
            />
          </li>
        </ul>
        <!-- AI-CONTEXT: label-then-figure, not "1 records". `t()` has no plural
             support, and the six launch locales do not share one plural rule — ru
             alone needs three forms — so a figure-first noun cannot be made correct
             here without ICU, which PRD §171 puts in F15's translation pipeline.
             Labelled figures are plural-free in every locale and match the count
             pattern the Docs archive and the photo checklist already use. -->
        <p class="records">
          {{ t("claim.records") }} <span class="records__n">{{ claim.record_count }}</span>
          · {{ t("claim.photos") }} <span class="records__n">{{ claim.artifact_count }}</span>
        </p>
      </section>

      <!-- D8: what has been handed out, and the two controls that were unreachable -->
      <section class="card">
        <h2 class="card__title">{{ t("claim.shares") }}</h2>
        <p v-if="!shares.length" class="muted">{{ t("claim.shares_none") }}</p>
        <ul v-else class="shares">
          <li v-for="s in shares" :key="s.share_id" class="share">
            <span class="share__state" :class="{ revoked: s.revoked }">
              {{ s.revoked ? t("claim.share_revoked") : t("claim.share_active") }}
            </span>
            <span class="share__meta">
              {{ t("claim.share_expires") }} {{ shareDate(s.expires_at) }}
              · {{ t("claim.share_opens") }} {{ s.opened_count }}
            </span>
            <span v-if="!s.revoked" class="share__actions">
              <button
                class="share__act"
                type="button"
                :disabled="!!shareBusy"
                @click="onExtend(s)"
              >
                <Spinner v-if="shareBusy === `extend:${s.share_id}`" />
                {{ shareBusy === `extend:${s.share_id}`
                  ? t("busy.saving")
                  : t("claim.share_extend") }}
              </button>
              <button
                class="share__act"
                type="button"
                :disabled="!!shareBusy"
                @click="onRevoke(s)"
              >
                <Spinner v-if="shareBusy === `revoke:${s.share_id}`" />
                {{ shareBusy === `revoke:${s.share_id}`
                  ? t("busy.working")
                  : t("claim.share_revoke") }}
              </button>
            </span>
          </li>
        </ul>
        <p v-if="shares.length" class="muted">{{ t("claim.share_opens_caveat") }}</p>
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
  /* AI-CONTEXT: audit U-04 — 40 dp, and the ONLY one of the nine `.back` buttons in
     `surfaces/` that was. The other eight are 48 or `--touch-min` already; this is the
     surface that had no harness state, which is the whole of U-04's argument. §6.5's
     floor is a gloved hand in a bouncing cab, and this is the screen every detention
     notification deep-links to. */
  width: var(--touch-min);
  height: var(--touch-min);
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
.authpill {
  margin-top: var(--s-2);
  padding: 2px var(--s-2);
  border-radius: var(--r-pill);
  background: var(--ledger-500);
  color: var(--ink-0);
  font-size: var(--type-caption-size);
  font-weight: 500;
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
.records__n {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-2);
}
.records {
  margin: var(--s-3) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.shares { list-style: none; margin: 0; padding: 0; }
.share {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-2) 0;
  border-bottom: 1px solid var(--line-1);
  font-size: var(--type-body-size);
}
.share__state { color: var(--ledger-500); }
.share__state.revoked { color: var(--text-3); }
.share__meta { color: var(--text-2); font-size: var(--type-label-size); }
.share__actions { margin-left: auto; display: flex; gap: var(--s-2); }
.share__act {
  min-height: 48px;
  padding: 0 var(--s-2);
  border: 0;
  background: none;
  color: var(--accent-500);
  font-size: var(--type-label-size);
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
