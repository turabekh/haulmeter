<!-- AI-CONTEXT: the way into the vendor portal (design-prd §18, §23 E-D3).

     Before this existed, a cook opening /vendor-portal was bounced to the DRIVER
     login — mobile-first, asking for their authority number — and then dropped on
     the trucking map, with no way back but the URL bar. This is the §18 portal
     version of that door: desktop-first, 1200 dp cap, the same tokens, and it never
     mentions a truck.

     Three states, one route: sign in · create an account · describe the business.
     The third step asks exactly what the Q-4 publish floor will require (languages,
     a halal answer) so a cook is not told after the fact that their listing cannot
     go out. Registration lands on the UNVERIFIED rung and the portal says so —
     there is no approval queue (owner decision), because the floor, the tier label
     and Q-8 moderation are the gate.

     PHASE A: nothing here takes a payment or asks for one. -->
<script setup>
import { computed, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { Store } from "lucide-vue-next";
import { useI18n } from "../../core/i18n.js";
import { BRAND } from "../../core/brand.js";
import { login, register, registerVendor, isAuthenticated } from "../../core/api.js";

const { t } = useI18n();
const router = useRouter();

// signin -> the cook already has an account; signup -> they do not; business -> the
// account exists and now needs a vendor profile. A signed-in visitor who is not yet
// a vendor lands straight on the third step rather than being asked to log in again.
const step = ref(isAuthenticated.value ? "business" : "signin");
const error = ref(null);
const busy = ref(false);

const account = reactive({ email: "", password: "" });
const business = reactive({
  name: "",
  vendor_type: "food_mobile",
  metro: "",
  contact_phone: "",
  languages: "",
  halal_disclosure: "",
});

const TYPES = ["food_mobile", "service_center"];

// what the Q-4 floor will ask for, asked HERE instead of after a refused publish
const ready = computed(
  () => business.name.trim().length > 0 && business.languages.trim().length > 0,
);

// AI-CONTEXT: a 409 means two DIFFERENT things on this one route, and saying the
// wrong one sends a cook looking for a problem they do not have:
//   · creating an account -> that email already has one. The fix is to sign in, and
//     it is one tap away, so the message offers it instead of describing it.
//   · describing the business -> Q-5, a vendor with these details already exists.
// `register()` signals the first as the message "email_taken" rather than a status,
// so both shapes are checked here.
const emailTaken = ref(false);

function fail(e, step) {
  const taken = e?.status === 409 || e?.message === "email_taken";
  if (step === "account" && taken) return t("auth.error_taken");
  if (step === "business" && taken) return t("vendor.join.duplicate");
  if (e?.status === 401 || e?.message?.includes("401")) return t("auth.error_invalid");
  if (typeof e?.detail === "string") return e.detail;
  return t("vendor.join.error");
}

function toSignIn() {
  // carry the email across: retyping it is the one thing they have already done
  step.value = "signin";
  emailTaken.value = false;
  error.value = null;
  account.password = "";
}

async function signIn() {
  busy.value = true;
  error.value = null;
  try {
    await login(account.email.trim(), account.password);
    // an existing vendor goes to their portal; a signed-in non-vendor is asked to
    // describe the business, which is the only thing still missing
    router.push("/vendor-portal");
  } catch (e) {
    error.value = fail(e, "signin");
  } finally {
    busy.value = false;
  }
}

async function createAccount() {
  busy.value = true;
  error.value = null;
  emailTaken.value = false;
  try {
    await register(account.email.trim(), account.password);
    step.value = "business";
  } catch (e) {
    emailTaken.value = e?.status === 409 || e?.message === "email_taken";
    error.value = fail(e, "account");
  } finally {
    busy.value = false;
  }
}

async function createBusiness() {
  busy.value = true;
  error.value = null;
  try {
    await registerVendor({
      name: business.name.trim(),
      vendor_type: business.vendor_type,
      metro: business.metro.trim(),
      contact_phone: business.contact_phone.trim() || null,
      languages: business.languages
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      halal_disclosure: business.halal_disclosure.trim(),
      // answering at all is what the floor checks — "no halal claim" is a complete
      // answer and a blank is not, so reaching this button marks it answered
      halal_answered: true,
    });
    router.push("/vendor-portal");
  } catch (e) {
    error.value = fail(e, "business");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="join">
    <header class="join__head">
      <Store :size="28" :stroke-width="2" aria-hidden="true" />
      <div>
        <h1 class="join__title">{{ t("vendor.join.title") }}</h1>
        <p class="join__sub">{{ t("vendor.join.subtitle", { brand: BRAND }) }}</p>
      </div>
    </header>

    <!-- said plainly and up front: this costs nothing and sells nothing -->
    <p class="join__free">{{ t("vendor.join.free") }}</p>

    <form class="card" @submit.prevent>
      <template v-if="step === 'signin'">
        <h2 class="card__title">{{ t("vendor.join.signin") }}</h2>
        <label class="field">
          <span class="field__label">{{ t("auth.email") }}</span>
          <input v-model="account.email" class="field__input" type="email" autocomplete="email" />
        </label>
        <label class="field">
          <span class="field__label">{{ t("auth.password") }}</span>
          <input
            v-model="account.password"
            class="field__input"
            type="password"
            autocomplete="current-password"
          />
        </label>
        <button class="cta" type="submit" :disabled="busy" @click="signIn">
          {{ t("vendor.join.signin") }}
        </button>
        <button class="link" type="button" @click="step = 'signup'; error = null">
          {{ t("vendor.join.to_signup") }}
        </button>
      </template>

      <template v-else-if="step === 'signup'">
        <h2 class="card__title">{{ t("vendor.join.create_account") }}</h2>
        <label class="field">
          <span class="field__label">{{ t("auth.email") }}</span>
          <input v-model="account.email" class="field__input" type="email" autocomplete="email" />
        </label>
        <label class="field">
          <span class="field__label">{{ t("auth.password") }}</span>
          <input
            v-model="account.password"
            class="field__input"
            type="password"
            autocomplete="new-password"
          />
        </label>
        <button class="cta" type="submit" :disabled="busy" @click="createAccount">
          {{ t("vendor.join.next") }}
        </button>
        <button class="link" type="button" @click="step = 'signin'; error = null">
          {{ t("vendor.join.to_signin") }}
        </button>
      </template>

      <template v-else>
        <h2 class="card__title">{{ t("vendor.join.business") }}</h2>
        <label class="field">
          <span class="field__label">{{ t("vendor.join.name") }}</span>
          <input v-model="business.name" class="field__input" type="text" maxlength="160" />
        </label>
        <fieldset class="field">
          <legend class="field__label">{{ t("vendor.join.type") }}</legend>
          <div class="types">
            <button
              v-for="ty in TYPES"
              :key="ty"
              type="button"
              class="type"
              :class="{ 'type--on': business.vendor_type === ty }"
              @click="business.vendor_type = ty"
            >
              {{ t(`vendor.type.${ty}`) }}
            </button>
          </div>
        </fieldset>
        <label class="field">
          <span class="field__label">{{ t("vendor.join.metro") }}</span>
          <input v-model="business.metro" class="field__input" type="text" maxlength="80" />
        </label>
        <label class="field">
          <span class="field__label">{{ t("vendor.phone") }}</span>
          <input v-model="business.contact_phone" class="field__input" type="tel" />
        </label>
        <label class="field">
          <span class="field__label">{{ t("vendor.languages") }}</span>
          <input v-model="business.languages" class="field__input" type="text" />
          <span class="field__hint">{{ t("vendor.join.languages_hint") }}</span>
        </label>
        <label class="field">
          <span class="field__label">{{ t("vendor.halal") }}</span>
          <input v-model="business.halal_disclosure" class="field__input" type="text" />
          <span class="field__hint">{{ t("vendor.join.halal_hint") }}</span>
        </label>
        <button class="cta" type="submit" :disabled="busy || !ready" @click="createBusiness">
          {{ t("vendor.join.finish") }}
        </button>
        <!-- the ladder, stated before they climb it, so "Unverified" on their pin is
             never a surprise (§11.7) -->
        <p class="join__ladder">{{ t("vendor.join.starts_unverified") }}</p>
      </template>

      <p v-if="error" class="join__error" role="alert">{{ error }}</p>
      <!-- the fix is one tap, so offer it rather than describing it -->
      <button v-if="emailTaken" class="cta" type="button" @click="toSignIn">
        {{ t("vendor.join.signin") }}
      </button>
    </form>
  </div>
</template>

<style scoped>
/* §18: desktop-first, comfortable, 1200 dp cap, tokens only */
.join {
  max-width: 640px;
  margin: 0 auto;
  padding: var(--s-6) var(--s-4);
}
.join__head {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  color: var(--shield-500);
}
.join__title {
  margin: 0;
  color: var(--text-1);
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
.join__sub {
  margin: var(--s-1) 0 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.join__free {
  margin: var(--s-4) 0 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
}
.card {
  margin-top: var(--s-4);
  padding: var(--s-5);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
}
.card__title {
  margin: 0 0 var(--s-4);
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.field {
  display: block;
  margin-bottom: var(--s-4);
  border: 0;
  padding: 0;
}
.field__label {
  display: block;
  margin-bottom: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.field__input {
  width: 100%;
  min-height: 48px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.field__hint {
  display: block;
  margin-top: var(--s-1);
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.types {
  display: flex;
  gap: var(--s-2);
}
.type {
  flex: 1 1 auto;
  min-height: 48px;
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.type--on {
  border-color: var(--shield-500);
  color: var(--shield-500);
}
.cta {
  display: block;
  width: 100%;
  min-height: 56px;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.cta:disabled {
  opacity: 0.5;
}
.link {
  display: block;
  width: 100%;
  min-height: 48px;
  margin-top: var(--s-2);
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-label-size);
}
.join__ladder {
  margin: var(--s-3) 0 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.join__error {
  margin: var(--s-3) 0 0;
  color: var(--flare-500);
  font-size: var(--type-body-size);
}
</style>
