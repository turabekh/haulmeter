<!-- AI-CONTEXT: A1 requirement 5 — "The driver reviews before it sends. Nothing leaves
     silently. A packet the driver did not see is a document they cannot vouch for."

     A queue that said "1 packet" and offered Send would satisfy the letter of that and
     none of its point. §11.7 — a figure never travels without what produced it — applies
     harder to a document than to a number, because the driver is vouching for this under
     their own name to the person who pays them. So the recipient, the load reference and
     the stop are all on the row, above the action.

     NAV: a full-screen push, not a sheet. §NAV-3 reserves those for linear flows and
     names CLAIM REVIEW as the example; this is the same shape and reached the same way,
     by a NAV-5 cross-link. No new navigation structure (§22.2).

     DRIVING: `withdraws`. Forbidden #11 bans interactive prompts at speed, and this is a
     decision that sends a document to a broker — the least appropriate thing to put in
     front of someone at 65 mph. The packet waits; that is what the queue is for. -->
<script setup>
import { ref, onMounted } from "vue";
import { FileText } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { fetchStopPackets, sendStopPacket } from "../core/api.js";
import Spinner from "../core/components/Spinner.vue";

const { t } = useI18n();
// SM-3 / Forbidden #11: sending a document to a broker under the driver's name is the
// least appropriate decision to put in front of someone at 65 mph. The queue still shows
// WHAT is waiting — that is information, and withdrawing it would just hide the backlog —
// but the action withdraws until they stop. The packet is durable; it can wait.
const { isDriving } = useDriverState();
const packets = ref([]);
const loading = ref(true);
const failed = ref(null);

async function load() {
  loading.value = true;
  try {
    packets.value = await fetchStopPackets();
  } catch {
    packets.value = [];
  } finally {
    loading.value = false;
  }
}

// AI-CONTEXT: WHICH packet is going, not merely "something is". This is a LIST, so a
// single boolean would spin every row's button at once and say the wrong thing about
// four packets to tell the truth about one.
//
// It is also the guard this route never had: `send` had no in-flight state at all, so a
// driver on a bad connection could tap a row twice and post the same packet twice. The
// server is idempotent, which is why this was survivable rather than harmless.
const sendingId = ref(null);
async function send(packet) {
  if (sendingId.value) return;
  sendingId.value = packet.id;
  failed.value = null;
  try {
    await sendStopPacket(packet.id);
    packets.value = packets.value.filter((p) => p.id !== packet.id);
  } catch {
    // §12.4: what happened and what to do. A tap that appears to work and does nothing
    // is the worse outcome — the driver would believe their paperwork went out.
    failed.value = packet.id;
  } finally {
    sendingId.value = null;
  }
}

onMounted(load);
</script>

<template>
  <section class="packets">
    <h1 class="packets__title">{{ t("packet.title") }}</h1>
    <p class="packets__note">{{ t("packet.note") }}</p>

    <p v-if="loading" class="packets__empty">{{ t("packet.loading") }}</p>
    <p v-else-if="!packets.length" class="packets__empty">{{ t("packet.empty") }}</p>

    <article v-for="p in packets" :key="p.id" class="packet">
      <h2 class="packet__ref">
        <FileText :size="16" :stroke-width="2" aria-hidden="true" />
        {{ p.reference || t("packet.no_reference") }}
      </h2>
      <p class="packet__where">{{ p.facility_name }}</p>
      <!-- WHO receives it. The driver is vouching for this document to that address. -->
      <p class="packet__to">
        {{ t("packet.to") }} {{ p.counterparty_name || t("packet.unknown_recipient") }}
        <span class="packet__email">{{ p.recipient || t("packet.no_recipient") }}</span>
      </p>
      <p v-if="failed === p.id" class="packet__failed">{{ t("packet.send_failed") }}</p>
      <button
        v-if="!isDriving"
        class="cta packet__send"
        type="button"
        :disabled="sendingId === p.id"
        @click="send(p)"
      >
        <Spinner v-if="sendingId === p.id" />
        {{ sendingId === p.id ? t("busy.sending") : t("packet.send") }}
      </button>
      <p v-else class="packet__driving">{{ t("packet.driving") }}</p>
    </article>
  </section>
</template>

<style scoped>
.packets {
  padding: var(--s-3);
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.packets__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-title-size);
}
.packets__note,
.packets__empty {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.packet {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.packet__ref {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-title-size);
}
.packet__where,
.packet__to {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.packet__email {
  display: block;
  color: var(--text-3);
}
.packet__driving {
  margin: var(--s-2) 0 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.packet__failed {
  margin: 0;
  color: var(--flare-500);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.packet__send {
  min-height: 56px;
  margin-top: var(--s-2);
  border: 0;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
}
</style>
