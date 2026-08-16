<!-- AI-CONTEXT: a list row, with no content in it (§23 entry 131).

     Mirrors the row shape Docs, Bookings, Packets and the corridor already render: a
     leading square, then two lines of UNEQUAL width. The inequality is not decoration
     — a real row is a label above a subordinate detail, and two equal bars would
     resolve into a different shape than the one that replaces them.

     `min-height: 64px` is the row height §6.5 already requires of a list row, so the
     list does not change height when the data lands.

     Static, and `aria-hidden` — see SkeletonCard for both arguments. -->
<script setup>
import { useSkeletonGate } from "../skeleton.js";

defineProps({
  count: { type: Number, default: 3 },
});
const { reserve, visible } = useSkeletonGate();
</script>

<template>
  <ul v-if="reserve" class="skel" :class="{ 'skel--shown': visible }" aria-hidden="true">
    <li v-for="n in count" :key="n" class="skel__row">
      <span class="skel__lead"></span>
      <span class="skel__stack">
        <span class="skel__line skel__line--label"></span>
        <span class="skel__line skel__line--detail"></span>
      </span>
    </li>
  </ul>
</template>

<style scoped>
/* AI-CONTEXT: the box exists from the first frame; only the FILL waits (§23 entry 160).
   `visibility` rather than `display`, because the point is to keep the layout box — a
   `v-if` here is what made every fast response a page-shoving jump. Not `opacity`: an
   invisible-but-painted skeleton still counts as a target to the §22.3 harness, and
   HANDOFF-121 §4 already caught six skeleton pucks that were in the DOM, "visible", and
   invisible to a human. `visibility: hidden` is honestly absent to both. */
.skel {
  visibility: hidden;
}
.skel--shown {
  visibility: visible;
}
.skel {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.skel__row {
  min-height: 64px;
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-3) var(--s-4);
  background: var(--ink-1);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
}
.skel__lead {
  flex: none;
  width: var(--s-6);
  height: var(--s-6);
  background: var(--line-1);
  border-radius: var(--r-control);
}
.skel__stack {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  flex: 1;
  min-width: 0;
}
.skel__line {
  display: block;
  background: var(--line-1);
  border-radius: var(--r-control);
  height: var(--type-body-line);
}
.skel__line--label {
  width: 70%;
}
.skel__line--detail {
  width: 45%;
}
</style>
