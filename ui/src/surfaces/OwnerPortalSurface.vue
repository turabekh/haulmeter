<!-- AI-CONTEXT: Property-Owner portal (M6-FR5, the supply side) — the third and
     last web-first §18 portal: desktop-first, comfortable layout, 1200 dp cap,
     shares ui/core tokens, NOT a driver-app screen (route meta.portal widens the
     frame, no tab chrome; login required). A parking-property owner's view of
     their listings + spots, their bookings, and the accrued payable the platform
     owes them (F7 owner_payable). Now READ-WRITE: create a listing, add/pause a
     spot, re-price it (M6-FR1) — writes hit /owner/* and reload. Payout SETTLEMENT
     is the deferred Stripe/Connect seam. Money is Mono/tabular (T-2). Falls back
     to a read-only fixture demo when unauthenticated/offline. -->
<script setup>
import { ref, reactive, onMounted } from "vue";
import { Building2, BadgeCheck, Plus } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { formatMoney } from "../core/meter.js";
import {
  fetchOwnerDashboard,
  createOwnerProperty,
  addOwnerSpot,
  updateOwnerSpot,
  cancelBooking,
} from "../core/api.js";
import { SAMPLE_OWNER } from "../core/fixtures.js";

const { t } = useI18n();
const board = ref(SAMPLE_OWNER);
const demo = ref(false);
const newProp = reactive({ name: "", lat: "", lon: "" });
const spotDrafts = reactive({}); // property_id -> { label, price }
// AI-CONTEXT: cancelling ARMS before it acts (§23 entry 108). Pausing a spot next to
// it is one tap because pausing is reversible; a cancellation refunds money and pushes
// a P0 to a driver who has planned their night around the spot, and F7 has no un-refund.
// This is a behaviour on the existing `.pause` button, not a new component pattern —
// §22 forbids inventing one, and an irreversible action behind a single click on a
// desktop table row is how an owner destroys a booking with a mis-click.
const arming = ref(null); // booking id awaiting its confirming second click
const ACTIVE_BOOKING_STATES = ["booked", "checked_in"];

const STATE_KEY = {
  booked: "owner.st_booked",
  checked_in: "owner.st_checked_in",
  checked_out: "owner.st_checked_out",
  refunded: "owner.st_refunded",
  canceled: "owner.st_canceled",
};
const stateLabel = (s) => t(STATE_KEY[s] ?? "owner.status");

async function reload() {
  board.value = await fetchOwnerDashboard();
}

function isActive(booking) {
  return ACTIVE_BOOKING_STATES.includes(booking.state);
}

async function onCancel(booking) {
  if (arming.value !== booking.id) {
    arming.value = booking.id; // first click arms, and only this one
    return;
  }
  arming.value = null;
  try {
    await cancelBooking(booking.id);
  } catch {
    /* already canceled, or offline — the reload below is the source of truth */
  }
  try {
    await reload();
  } catch {
    /* leave the table as it is rather than blanking it */
  }
}

async function init() {
  try {
    await reload();
  } catch {
    board.value = SAMPLE_OWNER; // unauthenticated / offline demo (read-only)
    demo.value = true;
  }
}
onMounted(init);

function draftFor(pid) {
  if (!spotDrafts[pid]) spotDrafts[pid] = { label: "", price: "" };
  return spotDrafts[pid];
}

async function addProperty() {
  if (!newProp.name.trim()) return;
  await createOwnerProperty(newProp.name.trim(), Number(newProp.lat) || 0, Number(newProp.lon) || 0);
  newProp.name = newProp.lat = newProp.lon = "";
  await reload();
}

async function addSpot(pid) {
  const d = draftFor(pid);
  const cents = Math.round(Number(d.price) * 100);
  if (!d.label.trim() || !cents) return;
  await addOwnerSpot(pid, d.label.trim(), cents);
  spotDrafts[pid] = { label: "", price: "" };
  await reload();
}

async function reprice(spot, dollars) {
  const cents = Math.round(Number(dollars) * 100);
  if (!cents || cents === spot.price_cents_per_night) return;
  await updateOwnerSpot(spot.id, { price_cents_per_night: cents });
  await reload();
}

