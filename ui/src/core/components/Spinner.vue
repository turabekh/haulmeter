<!-- AI-CONTEXT: §8's button loading state, built for the first time (owner request,
     2026-08-11).

     "Buttons: ... Loading state = inline spinner replacing label, width locked." That
     sentence has been in the design constitution since it was written and NOTHING in
     this product implemented it. Roughly a dozen buttons already held a `busy` ref and
     already set `:disabled` — so the guard existed and the FEEDBACK did not: a driver
     tapping Send on a dock with two bars watched a button that looked exactly like an
     untapped button, which is the state that teaches someone to tap it again.

     WHY IT IS `aria-hidden` AND NOT THE ONLY SIGNAL. §16: status is never colour alone,
     and never motion alone either — a spinner is invisible to a screen reader and to
     anyone who has turned motion off. The button's LABEL changes to a localized busy
     word beside it, and `:disabled` is what assistive tech actually announces. The
     spinner is the fast visual confirmation for the driver watching the screen; the
     label is the one that survives every other way of using this app.

     REDUCED MOTION (§6.4 — calm, physical, skippable): the ring stops rotating and
     holds a static three-quarter arc. It still reads as "not a normal button" because
     of the gap in the ring, so the state remains visible rather than disappearing for
     the people who most need it not to move.

     `currentColor`, deliberately. This renders inside a filled Primary (`--on-accent`),
     a tertiary text control (`--shield-500`) and a destructive confirm (`--on-accent`
     on flare) — three different foregrounds. Inheriting means no new colour token and
     no per-button variant, which is §22.2's "remove rather than add" applied to CSS. -->
<script setup>
defineProps({
  // matches the 16 dp icons already used inside labels; `size` exists because the
  // tertiary row runs at label size and a 20 dp ring there would out-weigh its own text.
  size: { type: Number, default: 16 },
});
</script>

<template>
  <span
    class="spin"
    :style="{ width: `${size}px`, height: `${size}px` }"
    aria-hidden="true"
  ></span>
</template>

<style scoped>
.spin {
  display: inline-block;
  flex: none;
  /* it always precedes a label, so the gap belongs to the spinner rather than to each
     of the ~35 buttons that render one. `middle` because most of these buttons are not
     flex containers — a small circle on the text baseline sits visibly low. */
  vertical-align: middle;
  margin-inline-end: var(--s-1);
  border-radius: 50%;
  /* the ring is the foreground at low opacity; the ARC is the foreground itself, so the
     shape reads on any of the three backgrounds this lands on without a second token. */
  border: 2px solid color-mix(in srgb, currentColor 30%, transparent);
  border-top-color: currentColor;
  animation: spin-rotate 800ms linear infinite;
}
@keyframes spin-rotate {
  to {
    transform: rotate(360deg);
  }
}
/* §6.4: motion is skippable. The arc stays — a full even ring would read as a disabled
   dot rather than as work in progress. */
@media (prefers-reduced-motion: reduce) {
  .spin {
    animation: none;
    transform: rotate(45deg);
  }
}
</style>
