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
const visible = useSkeletonGate();
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
.skel__puck {
  width: 28px; /* the puck inside it, same as `.pin__puck` */
  height: 28px;
  border-radius: var(--r-pill);
  background: var(--line-1);
  border: 1px solid var(--line-1);
}
</style>
