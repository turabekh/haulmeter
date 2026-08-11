<!-- AI-CONTEXT: the driver's own bookings (M6, §23 entry 110). Until this screen there
     was NO way for a driver to see a booking they had paid for: `owner_bookings` had
     existed since M6 shipped, `bookSpot` wrote and nothing read back, and the
     "booking canceled" P0 deep-linked to /book/<spot> — the CHECKOUT flow — because
     no screen described a cancellation.

     Lives under More (§10.5), not as a sixth tab: NAV-1 fixes five, and a list of
     reservations is a records screen, which is what More is for. Owner-delegated
     navigation decision, logged as §23 entry 110.

     Cancelling ARMS then acts, exactly as the owner portal does, for the same reason:
     F7 has no un-refund, and a late cancellation returns half. The refund rule is the
     server's and is not restated here — the row reports what came back.

     §11.7: a booking that was refunded says so. "Canceled" and "canceled, $24 back"
     are different facts and a driver checking whether their money returned is asking
     the second one. -->
<script setup>
import { ref, onMounted } from "vue";
import { ArrowLeft } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { useDriverState } from "../core/state.js";
import { formatMoney } from "../core/meter.js";
import { fetchMyBookings, cancelBooking } from "../core/api.js";
import Spinner from "../core/components/Spinner.vue";

const router = useRouter();
const { t } = useI18n();
const { isDriving } = useDriverState();

const rows = ref([]);
const loaded = ref(false);
const arming = ref(null);

const LIVE = ["booked", "checked_in"];
const STATE_KEY = {
  booked: "bookings.st_booked",
  checked_in: "bookings.st_checked_in",
  checked_out: "bookings.st_checked_out",
  canceled: "bookings.st_canceled",
  refunded: "bookings.st_refunded",
};

async function load() {
  try {
    rows.value = await fetchMyBookings();
  } catch {
    rows.value = []; // offline or unauthenticated — the empty state invites the map
  }
  loaded.value = true;
}
onMounted(load);

const stateLabel = (s) => t(STATE_KEY[s] ?? "bookings.st_booked");
const isLive = (b) => LIVE.includes(b.state);
const nightOf = (iso) => (iso || "").slice(0, 10);

// the arm/confirm pair means the SECOND tap is the one that moves money, and it had no
// in-flight state — so the confirm tap looked identical to the arm tap that preceded it.
const cancelling = ref("");
async function onCancel(booking) {
  if (cancelling.value) return;
  if (arming.value !== booking.id) {
    arming.value = booking.id;
    return;
  }
  arming.value = null;
  cancelling.value = booking.id;
  try {
    await cancelBooking(booking.id);
  } catch {
    /* already canceled, or offline — the reload is the source of truth */
  }
  await load();
  cancelling.value = "";
}
</script>

<template>
  <div class="bookings">
    <header class="bookings__head">
      <button
        class="back"
        type="button"
        :aria-label="t('nav.back')"
        @click="router.back()"
      >
        <ArrowLeft :size="22" :stroke-width="2" aria-hidden="true" />
      </button>
      <h1 class="bookings__title">{{ t("bookings.title") }}</h1>
    </header>

    <p v-if="loaded && !rows.length" class="muted">{{ t("bookings.empty") }}</p>

    <ul class="rows">
      <li v-for="b in rows" :key="b.id" class="row">
        <div class="row__main">
          <span class="row__where">{{ b.property_name }}</span>
          <span class="row__when">{{ nightOf(b.start_at) }} · {{ b.nights }} {{ t("owner.nights") }}</span>
        </div>
        <div class="row__right">
          <span class="row__amount">{{ formatMoney(b.price_cents) }}</span>
          <span class="row__state">{{ stateLabel(b.state) }}</span>
        </div>
        <!-- §10.5 is a records screen; acting on a booking is still an action, so it
             withdraws at speed like every other one (§22.3). -->
        <button
          v-if="isLive(b) && !isDriving"
          class="row__cancel"
          type="button"
          :disabled="!!cancelling"
          @click="onCancel(b)"
        >
          <Spinner v-if="cancelling === b.id" />
          {{ cancelling === b.id
            ? t("busy.working")
            : arming === b.id ? t("bookings.cancel_confirm") : t("bookings.cancel") }}
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.bookings {
  padding: var(--s-4);
}
.bookings__head {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  margin-bottom: var(--s-4);
}
.back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--touch-min);
  height: var(--touch-min);
  border: 0;
  background: transparent;
  color: var(--text-1);
}
.bookings__title {
  margin: 0;
  font-size: var(--type-title-size);
  font-weight: 600;
  color: var(--text-1);
}
.muted {
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  padding: var(--s-4);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
}
.row__main {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}
.row__where {
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.row__when {
  font-size: var(--type-caption-size);
  color: var(--text-2);
}
.row__right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--s-1);
}
.row__amount {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-1);
}
.row__state {
  font-size: var(--type-caption-size);
  color: var(--text-2);
}
.row__cancel {
  flex-basis: 100%;
  min-height: var(--touch-min);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--flare-500);
  font-size: var(--type-label-size);
}
</style>
