<!-- AI-CONTEXT: F1 login / create-account (PRD §7.1 — onboard in under 60 s, no
     activation step). A full-screen linear flow (NAV-3 onboarding), no tab
     chrome. §202 forms: 56 dp inputs, labels above, one primary CTA; errors are
     specific + unblaming (§12.4). Email/password only at launch. On success the
     session token persists (api.js) and the app's live APIs light up. -->
<script setup>
import { ref, reactive, computed } from "vue";
import { useRouter } from "vue-router";
import { Languages } from "lucide-vue-next";
import { useI18n } from "../core/i18n.js";
import { LOCALE_NAMES } from "../core/i18n/index.js";
import { login, register } from "../core/api.js";
import { BRAND } from "../core/brand.js";
import BottomSheet from "../core/components/BottomSheet.vue";
import LocalePicker from "../core/components/LocalePicker.vue";
import Spinner from "../core/components/Spinner.vue";

const router = useRouter();
const { t, locale } = useI18n();

// AI-CONTEXT: the language chooser belongs on THIS screen, not only in More
// (§23 entry 125). Every one of the six locales ships from day one, and until now
// the only way to reach five of them was to read an English login screen, guess
// the right words, sign up, find the More tab and scroll — the driver most in need
// of the setting had to complete the flow in a language they don't read to get it.
// The trigger names the CURRENT language in its own words, so it is legible before
// anything else on the page is.
const langOpen = ref(false);
const langName = computed(() => LOCALE_NAMES[locale.value] ?? LOCALE_NAMES.en);
const isDev = import.meta.env.DEV; // the dev-directory link ships only in dev builds

const mode = ref("login"); // login | register
const form = reactive({ email: "", password: "" });
const error = ref("");
const submitting = ref(false);

// operating authority declared at signup — decides whether detention claims are
// invoiced to the broker (owner-op) or exported to a carrier (company driver)
const AUTHORITIES = ["own_mc", "leased", "company"];
const authority = ref("own_mc");

function toggle() {
  mode.value = mode.value === "login" ? "register" : "login";
  error.value = "";
}

