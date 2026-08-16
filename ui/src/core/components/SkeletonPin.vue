<!-- AI-CONTEXT: the map's loading shape (§23 entry 131), and the one that closes U-10.

     This is what the map renders instead of `SAMPLE_PINS` — the defect where every
     cold app open drew fabricated truck stops until `/map/overlay` answered. A driver
     could route to one.

     NO STATUS COLOUR, deliberately and non-negotiably. §11.1 puts the signal on the
     pin's fill, so a coloured skeleton pin would be asserting parking availability
     that no reading supports — which is the §11.7 defect this whole entry exists to
     end, rebuilt in the fix for it. The puck is `--line-1`, the same neutral every
     other skeleton uses, and it carries no badge and no price.

     44 dp is §11.2's map hit area, matching `.pin` so the field does not reflow when
     the real pins land. It is a `<span>`, not a button: there is nothing to tap yet,
     and an inert control is worse than an absent one.

     Static, and `aria-hidden` — see SkeletonCard. -->
<script setup>
import { useSkeletonGate } from "../skeleton.js";

defineProps({
  count: { type: Number, default: 6 },
});
// AI-CONTEXT: pins take `visible` only, and skip `reserve` DELIBERATELY (§23 entry 160).
// The card and row skeletons reserve a layout box so content cannot shove the page; a
// map pin is absolutely positioned over the canvas and occupies no flow, so there is
// nothing to reserve and an always-present invisible puck would only add DOM the §22.3
// harness has to reason about.
const { visible } = useSkeletonGate();
</script>

<template>
  <div v-if="visible" class="skel" aria-hidden="true">
    <span v-for="n in count" :key="n" class="skel__pin">
      <span class="skel__puck"></span>
    </span>
  </div>
</template>

<style scoped>
.skel {
  display: flex;
  flex-wrap: wrap;
  align-content: flex-start;
  gap: var(--s-4);
}
.skel__pin {
  width: 44px; /* §11.2: the map hit area `.pin` uses */
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
/* AI-CONTEXT: `--on-accent` here, and it was a DEFECT that got this far.
 *
 * The first version filled with `--line-1`, matching SkeletonCard and SkeletonRow. That
 * is right on a CARD and wrong on a MAP: dark `--line-1` is #2A3644 against a night
 * basemap of roughly the same value, so the pucks were in the DOM, `visibility: visible`,
 * counted by the harness — and invisible to a human. `--ink-1` (#151C24) would have been
 * worse. Caught by throttling the network and LOOKING at the screen, which is the one
 * instruction the kickoff repeated twice; every automated check passed over it.
 *
 * `--on-accent` is theme-invariant white, and §23 entry 130 recorded that invariance as
 * load-bearing for this exact surface: `.pin--stale` fills with it because "a fill that
 * darkened with the theme would make a stale pin read as a filled one". A skeleton pin
 * has the same requirement — legible over both basemaps, carrying no status.
 *
 * It does not collide with `.pin--stale`, which is a white puck with a COLOURED ring and
 * a glyph. This is a white puck with a neutral ring and nothing inside it. */
.skel__puck {
  width: 28px; /* the puck inside it, same as `.pin__puck` */
  height: 28px;
  border-radius: var(--r-pill);
  background: var(--on-accent);
  border: 1px solid var(--line-1);
}
</style>
