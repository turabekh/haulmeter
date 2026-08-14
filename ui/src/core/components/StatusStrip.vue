<!-- AI-CONTEXT: Top context strip (design-prd §7.2) — connectivity only, and only
     when there is something to say.

     It used to carry two things that earned no space, on EVERY driver screen:

     · THE STATE LABEL rendered `state.value` raw — "idle", "on_site" — untranslated
       in all six locales, capitalised by CSS. §7.2 asks the strip for "read-only
       state", and this was the enum, not a state a driver reads. DRIVING is already
       visible without being named: the type scale steps up, the Map becomes the
       corridor, acting controls withdraw. A word for the state the app is in is the
       app talking about itself.
     · THE MIC had never had a handler. Its own note said so — six sessions of every
       screen carrying a control that did nothing — and it was left `disabled` as the
       honest version of that. Honest, but a permanently dead control on all thirteen
       driver screens is clutter with a good excuse. The working affordance is the Map
       surface's voice chip; a GLOBAL one needs the voice sheet mounted at app level,
       which is M11's to build. Labelled, never linked (§23's registry precedent) —
       and a thing that is not there needs no label at all.

     What remains is genuinely conditional, so the strip now renders NOTHING when the
     driver is online with nothing queued — which is almost always. That is ~56 dp
     returned to every screen in the app, and on the Map it is 56 dp of map.
     Owner-requested (§23 entry 89). -->
<script setup>
import { computed, ref } from "vue";
import { WifiOff, CloudOff, AlertTriangle, RefreshCw, Download, X } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { updateReady, applyUpdate } from "../pwa.js";
import { offerInstall, manualInstall, promptInstall, dismissInstall } from "../install.js";
import BottomSheet from "./BottomSheet.vue";
import InstallSheet from "./InstallSheet.vue";

const props = defineProps({
  online: { type: Boolean, default: true },
  pending: { type: Number, default: 0 },
  failed: { type: Number, default: 0 },
});
const { t } = useI18n();
const iosSheet = ref(false);
// the strip is for facts a driver cannot see anywhere else. All three of these are
// invisible without it, and none of them is true most of the time.
// AI-CONTEXT: a waiting build is the fourth fact this strip carries (§23 entry 143).
//
// It belongs HERE and not in a toast or a notification: §8 reserves toasts for
// confirmations and routes "persistent conditions" to this strip, and a notification
// would spend §13.1's budget — two per driver per day — on the app talking about
// itself. It is also, like the other three, almost never true.
const hasSomethingToSay = computed(
  () => !props.online || props.pending > 0 || props.failed > 0 || updateReady.value,
);

// AI-CONTEXT: the install offer YIELDS to everything else on this strip (§23 entry 152).
//
// Offline, queued writes, a refused write and a waiting build are all facts about the
// work in front of the driver right now. An offer to install is the only thing this
// strip can carry that can wait, and it is the only one that is true for weeks rather
// than minutes. So it renders only when the strip would otherwise be silent.
//
// That is not merely deference, it is what keeps LAW 0 satisfiable: "Offline —
// everything saves to your phone" plus a second label plus an action word plus a
// dismiss does not fit 360 dp in six locales, and the alternative to a rule here is a
// clipped string in Russian that no screenshot in this repo would have caught.
const showInstall = computed(() => offerInstall.value && !hasSomethingToSay.value);

async function onInstall() {
  // iOS cannot be prompted — Safari fires no event and exposes no API — so the sheet
  // showing the Share gesture IS the install path there, not a fallback from one.
  if (manualInstall.value) {
    iosSheet.value = true;
    return;
  }
  await promptInstall();
}
</script>

