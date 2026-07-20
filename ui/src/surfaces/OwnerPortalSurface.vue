<!-- AI-CONTEXT: Property-Owner portal (M6-FR5, the supply side) — the third and
     last web-first §18 portal: desktop-first, comfortable layout, 1200 dp cap,
     shares ui/core tokens, NOT a driver-app screen (route meta.portal widens the
     frame, no tab chrome; login required). A parking-property owner's view of
     their listings + spots, their bookings, and the accrued payable the platform
     owes them (F7 owner_payable). Payout SETTLEMENT is the deferred Stripe/Connect
     seam — this is the view, not the transfer. Money is Mono/tabular (T-2). Falls
     back to the fixture demo when unauthenticated/offline. -->
<script setup>
import { ref, onMounted } from "vue";
import { Building2, BadgeCheck } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { formatMoney } from "../core/meter.js";
import { fetchOwnerDashboard } from "../core/api.js";
import { SAMPLE_OWNER } from "../core/fixtures.js";

const { t } = useI18n();
const board = ref(SAMPLE_OWNER);
const demo = ref(false);

const STATE_KEY = {
  booked: "owner.st_booked",
  checked_in: "owner.st_checked_in",
  checked_out: "owner.st_checked_out",
  refunded: "owner.st_refunded",
  canceled: "owner.st_canceled",
};
const stateLabel = (s) => t(STATE_KEY[s] ?? "owner.status");

async function init() {
  try {
    board.value = await fetchOwnerDashboard();
  } catch {
    board.value = SAMPLE_OWNER; // unauthenticated / offline demo
    demo.value = true;
  }
}
onMounted(init);
</script>

<template>
  <div class="owner">
    <header class="owner__head">
      <h1 class="owner__title">{{ t("owner.title") }}</h1>
      <div class="payout">
        <span class="payout__label">{{ t("owner.payout") }}</span>
        <span class="payout__figure">{{ formatMoney(board.payout_cents) }}</span>
        <span class="payout__note">{{ t("owner.payout_note") }}</span>
      </div>
    </header>

    <section class="block">
      <h2 class="block__title">{{ t("owner.properties") }}</h2>
      <p v-if="!board.properties.length" class="muted">{{ t("owner.empty") }}</p>
      <ul v-else class="props">
        <li v-for="p in board.properties" :key="p.id" class="prop">
          <div class="prop__head">
            <Building2 :size="18" :stroke-width="2" class="prop__icon" aria-hidden="true" />
            <span class="prop__name">{{ p.name }}</span>
            <span v-if="p.vetted" class="badge">
              <BadgeCheck :size="14" :stroke-width="2" aria-hidden="true" /> {{ t("owner.vetted") }}
            </span>
            <span class="prop__count">{{ p.spots.length }} {{ t("owner.spots") }}</span>
          </div>
          <ul class="spots">
            <li v-for="s in p.spots" :key="s.label" class="spot" :class="{ 'spot--off': !s.active }">
              <span class="spot__label">{{ s.label }}</span>
              <span class="spot__price">{{ formatMoney(s.price_cents_per_night) }}{{ t("owner.per_night") }}</span>
              <span class="spot__state">{{ s.active ? t("owner.active") : t("owner.paused") }}</span>
            </li>
          </ul>
        </li>
      </ul>
    </section>

    <section class="block">
      <h2 class="block__title">{{ t("owner.bookings") }}</h2>
      <p v-if="!board.bookings.length" class="muted">{{ t("owner.no_bookings") }}</p>
      <table v-else class="ledger-table">
        <thead>
          <tr>
            <th>{{ t("owner.nights") }}</th>
            <th class="num">{{ t("owner.charged") }}</th>
            <th class="num">{{ t("owner.your_cut") }}</th>
            <th>{{ t("owner.status") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in board.bookings" :key="b.id">
            <td>{{ b.nights }}</td>
            <td class="num">{{ formatMoney(b.price_cents) }}</td>
            <td class="num ledger">{{ formatMoney(b.owner_payout_cents) }}</td>
            <td>{{ stateLabel(b.state) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.owner {
  padding: var(--s-5);
}
.owner__head {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  margin-bottom: var(--s-5);
}
@media (min-width: 720px) {
  .owner__head {
    flex-direction: row;
    align-items: flex-end;
    justify-content: space-between;
  }
}
.owner__title {
  margin: 0;
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
.payout {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  padding: var(--s-3) var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.payout__label {
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.payout__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-display-size);
  color: var(--shield-500);
}
.payout__note {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.block {
  margin-bottom: var(--s-5);
}
.block__title {
  margin: 0 0 var(--s-3);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.props {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.prop {
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
  overflow: hidden;
}
.prop__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-3) var(--s-4);
  border-bottom: 1px solid var(--line-1);
}
.prop__icon {
  color: var(--text-3);
  flex: none;
}
.prop__name {
  font-weight: var(--type-title-weight);
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--shield-500);
  font-size: var(--type-caption-size);
}
.prop__count {
  margin-left: auto;
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.spots {
  list-style: none;
  margin: 0;
  padding: 0;
}
.spot {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-2) var(--s-4);
  border-top: 1px solid var(--line-1);
}
.spot:first-child {
  border-top: none;
}
.spot--off {
  color: var(--text-3);
}
.spot__label {
  min-width: 40px;
  font-family: var(--font-mono);
}
.spot__price {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.spot__state {
  margin-left: auto;
  font-size: var(--type-caption-size);
  color: var(--text-2);
}
.ledger-table {
  width: 100%;
  border-collapse: collapse;
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  overflow: hidden;
}
.ledger-table th,
.ledger-table td {
  padding: var(--s-2) var(--s-3);
  text-align: left;
  border-bottom: 1px solid var(--line-1);
  font-size: var(--type-body-size);
}
.ledger-table th {
  color: var(--text-2);
  font-size: var(--type-label-size);
  font-weight: var(--type-label-weight);
}
.ledger-table tbody tr:last-child td {
  border-bottom: none;
}
.num {
  text-align: right;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.ledger {
  color: var(--shield-500);
}
.muted {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-body-size);
}
</style>
