<!-- AI-CONTEXT: More tab — the overflow/settings home. Holds the F1 account
     section (who's signed in + Log out) and the M10 points/reputation card
     (balance in Mono + contributor level). Calm and minimal (§15.3). Log out
     clears the session (api.js) and returns to the auth surface. -->
<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Check } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { useTheme } from "../core/theme.js";
import { email, logout, fetchPoints, fetchMe, verifyAuthority, saveEquipment, setFoodAlerts, fetchNotificationClasses } from "../core/api.js";
import SkeletonCard from "../core/components/SkeletonCard.vue";
import { LoadState, Failure, failureOf } from "../core/load-state.js";
import BottomSheet from "../core/components/BottomSheet.vue";
import InstallSheet from "../core/components/InstallSheet.vue";
import { installable, manualInstall, promptInstall } from "../core/install.js";
import LocalePicker from "../core/components/LocalePicker.vue";
import { mpgError, normalizeMpg, MIN_MPG, MAX_MPG } from "../core/truck.js";
import NotificationsSheet from "../core/components/NotificationsSheet.vue";
import { fetchNotifications, markNotificationRead } from "../core/api.js";
import Spinner from "../core/components/Spinner.vue";

const router = useRouter();
const { t } = useI18n();

// AI-CONTEXT: §23 entry 102 — F8's inbox, reached from the More list.
//
// §10.5 says More is "deliberately boring; a plain 64 dp row list. No cards, no
// promos, NO BADGES", so there is no unread count on this row and none on the tab:
// a number that follows a driver around is an interruption wearing a different hat,
// and §13's budget governs interruptions however they are dressed. The unread state
// lives INSIDE the sheet, where a driver who opened it has already asked.
const notifications = ref([]);
const notifOpen = ref(false);
const nowMs = ref(Date.now());

async function openNotifications() {
  notifOpen.value = true;
  try {
    notifications.value = (await fetchNotifications()).notifications;
  } catch {
    // offline: this surface is pure history, so an empty list plus the sheet's own
    // "nothing yet" is honest — there is no pending action to lose
    notifications.value = [];
  }
  nowMs.value = Date.now();
}

async function openNotification(n) {
  notifOpen.value = false;
  if (!n.read_at) {
    markNotificationRead(n.id).catch(() => {});
    n.read_at = new Date().toISOString();
  }
  // §13.5: land on the exact screen and state it describes, never a tab root
  if (n.deep_link) router.push(n.deep_link);
}
// iOS has no install API at all, so the sheet showing the Share gesture IS the path
// there rather than a fallback from one. Same branch as the strip's, deliberately —
// one module decides which platform can be prompted, and both callers ask it.
const installSheet = ref(false);
async function onInstall() {
  if (manualInstall.value) {
    installSheet.value = true;
    return;
  }
  await promptInstall();
}

const { mode, setMode, modes } = useTheme();
// AI-CONTEXT: §23 entry 131 — this was `ref(SAMPLE_POINTS)`, so More opened showing a
// balance and a loyalty LEVEL the driver had not earned. A points balance is a promise
// about what the platform owes them.
const points = ref(null);
const pointsState = ref(LoadState.LOADING);
const pointsFailure = ref(null);

// F1: operating-authority verification (FMCSA). Section only appears when the
// F13 flag is on; verified state is plain text here (§10 — no badges on More),
// the colored status pill lives where credibility is consumed (Claim / Money).
const me = ref(null);
const authForm = reactive({ number: "", busy: false, error: "" });

async function loadMe() {
  try {
    me.value = await fetchMe();
    equip.plate_state = me.value.plate_state || "";
    equip.plate_number = me.value.plate_number || "";
    equip.unit_number = me.value.unit_number || "";
    equip.vin = me.value.vin || "";
    // "" when the driver has never reported one, which is what the field must show —
    // prefilling 6.0 would put the app's own assumption in a box labelled as theirs
    equip.mpg = me.value.mpg == null ? "" : String(me.value.mpg);
  } catch {
    me.value = null; // unauthenticated / offline — hide the section
  }
}

