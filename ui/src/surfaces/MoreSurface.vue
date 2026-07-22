<!-- AI-CONTEXT: More tab — the overflow/settings home. Holds the F1 account
     section (who's signed in + Log out) and the M10 points/reputation card
     (balance in Mono + contributor level). Calm and minimal (§15.3). Log out
     clears the session (api.js) and returns to the auth surface. -->
<script setup>
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Check } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { LAUNCH_LOCALES } from "../core/i18n/index.js";
import { email, logout, fetchPoints, fetchMe, verifyAuthority } from "../core/api.js";
import { SAMPLE_POINTS } from "../core/fixtures.js";

const router = useRouter();
const { t, locale, setLocale } = useI18n();
const points = ref(SAMPLE_POINTS);

// F1: operating-authority verification (FMCSA). Section only appears when the
// F13 flag is on; verified state is plain text here (§10 — no badges on More),
// the colored status pill lives where credibility is consumed (Claim / Money).
const me = ref(null);
const authForm = reactive({ number: "", busy: false, error: "" });

async function loadMe() {
  try {
    me.value = await fetchMe();
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

    <section class="card">
      <h2 class="card__title">{{ t("more.account") }}</h2>
      <p v-if="email" class="more__email">{{ email }}</p>
      <button class="cta cta--danger" type="button" @click="signOut">{{ t("auth.logout") }}</button>
    </section>
  </div>
</template>

<style scoped>
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
.lang {
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
.langs li:first-child .lang {
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
