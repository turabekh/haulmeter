<!-- AI-CONTEXT: §8's card, with no content in it (§23 entry 131).

     §8 says skeletons MIRROR THE REAL LAYOUT, so this is not a generic grey box: it is
     the same `--ink-1` fill, the same hairline `--line-1`, the same `--r-card` and the
     same `--s-4` padding every card on Money, Load, Audit and Fleet already uses. A
     skeleton whose shape differs from what replaces it produces a visible jump, which
     is a state change communicated badly (§6.4).

     STATIC. §6.4 forbids looping ambient motion outright, and a shimmer would also
     compete with The Meter for the one living element on the screen. `prefers-reduced-
     motion` therefore needs no branch here — there is no motion to reduce.

     `aria-hidden`: the blocks carry no information a screen-reader user can act on.
     Announcing "rectangle, rectangle" is noise, not access. -->
<script setup>
import { useSkeletonGate } from "../skeleton.js";

defineProps({
  count: { type: Number, default: 1 },
});
const visible = useSkeletonGate();
</script>

<template>
  <div v-if="visible" class="skel" aria-hidden="true">
    <div v-for="n in count" :key="n" class="skel__card">
      <span class="skel__line skel__line--title"></span>
      <span class="skel__line skel__line--figure"></span>
    </div>
  </div>
</template>

<style scoped>
.skel {
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
.skel__card {
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  padding: var(--s-4);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.skel__line {
  display: block;
  background: var(--line-1);
  border-radius: var(--r-control);
}
/* the two lines a card leads with: a title, then the figure under it (§8, §9) */
.skel__line--title {
  width: 60%;
  height: var(--type-title-line);
}
.skel__line--figure {
  width: 40%;
  height: var(--type-display-line);
}
</style>