async function togglePause(spot) {
  await updateOwnerSpot(spot.id, { active: !spot.active });
  await reload();
}
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

    <p v-if="demo" class="demo">{{ t("owner.demo") }}</p>

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
            <li v-for="s in p.spots" :key="s.id || s.label" class="spot" :class="{ 'spot--off': !s.active }">
              <span class="spot__label">{{ s.label }}</span>
              <span class="spot__money">
                <span class="spot__cur">$</span>
                <input
                  v-if="!demo"
                  class="spot__price-in"
                  type="number"
                  step="0.01"
                  min="0"
                  :value="(s.price_cents_per_night / 100).toFixed(2)"
                  :aria-label="t('owner.per_night')"
                  @change="reprice(s, $event.target.value)"
                />
                <span v-else class="spot__price">{{ (s.price_cents_per_night / 100).toFixed(2) }}</span>
                <span class="spot__per">{{ t("owner.per_night") }}</span>
              </span>
              <button v-if="!demo" class="pause" type="button" @click="togglePause(s)">
                {{ s.active ? t("owner.pause") : t("owner.resume") }}
              </button>
              <span v-else class="spot__state">{{ s.active ? t("owner.active") : t("owner.paused") }}</span>
            </li>
          </ul>

          <form v-if="!demo" class="addspot" @submit.prevent="addSpot(p.id)">
            <input v-model="draftFor(p.id).label" class="in in--label" type="text" :placeholder="t('owner.spot_label')" />
            <input v-model="draftFor(p.id).price" class="in in--price" type="number" step="0.01" min="0" :placeholder="t('owner.price')" />
            <button class="add add--sm" type="submit">
              <Plus :size="14" :stroke-width="2" aria-hidden="true" /> {{ t("owner.add_spot") }}
            </button>
          </form>
        </li>
      </ul>

      <form v-if="!demo" class="addprop" @submit.prevent="addProperty">
        <input v-model="newProp.name" class="in in--name" type="text" :placeholder="t('owner.prop_name')" />
        <input v-model="newProp.lat" class="in in--geo" type="number" step="any" :placeholder="t('owner.lat')" />
        <input v-model="newProp.lon" class="in in--geo" type="number" step="any" :placeholder="t('owner.lon')" />
        <button class="add" type="submit">
          <Plus :size="16" :stroke-width="2" aria-hidden="true" /> {{ t("owner.add_property") }}
        </button>
      </form>
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
            <th v-if="!demo">{{ t("owner.cancel") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in board.bookings" :key="b.id">
            <td>{{ b.nights }}</td>
            <td class="num">{{ formatMoney(b.price_cents) }}</td>
            <td class="num ledger">{{ formatMoney(b.owner_payout_cents) }}</td>
            <td>{{ stateLabel(b.state) }}</td>
            <td v-if="!demo">
              <button
                v-if="isActive(b)"
                class="pause"
                type="button"
                @click="onCancel(b)"
              >
                {{ arming === b.id ? t("owner.cancel_confirm") : t("owner.cancel") }}
              </button>
            </td>
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
.demo {
  margin: 0 0 var(--s-4);
  padding: var(--s-2) var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
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
  margin: 0 0 var(--s-3);
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
.spot__money {
  display: flex;
  align-items: baseline;
  gap: 2px;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.spot__cur {
  color: var(--text-3);
}
.spot__price-in {
  width: 84px;
  min-height: 40px;
  padding: 0 var(--s-2);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-1);
  color: var(--text-1);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-body-size);
}
.spot__per {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.spot__state {
  margin-left: auto;
  font-size: var(--type-caption-size);
  color: var(--text-2);
}
.pause {
  margin-left: auto;
  min-height: 40px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--text-1);
  font-size: var(--type-label-size);
}
.addspot,
.addprop {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  align-items: center;
}
.addspot {
  padding: var(--s-3) var(--s-4);
  border-top: 1px solid var(--line-1);
  background: var(--ink-2, transparent);
}
.addprop {
  margin-top: var(--s-2);
}
.in {
  min-height: 44px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.in--label {
  width: 96px;
}
.in--price {
  width: 96px;
  font-family: var(--font-mono);
}
.in--name {
  flex: 1 1 200px;
}
.in--geo {
  width: 120px;
  font-family: var(--font-mono);
}
.add {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  min-height: 44px;
  padding: 0 var(--s-4);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.add--sm {
  min-height: 40px;
  padding: 0 var(--s-3);
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
