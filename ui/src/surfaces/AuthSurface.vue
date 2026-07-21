<!-- AI-CONTEXT: F1 login / create-account (PRD §7.1 — onboard in under 60 s, no
     activation step). A full-screen linear flow (NAV-3 onboarding), no tab
     chrome. §202 forms: 56 dp inputs, labels above, one primary CTA; errors are
     specific + unblaming (§12.4). Email/password only at launch. On success the
     session token persists (api.js) and the app's live APIs light up. -->
<script setup>
import { ref, reactive } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { login, register } from "../core/api.js";

const router = useRouter();
const { t } = useI18n();

const mode = ref("login"); // login | register
const form = reactive({ email: "", password: "" });
const error = ref("");
const submitting = ref(false);

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
      await register(form.email.trim(), form.password);
    }
    router.push("/map");
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
    <div class="auth__head">
      <h1 class="auth__brand">LONGHAUL</h1>
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

      <p v-if="error" class="auth__error" role="alert">{{ error }}</p>

      <button class="cta" type="submit" :disabled="submitting">
        {{ mode === "login" ? t("auth.login") : t("auth.register") }}
      </button>
    </form>

    <button class="auth__toggle" type="button" @click="toggle">
      {{ mode === "login" ? t("auth.to_register") : t("auth.to_login") }}
    </button>

    <button class="auth__dev" type="button" @click="router.push('/dev')">
      Explore all screens (dev directory) →
    </button>
  </div>
</template>

<style scoped>
.auth__dev {
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
.auth__head {
  margin-top: var(--s-6);
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
