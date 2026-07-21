<!-- AI-CONTEXT: More tab — the overflow/settings home. Holds the F1 account
     section (who's signed in + Log out) and the M10 points/reputation card
     (balance in Mono + contributor level). Calm and minimal (§15.3). Log out
     clears the session (api.js) and returns to the auth surface. -->
<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Check } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { LAUNCH_LOCALES } from "../core/i18n/index.js";
import { email, logout, fetchPoints } from "../core/api.js";
import { SAMPLE_POINTS } from "../core/fixtures.js";

const router = useRouter();
const { t, locale, setLocale } = useI18n();
const points = ref(SAMPLE_POINTS);

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
