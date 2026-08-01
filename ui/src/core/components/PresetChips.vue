<!-- AI-CONTEXT: Map presets (design-prd §11.3) — presets ARE the interface, not
     filters. Scrollable chip row at the top of the Map surface. One "More filters"
     sheet exists elsewhere; these five are the interface.

     AI-CONTEXT: ICONS, not words — owner-requested, logged as §23 entry 89.
     Three things that decision has to survive, each handled here rather than hoped for:

     · MEANING. The icons are not chosen freshly. Three of the five are the SAME glyphs
       the map already draws on its pins (Warehouse = shipper_receiver, Fuel =
       fuel_station, UtensilsCrossed = the food badge), so a chip and the pins it
       reveals now say the same thing. That shared vocabulary is the only reason an
       icon can carry a word's meaning at all.
     · THE NAME IS NOT LOST. Every chip keeps its translated name as `aria-label` and
       as `title`, so a screen reader and a long-press both still say "Tonight". Six
       locales keep working; the icons simply stop needing translation.
     · C-1. Colour may never be the only signal. A text chip could lean on it because
       the LABEL carried the meaning; an icon chip cannot. Selection is now a FILL — a
       shape and weight change, not a hue change — plus `aria-selected`, so the pressed
       chip is obvious with no colour perception at all.

     Density is the point: five 48 dp squares instead of five text pills, in a row
     56 dp tall rather than 64. -->
<script setup>
import { Navigation, Moon, Warehouse, Fuel, UtensilsCrossed, Wrench } from "lucide-vue-next";
import { useI18n } from "../i18n.js";

const props = defineProps({
  modelValue: { type: String, default: "drive" },
});
const emit = defineEmits(["update:modelValue"]);
const { t } = useI18n();
// M13 / §23 E-D2: "Food" joins the four §11.3 presets as an approved addition. The row
// already scrolls horizontally, so a fifth chip costs nothing at 360 dp. (NAV-1 governs
// TABS and is untouched: this is a filter row, not navigation.)
const presets = [
  { key: "drive", label: "map.preset.drive", icon: Navigation },
  { key: "tonight", label: "map.preset.tonight", icon: Moon },
  { key: "work", label: "map.preset.work", icon: Warehouse },
  { key: "fuel", label: "map.preset.fuel", icon: Fuel },
  { key: "food", label: "map.preset.food", icon: UtensilsCrossed },
  // A5 / §23 E-D2's precedent again: drivers asked for repair shops, tire shops and
  // "other entities that may help". NAV-1 governs TABS and is untouched — this row is
  // a filter, and it already scrolls, so a sixth chip costs nothing at 360 dp. Wrench
  // is the glyph the map already draws on a `repair` pin, so the chip and the pins it
  // reveals say the same thing (the shared-vocabulary rule above).
  { key: "service", label: "map.preset.service", icon: Wrench },
];
</script>

<template>
  <div class="chips" role="tablist" aria-label="Map presets">
    <button
      v-for="p in presets"
      :key="p.key"
      type="button"
      class="chip"
      :class="{ 'chip--active': modelValue === p.key }"
      role="tab"
      :aria-selected="modelValue === p.key"
      :aria-label="t(p.label)"
      :title="t(p.label)"
      @click="emit('update:modelValue', p.key)"
    >
      <component :is="p.icon" :size="22" :stroke-width="2" aria-hidden="true" />
    </button>
  </div>
</template>

<style scoped>
.chips {
  display: flex;
  /* AI-CONTEXT: SPREAD, not packed. Five 48 dp squares left-aligned with an 8 dp gap
     left a third of the row empty on the right and read as crowded rather than
     dense — the owner's word was "squished". `space-between` distributes the 88 dp
     of slack into four 22 dp gaps, so the row uses the width it occupies.
     `gap` stays as the floor for the case `space-between` cannot help: a narrower
     viewport, where the row scrolls instead.
     And 12 dp above and below rather than 4 — the strip that used to sit above this
     row is gone (§23 entry 89), so these chips are now the topmost thing on the
     screen and need the breathing room it used to provide. Still 56 dp cheaper than
     strip-plus-row was. */
  justify-content: space-between;
  gap: var(--s-2);
  overflow-x: auto;
  padding: var(--s-3) var(--s-4);
  scrollbar-width: none;
}
.chips::-webkit-scrollbar {
  display: none;
}
.chip {
  flex: 0 0 auto;
  /* §6.5 glove spec floor, in BOTH axes. A text chip was as wide as its label; an
     icon chip is only as wide as it is told to be, so the width is declared. */
  min-height: 48px;
  min-width: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-1);
  background: var(--ink-1);
  color: var(--text-2);
}
/* C-1: selection is a FILL, not a hue — legible with no colour perception at all. */
.chip--active {
  border-color: var(--accent-fill);
  background: var(--accent-fill);
  color: var(--on-accent);
}
</style>