async function submitVerify() {
  authForm.error = "";
  if (!authForm.number.trim()) return;
  authForm.busy = true;
  try {
    me.value = { ...me.value, ...(await verifyAuthority({ mcNumber: authForm.number.trim() })) };
    if (!me.value.verified) authForm.error = t("authority.error");
    else authForm.number = "";
  } catch (e) {
    authForm.error = e.message === "verification_disabled" ? t("authority.disabled") : t("authority.error");
  } finally {
    authForm.busy = false;
  }
}

// E2: self-reported equipment. NO verification is offered or implied here — the
// only verified thing on this screen is FMCSA authority, and conflating the two
// would be exactly the overclaim §11.7 forbids.
const equip = reactive({
  plate_state: "",
  plate_number: "",
  unit_number: "",
  vin: "",
  mpg: "",
  busy: false,
  error: "",
  saved: false,
});
// the same rule the server applies, so the driver reads "between 3 and 12" in their own
// language rather than a 422 carrying a sentence of English out of a Python exception
const mpgFieldError = computed(() => mpgError(equip.mpg));

async function submitEquipment() {
  equip.error = "";
  equip.saved = false;
  equip.busy = true;
  try {
    const saved = await saveEquipment({
      plateState: equip.plate_state,
      plateNumber: equip.plate_number,
      unitNumber: equip.unit_number,
      vin: equip.vin,
      mpg: normalizeMpg(equip.mpg),
    });
    equip.plate_state = saved.plate_state || "";
    equip.plate_number = saved.plate_number || "";
    equip.unit_number = saved.unit_number || "";
    equip.vin = saved.vin || "";
    equip.mpg = saved.mpg == null ? "" : String(saved.mpg);
    equip.saved = true;
  } catch (e) {
    equip.error = e.message === "invalid_vin" ? t("equipment.vin_error") : t("equipment.vin_error");
  } finally {
    equip.busy = false;
  }
}

// M13 / E-D1: food alerts are OFF until turned on here. The hint states the caps
// plainly rather than burying them — a driver should know what they're agreeing to.
const foodAlerts = ref(false);
// AI-CONTEXT: THIS SWITCH NEVER READ ITS OWN STATE (N-17, §23 entry 224). It was
// `ref(false)` initialised by nothing, so a driver who had opted in reopened the app to
// an OFF switch — and tapping it, believing they were opting in, opted them OUT. A
// control that misreports itself is worse than one that does nothing, because the driver
// acts on it.
//
// F8 has had the answer since it shipped: `GET /notifications/classes` is the canonical
// per-class preference read, and the notifications sheet beside this card already uses
// it. Read here rather than through `/vendors/alerts/opt-in`, which has no GET at all.
const VENDOR_ALERT_CLASS = "vendor_alert";
async function loadFoodAlerts() {
  try {
    const data = await fetchNotificationClasses();
    const row = (data.classes || []).find((c) => c.key === VENDOR_ALERT_CLASS);
    // absent means F8 has no row yet, which is the same as not opted in
    foodAlerts.value = row ? !!row.opted_in : false;
  } catch {
    /* the switch keeps its default; a failed READ must not assert an opt-in state */
  }
}
async function toggleFoodAlerts() {
  const next = !foodAlerts.value;
  foodAlerts.value = next;
  await setFoodAlerts(next).catch(() => {
    foodAlerts.value = !next; // server said no — don't show a state we didn't save
  });
}

async function loadPoints() {
  try {
    points.value = await fetchPoints();
    pointsState.value = LoadState.LOADED;
    pointsFailure.value = null;
  } catch (e) {
    points.value = null;
    pointsFailure.value = failureOf(e);
    pointsState.value = LoadState.FAILED;
  }
}

onMounted(async () => {
  await loadPoints();
  await loadMe();
  // only when the card is actually on screen — a switched-off module is not asked about
  if (me.value?.food_enabled) await loadFoodAlerts();
});

function changePassword() {
  // D5's ORDINARY entry point. `MoreSurface` is the settings home ("Holds the F1
  // account…"), and it is the only surface where a driver's account details live.
  router.push("/password");
}

function signOut() {
  logout();
  router.push("/login");
}
</script>

