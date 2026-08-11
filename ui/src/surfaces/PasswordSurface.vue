<!-- AI-CONTEXT: the screen that makes four finished things usable (D1, D5).

     `complete_credential_change` had no route and no screen, so session revocation, the
     password floor and the opportunistic rehash were all correct and unreachable — and an
     admin-issued temporary password silently became the permanent one.

     ONE component, two framings. `forced` is the post-reset case: it explains why the
     driver is here and offers no way out but completing it. The router guard is what makes
     that true; this component only renders it. Composed from existing field and error
     patterns — no new control types. -->
<script setup>
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "../core/i18n.js";
import { changePassword, mustChangePassword } from "../core/api.js";
import { useDriverState } from "../core/state.js";

const { t } = useI18n();
const router = useRouter();
// §22.3: this route declares `withdraws`, and the claim has to be backed. A credential
// form is the definition of a task not to attempt at speed — two password fields and a
// keyboard is exactly what SM-3 exists to take off the screen.
const { isDriving } = useDriverState();

const forced = computed(() => mustChangePassword.value);
const current = ref("");
const next = ref("");
const busy = ref(false);
const error = ref(null);
const done = ref(null);

// the same floor the server applies, so a driver learns before the round trip
const MIN = 8;
const tooShort = computed(() => next.value.length > 0 && next.value.length < MIN);
const blocked = computed(
  () => busy.value || !current.value || next.value.length < MIN,
);

async function submit() {
  if (blocked.value) return;
  busy.value = true;
  error.value = null;
  try {
    done.value = await changePassword(current.value, next.value);
    current.value = "";
    next.value = "";
  } catch (err) {
    // the REAL error, never a false success — D5's honesty requirement
    if (err.status === 401) error.value = t("pw.err_current");
    else if (err.status === 429) {
      error.value = t("pw.err_throttled", { seconds: err.retryAfter ?? 60 });
    } else if (err.status === 422) error.value = t("auth.password_too_short");
    else error.value = t("pw.err_network");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="pw">
    <p v-if="isDriving" class="pw__hint" role="status">{{ t("voice.unavailable") }}</p>
    <template v-else>
    <h1 class="pw__title">{{ forced ? t("pw.forced_title") : t("pw.title") }}</h1>
    <p v-if="forced" class="pw__hint">{{ t("pw.forced_hint") }}</p>

    <template v-if="!done">
      <label class="pw__field">
        <span class="pw__label">{{ t("pw.current") }}</span>
        <input v-model="current" class="pw__input" type="password" autocomplete="current-password" />
      </label>
      <label class="pw__field">
        <span class="pw__label">{{ t("pw.new") }}</span>
        <input v-model="next" class="pw__input" type="password" autocomplete="new-password" />
        <span v-if="tooShort" class="pw__error" role="alert">{{ t("auth.password_too_short") }}</span>
      </label>
      <p v-if="error" class="pw__error" role="alert">{{ error }}</p>
      <button class="pw__cta" type="button" :disabled="blocked" @click="submit">
        {{ t("pw.submit") }}
      </button>
    </template>

    <template v-else>
      <p class="pw__ok" role="status">{{ t("pw.ok") }}</p>
      <!-- a security action the driver cannot observe is one they cannot trust — and if
           nothing else was signed out, say nothing rather than saying zero -->
      <p v-if="done.other_sessions_ended > 0" class="pw__hint">{{ t("pw.others_out") }}</p>
      <button class="pw__cta" type="button" @click="router.push('/')">{{ t("booking.done") }}</button>
    </template>
    </template>
  </div>
</template>

<style scoped>
.pw { padding: var(--s-4); display: flex; flex-direction: column; gap: var(--s-3); }
.pw__title { color: var(--text-1); font-size: var(--type-title-size); }
.pw__hint { color: var(--text-2); font-size: var(--type-body-size); }
.pw__label { display: block; margin-bottom: var(--s-2); color: var(--text-2); font-size: var(--type-label-size); }
.pw__field { display: block; }
.pw__input {
  width: 100%;
  min-height: 56px;
  min-width: 0;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.pw__error { display: block; margin-top: var(--s-2); color: var(--marker-500); font-size: var(--type-label-size); }
.pw__ok { color: var(--ledger-500); font-size: var(--type-body-size); }
.pw__cta {
  min-height: 48px;
  border: 0;
  border-radius: var(--r-control);
  background: var(--accent-500);
  color: var(--on-accent);
  font-size: var(--type-body-size);
}
.pw__cta:disabled { opacity: 0.5; }
</style>
