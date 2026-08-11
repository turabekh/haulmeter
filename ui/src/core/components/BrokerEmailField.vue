<!-- AI-CONTEXT: the broker's address, shown and edited in place.

     ONE component for two surfaces on purpose. The Load tab shows it as a fact about the
     load; the claim screen shows it as the thing standing between the driver and a notice
     they are trying to send. Those are different framings of the same field, and two
     copies would drift in exactly the way the five delivery states nearly did — the copy
     is passed in, the behaviour is not.

     It is fields and states composed from existing tokens: no new colour, no new type
     size, no new control pattern (design-prd §22.2). The input reuses the 56 dp control
     height every other text field in this app uses, so §6.5's touch floor is inherited
     rather than re-argued. -->
<script setup>
import { ref, computed, watch } from "vue";
import { Mail, Check } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { contactEmailError, normalizeContactEmail } from "../contact.js";
import { setCounterpartyEmail } from "../api.js";

const props = defineProps({
  loadId: { type: String, default: null },
  email: { type: String, default: null },
  // "row" states the fact and offers an edit; "inline" is already open, because the
  // surface using it has just told the driver the address is what is missing
  variant: { type: String, default: "row" },
});
const emit = defineEmits(["saved"]);
const { t } = useI18n();

const open = ref(props.variant === "inline");
const draft = ref(props.email ?? "");
const saving = ref(false);
const saved = ref(false);
// a refusal the server made that the client's own rule did not catch — the server is the
// one that decides, so its message is shown rather than second-guessed
const serverError = ref(null);

watch(
  () => props.email,
  (next) => {
    draft.value = next ?? "";
  },
);

const localError = computed(() => contactEmailError(draft.value));
const blocked = computed(() => saving.value || !!localError.value || !props.loadId);

async function save() {
  if (blocked.value) return;
  saving.value = true;
  serverError.value = null;
  try {
    const res = await setCounterpartyEmail(props.loadId, normalizeContactEmail(draft.value));
    saved.value = true;
    open.value = props.variant === "inline";
    // the parent re-reads rather than trusting this component's copy: under copy-on-write
    // the load's counterparty identity changed, and the delivery state has to re-derive
    emit("saved", res);
  } catch (err) {
    serverError.value = err.detail || null;
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="bmail" :class="`bmail--${variant}`">
    <p v-if="variant === 'row'" class="bmail__fact">
      <Mail :size="16" :stroke-width="2" aria-hidden="true" />
      <span v-if="email" class="bmail__addr">{{ email }}</span>
      <span v-else class="bmail__none">{{ t("load.broker_email_none") }}</span>
      <button v-if="!open" class="bmail__edit" type="button" @click="open = true">
        {{ email ? t("load.broker_email_edit") : t("load.broker_email_add") }}
      </button>
    </p>

    <div v-if="open" class="bmail__editor">
      <label class="bmail__label" :for="`bmail-${loadId}`">
        {{ t("load.broker_email") }}
      </label>
      <input
        :id="`bmail-${loadId}`"
        v-model="draft"
        class="bmail__input"
        type="email"
        inputmode="email"
        autocomplete="off"
        autocapitalize="none"
        spellcheck="false"
      />
      <p v-if="localError" class="bmail__error" role="alert">{{ t(localError) }}</p>
      <p v-else-if="serverError" class="bmail__error" role="alert">{{ serverError }}</p>
      <button class="bmail__save" type="button" :disabled="blocked" @click="save">
        {{ t("load.broker_email_save") }}
      </button>
      <p v-if="saved && !localError" class="bmail__saved">
        <Check :size="14" :stroke-width="2.5" aria-hidden="true" />
        {{ t("load.broker_email_saved") }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.bmail__fact {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.bmail__addr {
  color: var(--text-1);
  word-break: break-all;
}
.bmail__none {
  color: var(--text-3);
}
.bmail__edit {
  margin-left: auto;
  min-height: 48px;
  padding: 0 var(--s-2);
  border: 0;
  background: none;
  color: var(--accent-500);
  font-size: var(--type-label-size);
}
.bmail__label {
  display: block;
  margin-bottom: var(--s-2);
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.bmail__input {
  width: 100%;
  /* the control height every other text field here uses, so §6.5's floor is inherited */
  min-height: 56px;
  min-width: 0;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.bmail__error {
  margin-top: var(--s-2);
  color: var(--marker-500);
  font-size: var(--type-label-size);
}
.bmail__save {
  margin-top: var(--s-2);
  width: 100%;
  min-height: 48px;
  border: 0;
  border-radius: var(--r-control);
  background: var(--accent-500);
  color: var(--on-accent);
  font-size: var(--type-body-size);
}
.bmail__save:disabled {
  opacity: 0.5;
}
.bmail__saved {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-2);
  color: var(--ledger-500);
  font-size: var(--type-label-size);
}
</style>