<template>
  <header v-if="hasSomethingToSay || showInstall" class="strip">
    <!-- offline is a calm banner, never red (§15.1) -->
    <span v-if="!online" class="strip__offline">
      <WifiOff :size="16" :stroke-width="2" aria-hidden="true" />
      {{ t("system.offline") }}
    </span>
    <!-- F12: queued captures show a subtle pending glyph (§15.1) -->
    <span v-if="pending > 0" class="strip__pending" :aria-label="t('system.pending')">
      <CloudOff :size="14" :stroke-width="2" aria-hidden="true" />
      {{ pending }}
    </span>
    <!-- AI-CONTEXT: U-07. A write the server refused is NOT pending and must not read as
         pending — the driver was previously shown "synced" over lost evidence. This is
         the one thing on the strip that is not calm, and §15.1's "offline is never red"
         does not cover it: offline is a condition that resolves itself, and this does
         not. §15.4 requires a failed money-moving action to be explicit and persistent.
         --flare-500 is the existing semantic token for that; no new colour, no new
         pattern — the same icon-plus-count shape the pending glyph already uses. -->
    <span v-if="failed > 0" class="strip__failed" :aria-label="t('system.failed')">
      <AlertTriangle :size="14" :stroke-width="2" aria-hidden="true" />
      {{ failed }}
    </span>
    <!-- the driver decides WHEN. It never reloads under someone photographing a BOL,
         which is the one thing an auto-updating shell must not do. -->
    <button v-if="updateReady" class="strip__update" type="button" @click="applyUpdate">
      <RefreshCw :size="14" :stroke-width="2" aria-hidden="true" />
      {{ t("system.update_ready") }}
      <span class="strip__updatego">{{ t("system.update_apply") }}</span>
    </button>
    <!-- AI-CONTEXT: the app asking to be installed, for the first time (§23 entry 152).
         The app has satisfied every installability rule since entry 143 and nothing in
         it had ever handled `beforeinstallprompt` — the event the browser fires to hand
         the app the right to ask. It is a strip and not a notification for entry 143's
         reason: §13.1's budget is for reaching a driver, never for the app talking
         about itself. It is dismissible because "install me" is an offer, not a
         condition, and §15.5's rule for the one thing this strip cannot resolve on its
         own is "never nags beyond that card". Dismissing silences the strip forever;
         the More tab keeps the same offer permanently, so nothing is lost by tapping ×. -->
    <button v-if="showInstall" class="strip__install" type="button" @click="onInstall">
      <Download :size="14" :stroke-width="2" aria-hidden="true" />
      {{ t("install.offer") }}
      <span class="strip__installgo">{{ t("install.action") }}</span>
    </button>
    <button
      v-if="showInstall"
      class="strip__dismiss"
      type="button"
      :aria-label="t('install.dismiss')"
      @click="dismissInstall"
    >
      <X :size="14" :stroke-width="2" aria-hidden="true" />
    </button>
  </header>
  <BottomSheet :open="iosSheet" :title="t('install.title')" @close="iosSheet = false">
    <InstallSheet />
  </BottomSheet>
</template>

<style scoped>
.strip {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 32px;
  padding: var(--s-1) var(--s-4);
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
/* §6.5's floor does not apply to the 32 dp strip — §7.2 fixes its height — so this is
   the one control in the app that cannot be 48 dp. It gains the whole strip's width
   instead: `margin-left: auto` puts it in the corner the thumb reaches, and the label
   is two words rather than an icon so the target is the text, not the glyph. */
.strip__update {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  margin-left: auto;
  padding: 0;
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-caption-size);
  font-weight: 500;
}
.strip__updatego {
  text-decoration: underline;
}
/* AI-CONTEXT: §6.5's 48 dp floor is MET here, and that is a deliberate difference from
   `.strip__update` above (§23 entry 152).
 *
 * That control is excused because it renders in no layout state — the harness cannot
 * reach module state a real service worker sets, recorded as a known gap in entry 143.
 * The install offer DOES get a layout state, so the sweep measures these two, and the
 * honest way to pass a check is to satisfy it rather than to add a name to
 * `TARGET_EXEMPT`. The strip's 32 dp is a `min-height`, so the row simply grows to 48
 * in the one case this is visible — and it is visible only when the strip is otherwise
 * empty, so nothing else on any screen moves. These are also exactly the taps §6.5 is
 * about: a gloved thumb choosing "add it" or "not now" at a fuel island. */
.strip__install {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  min-height: 48px;
  padding: 0;
  background: transparent;
  color: var(--shield-500);
  font-size: var(--type-caption-size);
  font-weight: 500;
}
.strip__installgo {
  text-decoration: underline;
}
.strip__dismiss {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: auto;
  min-width: 48px;
  min-height: 48px;
  padding: 0;
  background: transparent;
  color: var(--text-3);
}
.strip__offline {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  color: var(--text-2);
}
.strip__pending {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
}
.strip__failed {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
  color: var(--flare-500);
  font-variant-numeric: tabular-nums;
}
</style>