<template>
  <div class="more">
    <h1 class="more__title">{{ t("nav.more") }}</h1>

    <!-- AI-CONTEXT: §23 entry 110 — a driver could not see a booking they had paid
         for. More is where a records screen belongs under NAV-1's five fixed tabs. -->
    <section class="card">
      <h2 class="card__title">{{ t("bookings.title") }}</h2>
      <button class="cta" type="button" @click="router.push('/bookings')">
        {{ t("bookings.view") }}
      </button>
    </section>

    <!-- AI-CONTEXT: the install offer's permanent home (§23 entry 152).
         It deliberately does NOT consult the strip's dismissal: tapping × silences an
         interruption, it does not withdraw a capability, and §15.5's "never nags beyond
         that card" only works if the card is somewhere the driver can come back to.
         Gated on `installable` rather than rendered always, because a button that
         cannot install is the dead mic entry 89 cleared off thirteen screens — and it
         disappears once the app IS installed, since `initInstall` returns early in
         standalone and neither ref is ever set. -->
    <section v-if="installable" class="card">
      <h2 class="card__title">{{ t("install.title") }}</h2>
      <p class="install__why">{{ t("install.why") }}</p>
      <button class="cta" type="button" @click="onInstall">{{ t("install.action_long") }}</button>
    </section>

    <!-- M10 points + contributor level. The whole CARD is the unit of loading, per
         §8's "skeletons mirror the real layout" — a balance and a level are one fact
         about the driver's standing and appear together or not at all. -->
    <SkeletonCard v-if="pointsState === LoadState.LOADING" :count="1" />
    <section v-else class="card">
      <h2 class="card__title">{{ t("points.title") }}</h2>
      <p v-if="pointsState === LoadState.FAILED" class="more__failed">
        {{ pointsFailure === Failure.OFFLINE ? t("system.load_offline") : t("more.points_failed") }}
        <button class="more__retry" type="button" @click="loadPoints">{{ t("system.retry") }}</button>
      </p>
      <div v-else class="points">
        <span class="points__figure">{{ points.balance }}</span>
        <span class="points__level">{{ t(`points.level.${points.level}`) }}</span>
      </div>
    </section>

    <!-- F15: pick your language; persists across sessions. The list itself is
         LocalePicker — the same component the login screen opens, so the choice a
         driver makes at the door and the one they change here are one control. -->
    <section class="card">
      <h2 class="card__title">{{ t("more.language") }}</h2>
      <LocalePicker />
    </section>

    <!-- AI-CONTEXT: §6.1 C-3 — "toggled by system setting + manual override". The
         override had no control anywhere in the app, so light was reachable only by
         changing the operating system. Same shape as the language rows beside it:
         chips, not a dropdown (§8 forms — chips when ≤5 options), and the choice
         persists like the locale does. -->
    <section class="card">
      <h2 class="card__title">{{ t("more.appearance") }}</h2>
      <ul class="langs">
        <li v-for="m in modes" :key="m">
          <button
            class="theme-opt"
            :class="{ 'lang--on': mode === m }"
            type="button"
            :aria-pressed="mode === m"
            @click="setMode(m)"
          >
            <span class="lang__name">{{ t(`more.theme.${m}`) }}</span>
            <Check v-if="mode === m" :size="18" :stroke-width="2.5" class="lang__tick" aria-hidden="true" />
          </button>
        </li>
      </ul>
    </section>

    <!-- F1: operating-authority verification — only when the F13 flag is on -->
    <section v-if="me && me.verification_enabled" class="card">
      <h2 class="card__title">{{ t("more.authority") }}</h2>

      <div v-if="me.verified" class="verified">
        <Check :size="18" :stroke-width="2.5" class="verified__tick" aria-hidden="true" />
        <span class="verified__name">{{ me.legal_name || ("MC# " + me.mc_number) }}</span>
        <span class="verified__label">{{ t("authority.verified") }}</span>
      </div>

      <div v-else class="authority__body">
        <p class="authority__hint">{{ t("authority.hint") }}</p>
        <form class="authority__form" @submit.prevent="submitVerify">
          <label class="field">
            <span class="field__label">{{ t("authority.number_label") }}</span>
            <input
              v-model="authForm.number"
              class="field__input"
              type="text"
              inputmode="numeric"
              :placeholder="t('authority.number_ph')"
              autocapitalize="characters"
            />
          </label>
          <p v-if="authForm.error" class="authority__error" role="alert">{{ authForm.error }}</p>
          <button class="cta cta--accent" type="submit" :disabled="authForm.busy">
            <Spinner v-if="authForm.busy" />
            {{ authForm.busy ? t("authority.verifying") : t("authority.verify") }}
          </button>
        </form>
      </div>
    </section>

    <!-- E2: self-reported equipment. The honesty line sits directly under the
         title so it is read before the fields, not after (§11.7 / §12.4). -->
    <section class="card">
      <h2 class="card__title">{{ t("equipment.title") }}</h2>
      <p class="equip__note">{{ t("equipment.self_reported") }}</p>
      <form class="equip" @submit.prevent="submitEquipment">
        <label class="field">
          <span class="field__label">{{ t("equipment.plate_state") }}</span>
          <input
            v-model="equip.plate_state"
            class="field__input"
            type="text"
            maxlength="2"
            autocapitalize="characters"
          />
        </label>
        <label class="field">
          <span class="field__label">{{ t("equipment.plate_number") }}</span>
          <input
            v-model="equip.plate_number"
            class="field__input"
            type="text"
            autocapitalize="characters"
          />
        </label>
        <label class="field">
          <span class="field__label">{{ t("equipment.unit_number") }}</span>
          <input v-model="equip.unit_number" class="field__input" type="text" />
        </label>
        <label class="field">
          <span class="field__label">{{ t("equipment.vin") }}</span>
          <input
            v-model="equip.vin"
            class="field__input"
            type="text"
            maxlength="17"
            autocapitalize="characters"
          />
        </label>
        <!-- AI-CONTEXT: the truck's fuel economy (§23 entry 154). It sits in the
             equipment card because that is where truck FACTS live, and the calculator
             reads it from here rather than owning a second copy. Blank is a real answer
             and the hint says what blank means, so an empty box is not read as an
             unfinished form. -->
        <label class="field">
          <span class="field__label">{{ t("equipment.mpg") }}</span>
          <input
            v-model="equip.mpg"
            class="field__input"
            type="number"
            inputmode="decimal"
            step="0.1"
            :min="MIN_MPG"
            :max="MAX_MPG"
          />
          <span class="equip__hint">{{ t("equipment.mpg_hint") }}</span>
          <span v-if="mpgFieldError" class="equip__error" role="alert">
            {{ t(mpgFieldError) }}
          </span>
        </label>
        <p v-if="equip.error" class="equip__error" role="alert">{{ equip.error }}</p>
        <button class="cta cta--accent" type="submit" :disabled="equip.busy || !!mpgFieldError">
          <Spinner v-if="equip.busy" />
          {{ equip.busy
            ? t("busy.saving")
            : equip.saved ? t("equipment.saved") : t("equipment.save") }}
        </button>
      </form>
    </section>

    <!-- AI-CONTEXT: THE FOOD HALF WAS SWITCHED OFF AND THIS CARD KEPT ADVERTISING IT
         (§23 entry 223, owner report). `m13_vendor` has been FALSE in production since
         HANDOFF-114, food goes BY FLAG rather than by deletion (v2.0 §4: "do not delete
         the code; the cost is sunk and the flag makes it free to carry") — and this
         section had no condition at all, while the authority card twenty lines up has
         had one since it shipped.
         M13 / E-D1: opt-in food alerts. Default OFF; the caps are stated, not buried. -->
    <section v-if="me && me.food_enabled" class="card">
      <h2 class="card__title">{{ t("vendor.alerts") }}</h2>
      <button
        class="alerts"
        type="button"
        :aria-pressed="foodAlerts"
        @click="toggleFoodAlerts"
      >
        <span class="alerts__name">{{ t("vendor.alerts") }}</span>
        <Check v-if="foodAlerts" :size="18" :stroke-width="2.5" class="alerts__tick" aria-hidden="true" />
      </button>
      <p class="equip__note">{{ t("vendor.alerts_hint") }}</p>
    </section>

    <!-- §23 entry 102: the inbox row, composed from the row shapes already in this
         list. §10.5 forbids badges here, so it carries a label and nothing else. -->
    <section class="card">
      <h2 class="card__title">{{ t("notifications.title") }}</h2>
      <button class="alerts alerts--link" type="button" @click="openNotifications">
        <span class="alerts__name">{{ t("more.notifications") }}</span>
      </button>
    </section>

    <section class="card">
      <h2 class="card__title">{{ t("more.account") }}</h2>
      <p v-if="email" class="more__email">{{ email }}</p>
      <button class="cta" type="button" @click="changePassword">
        {{ t("more.change_password") }}
      </button>
      <button class="cta cta--danger" type="button" @click="signOut">{{ t("auth.logout") }}</button>
    </section>

    <BottomSheet :open="notifOpen" :title="t('notifications.title')" @close="notifOpen = false">
      <NotificationsSheet :notifications="notifications" :now="nowMs" @open="openNotification" />
    </BottomSheet>

    <BottomSheet :open="installSheet" :title="t('install.title')" @close="installSheet = false">
      <InstallSheet />
    </BottomSheet>
  </div>
</template>

<style scoped>
/* E2/M13 sections reuse the existing card + field styles; only the honesty note
   and the toggle row are new, both composed from tokens */
.equip {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.equip__note {
  margin: 0 0 var(--s-3);
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.equip__error {
  margin: 0;
  color: var(--flare-500);
  font-size: var(--type-caption-size);
}
/* what a BLANK field means, said where the blank is — an empty box on a form otherwise
   reads as one the driver has not finished */
.equip__hint {
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.alerts {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 64px;
  background: transparent;
  color: var(--text-1);
  font-size: var(--type-body-size);
  text-align: left;
}
.alerts__tick {
  color: var(--shield-500);
}
.more {
  padding: var(--s-4);
}
.more__title {
  margin: 0 0 var(--s-4);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.card {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
  margin-bottom: var(--s-3);
}
.card__title {
  margin: 0 0 var(--s-2);
  font-size: var(--type-label-size);
  color: var(--text-2);
  font-weight: 500;
}
.langs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.theme-opt {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 48px;
  padding: var(--s-2) 0;
  background: transparent;
  border: none;
  border-top: 1px solid var(--line-1);
  color: var(--text-1);
  text-align: left;
  cursor: pointer;
}
/* the theme rows carry no hairline between them — unchanged when the language list
   moved out to LocalePicker, where the rule was `.langs li:first-child .lang,
   .theme-opt`: the second selector was unqualified, so EVERY theme row lost its
   border, and that is the appearance this keeps. */
.theme-opt {
  border-top: none;
}
.lang__name {
  font-size: var(--type-body-size);
}
.lang--on .lang__name {
  color: var(--shield-500);
  font-weight: 500;
}
.lang__tick {
  color: var(--shield-500);
}
.more__failed {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.more__retry {
  min-height: 48px;
  padding: 0 var(--s-2);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
.points {
  display: flex;
  align-items: baseline;
  gap: var(--s-3);
}
.points__figure {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-size: var(--type-display-size);
}
.points__level {
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.more__email {
  margin: 0 0 var(--s-4);
  font-size: var(--type-body-size);
  color: var(--text-1);
}
.verified {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 48px;
}
.verified__tick {
  color: var(--ledger-500);
  flex-shrink: 0;
}
.verified__name {
  font-size: var(--type-body-size);
  color: var(--text-1);
  flex: 1;
}
.verified__label {
  font-size: var(--type-caption-size);
  color: var(--ledger-500);
  font-weight: 500;
}
.authority__hint {
  margin: 0 0 var(--s-3);
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.authority__form {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.field__label {
  font-size: var(--type-label-size);
  color: var(--text-2);
}
.field__input {
  min-height: 56px;
  padding: 0 var(--s-3);
  border-radius: var(--r-control);
  border: 1px solid var(--line-1);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.authority__error {
  margin: 0;
  color: var(--flare-500);
  font-size: var(--type-caption-size);
}
.install__why {
  margin: 0 0 var(--s-3);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.cta--accent {
  background: var(--accent-fill);
  color: var(--on-accent);
}
.cta {
  width: 100%;
  min-height: 56px;
  border-radius: var(--r-control);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta--danger {
  background: transparent;
  border: 1px solid var(--line-1);
  color: var(--flare-500);
}
</style>