async function submit() {
  error.value = "";
  submitting.value = true;
  try {
    if (mode.value === "login") {
      await login(form.email.trim(), form.password);
    } else {
      await register(form.email.trim(), form.password, authority.value);
    }
    // AI-CONTEXT: the first screen after signing in, and it named the MAP (D21, §23
    // entry 228). With the map dormant that pushed every new driver at a redirect on
    // their very first tap. `"/"` rather than a literal `/load`: the router owns where
    // home is, so this line does not have to be found again when the map returns.
    router.push("/");
  } catch (e) {
    if (e.message === "email_taken") error.value = t("auth.error_taken");
    else if (e.message?.startsWith("login") || e.message?.includes("401")) error.value = t("auth.error_invalid");
    else if (mode.value === "login") error.value = t("auth.error_invalid");
    else error.value = t("auth.error_network");
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="auth">
    <!-- above the brand, because a driver who cannot read the tagline needs this
         before they need anything else on the screen. NAV-3: the list opens as a
         sheet over the flow rather than a sixth control stacked into it. -->
    <div class="auth__bar">
      <button class="lang-btn" type="button" :aria-label="t('more.language')" @click="langOpen = true">
        <Languages :size="20" :stroke-width="2" aria-hidden="true" />
        <span class="lang-btn__name" :lang="locale">{{ langName }}</span>
      </button>
    </div>

    <div class="auth__head">
      <h1 class="auth__brand">{{ BRAND }}</h1>
      <p class="auth__tagline">{{ t("auth.tagline") }}</p>
    </div>

    <form class="auth__form" @submit.prevent="submit">
      <label class="field">
        <span class="field__label">{{ t("auth.email") }}</span>
        <input
          v-model="form.email"
          class="field__input"
          type="email"
          inputmode="email"
          autocomplete="email"
          autocapitalize="none"
          required
        />
      </label>
      <label class="field">
        <span class="field__label">{{ t("auth.password") }}</span>
        <input
          v-model="form.password"
          class="field__input"
          type="password"
          autocomplete="current-password"
          required
        />
      </label>

      <!-- operating authority — asked once, at signup (§7.1) -->
      <fieldset v-if="mode === 'register'" class="authority">
        <legend class="field__label">{{ t("auth.authority_q") }}</legend>
        <div class="authority__opts" role="radiogroup">
          <button
            v-for="a in AUTHORITIES"
            :key="a"
            type="button"
            class="auth-opt"
            :class="{ 'auth-opt--on': authority === a }"
            role="radio"
            :aria-checked="authority === a"
            @click="authority = a"
          >
            <span class="auth-opt__name">{{ t(`auth.authority.${a}`) }}</span>
            <span class="auth-opt__desc">{{ t(`auth.authority_desc.${a}`) }}</span>
          </button>
        </div>
      </fieldset>

      <p v-if="error" class="auth__error" role="alert">{{ error }}</p>

      <button class="cta" type="submit" :disabled="submitting">
        <Spinner v-if="submitting" />
        {{ submitting
          ? t("busy.working")
          : mode === "login" ? t("auth.login") : t("auth.register") }}
      </button>
    </form>

    <button class="auth__toggle" type="button" @click="toggle">
      {{ mode === "login" ? t("auth.to_register") : t("auth.to_login") }}
    </button>

    <button v-if="isDev" class="auth__dev" type="button" @click="router.push('/dev')">
      Explore all screens (dev directory) →
    </button>

    <BottomSheet :open="langOpen" :title="t('more.language')" @close="langOpen = false">
      <LocalePicker @pick="langOpen = false" />
    </BottomSheet>
  </div>
</template>

<style scoped>
/* §6.5 glove spec: 48 dp is the floor for anything tappable, and a dev-only
   affordance is not exempt — the first thing the layout harness ever found was this
   control at 328×19, which no gloved thumb could hit reliably. */
.auth__dev {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 48px;
  margin-top: var(--s-4);
  background: transparent;
  border: none;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  text-decoration: underline;
}
</style>

<style scoped>
.auth {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  padding: var(--s-6) var(--s-4) var(--s-4);
}
.auth__bar {
  display: flex;
  justify-content: flex-end;
}
/* a hairline secondary (§8), sized by --touch-min like everything tappable (§6.5).
   The language's own name rides beside the glyph rather than behind it: an icon
   alone would say "there is a setting here" without saying which way it is set,
   and the whole value of this control is being readable to someone who cannot
   read the rest of the screen. */
.lang-btn {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--text-1);
  font-size: var(--type-label-size);
}
.auth__head {
  margin-top: var(--s-4);
  margin-bottom: var(--s-6);
  text-align: center;
}
.auth__brand {
  margin: 0;
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
  letter-spacing: 0.04em;
}
.auth__tagline {
  margin: var(--s-2) 0 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.auth__form {
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
  background: var(--ink-1);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.auth__error {
  margin: 0;
  color: var(--flare-500);
  font-size: var(--type-caption-size);
}
.authority {
  border: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.authority legend {
  padding: 0;
  margin-bottom: var(--s-1);
}
.authority__opts {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.auth-opt {
  display: flex;
  flex-direction: column;
  gap: 2px;
  text-align: left;
  padding: var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-1);
  color: var(--text-1);
}
.auth-opt--on {
  border-color: var(--shield-500);
  background: var(--shield-050, var(--ink-1));
}
.auth-opt__name {
  font-size: var(--type-body-size);
  font-weight: 500;
}
.auth-opt--on .auth-opt__name {
  color: var(--shield-500);
}
.auth-opt__desc {
  font-size: var(--type-caption-size);
  color: var(--text-3);
}
.cta {
  width: 100%;
  min-height: 56px;
  margin-top: var(--s-2);
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta:disabled {
  opacity: 0.6;
}
.auth__toggle {
  margin-top: var(--s-4);
  min-height: 48px;
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
</style>
