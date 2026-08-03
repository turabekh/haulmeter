<!-- AI-CONTEXT: the six-locale chooser (F15 / design-prd §12.5), built once here and
     reused — More's settings row and the login screen show the SAME list, because a
     driver who picks their language at the door and a driver who changes it later are
     making one choice and must not meet two controls for it (§8: components are built
     once in core and reused).

     Each language is written in its OWN name (`LOCALE_NAMES`, endonyms), never
     translated: on /login the reader by definition cannot yet read the interface, so
     the list has to be legible with the app still speaking a language they don't.
     Rows, not chips — §8 puts chips at ≤5 options and there are six — and 48 dp
     minimum per §6.5. The tick is not the only signal (C-1): the chosen row also
     carries the shield colour and weight. -->
<script setup>
import { Check } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { LAUNCH_LOCALES, LOCALE_NAMES } from "../i18n/index.js";

const emit = defineEmits(["pick"]);
const { locale, setLocale } = useI18n();

function choose(code) {
  setLocale(code);
  emit("pick", code);
}
</script>

<template>
  <ul class="langs">
    <li v-for="code in LAUNCH_LOCALES" :key="code">
      <button
        class="lang"
        :class="{ 'lang--on': locale === code }"
        type="button"
        :aria-pressed="locale === code"
        :lang="code"
        @click="choose(code)"
      >
        <span class="lang__name">{{ LOCALE_NAMES[code] }}</span>
        <Check
          v-if="locale === code"
          :size="18"
          :stroke-width="2.5"
          class="lang__tick"
          aria-hidden="true"
        />
      </button>
    </li>
  </ul>
</template>

<style scoped>
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
  min-height: var(--touch-min);
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
</style>
