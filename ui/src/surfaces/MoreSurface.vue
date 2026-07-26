<!-- AI-CONTEXT: More tab — the overflow/settings home. Holds the F1 account
     section (who's signed in + Log out) and the M10 points/reputation card
     (balance in Mono + contributor level). Calm and minimal (§15.3). Log out
     clears the session (api.js) and returns to the auth surface. -->
<script setup>
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Check } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { useTheme } from "../core/theme.js";
import { LAUNCH_LOCALES } from "../core/i18n/index.js";
import { email, logout, fetchPoints, fetchMe, verifyAuthority, saveEquipment, setFoodAlerts } from "../core/api.js";
import { SAMPLE_POINTS } from "../core/fixtures.js";

const router = useRouter();
const { t, locale, setLocale } = useI18n();
const { mode, setMode, modes } = useTheme();
const points = ref(SAMPLE_POINTS);

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
  busy: false,
  error: "",
  saved: false,
});

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
    });
    equip.plate_state = saved.plate_state || "";
    equip.plate_number = saved.plate_number || "";
    equip.unit_number = saved.unit_number || "";
    equip.vin = saved.vin || "";
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
async function toggleFoodAlerts() {
  const next = !foodAlerts.value;
  foodAlerts.value = next;
  await setFoodAlerts(next).catch(() => {
    foodAlerts.value = !next; // server said no — don't show a state we didn't save
  });
}

// each language shown in its OWN name so a driver recognizes it regardless of the
// current UI language (F15 launch locales)
const LANG_NAMES = {
  en: "English",
  es: "Español",
  pa: "ਪੰਜਾਬੀ",
  ru: "Русский",
  uz: "Oʻzbekcha",
  so: "Soomaali",
};

onMounted(async () => {
  try {
    points.value = await fetchPoints();
  } catch {
    points.value = SAMPLE_POINTS; // unauthenticated / offline
  }
  await loadMe();
});

function signOut() {
  logout();
  router.push("/login");
}
</script>

<template>
  <div class="more">
    <h1 class="more__title">{{ t("nav.more") }}</h1>

    <!-- M10 points + contributor level -->
    <section class="card">
      <h2 class="card__title">{{ t("points.title") }}</h2>
      <div class="points">
        <span class="points__figure">{{ points.balance }}</span>
        <span class="points__level">{{ t(`points.level.${points.level}`) }}</span>
      </div>
    </section>

    <!-- F15: pick your language; persists across sessions -->
    <section class="card">
      <h2 class="card__title">{{ t("more.language") }}</h2>
      <ul class="langs">
        <li v-for="code in LAUNCH_LOCALES" :key="code">
          <button
            class="lang"
            :class="{ 'lang--on': locale === code }"
            type="button"
            :aria-pressed="locale === code"
            @click="setLocale(code)"
          >
            <span class="lang__name">{{ LANG_NAMES[code] }}</span>
            <Check v-if="locale === code" :size="18" :stroke-width="2.5" class="lang__tick" aria-hidden="true" />
          </button>
        </li>
      </ul>
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
        <p v-if="equip.error" class="equip__error" role="alert">{{ equip.error }}</p>
        <button class="cta cta--accent" type="submit" :disabled="equip.busy">
          {{ equip.saved && !equip.busy ? t("equipment.saved") : t("equipment.save") }}
        </button>
      </form>
    </section>

    <!-- M13 / E-D1: opt-in food alerts. Default OFF; the caps are stated, not buried. -->
    <section class="card">
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

    <section class="card">
      <h2 class="card__title">{{ t("more.account") }}</h2>
      <p v-if="email" class="more__email">{{ email }}</p>
      <button class="cta cta--danger" type="button" @click="signOut">{{ t("auth.logout") }}</button>
    </section>
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
.lang,
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
.langs li:first-child .lang,
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
