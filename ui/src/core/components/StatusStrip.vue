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
import { computed } from "vue";
import { WifiOff, CloudOff, AlertTriangle } from "lucide-vue-next";
import { useI18n } from "../i18n.js";

const props = defineProps({
  online: { type: Boolean, default: true },
  pending: { type: Number, default: 0 },
  failed: { type: Number, default: 0 },
});
const { t } = useI18n();
// the strip is for facts a driver cannot see anywhere else. All three of these are
// invisible without it, and none of them is true most of the time.
const hasSomethingToSay = computed(
  () => !props.online || props.pending > 0 || props.failed > 0,
);
</script>

<template>
  <header v-if="hasSomethingToSay" class="strip">
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
  </header>
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
