// AI-CONTEXT: the two rules every skeleton obeys, in ONE place (§23 entry 131).
//
// Both of these are easy to state and easy to forget at a call site, and a skeleton
// that forgets either is worse than no skeleton at all. So they live in the gate
// rather than in the surfaces: a surface says `v-if="state === 'loading'"` and cannot
// opt out of them.
//
// 1. THE DELAY. A skeleton that flashes is worse than a brief blank — it reads as a
//    glitch rather than as progress. Nothing renders for the first 200 ms, so a fast
//    local response never shows one at all.
//
// 2. NO SKELETON WHILE DRIVING. A skeleton is a promise that content is coming, which
//    is a reason to keep looking at a screen. At speed the surface withdraws (SM-3)
//    and says so with the existing `driving.paused` line. This is the rule most likely
//    to be lost in a copy-paste, which is exactly why it is not at the call site.
import { ref, computed, onUnmounted } from "vue";
import { useDriverState } from "./state.js";

// one constant, not six copies (§23 entry 131)
export const SKELETON_DELAY_MS = 200;

/* AI-CONTEXT: THE DELAY HIDES THE SKELETON — IT MUST NOT REMOVE ITS BOX (§23 entry 160).
 *
 * The rule above is right and its implementation had the opposite effect. `v-if` on the
 * delayed flag meant the skeleton rendered NO DOM AT ALL for the first 200 ms, so any
 * response faster than that — every local one, and most on a working connection —
 * produced a zero-height hole that then popped to full height. The delay written to stop
 * skeletons FLASHING is what made content JUMP.
 *
 * MEASURED on a tab switch with a working API, sampling every animation frame:
 *   Money   10 ms  headings only
 *           44 ms  "Recovered and saved money shows up here…"
 *           80 ms  "Owed to you $0.00 · Paid to you $0.00 · Fuel saved…"
 * Three different screens in 80 ms, each a different height. That is the flicker the
 * owner reported as "showing something different and coming back".
 *
 * So the gate returns TWO things now, and the distinction is the whole fix:
 *   · `reserve` — render the skeleton's BOX from the first frame, so the section already
 *     has its final height and the content arrives in place instead of shoving the page.
 *   · `visible` — paint its fill only after the delay, so a fast response never shows a
 *     skeleton at all. Same anti-flash promise, kept by opacity rather than by absence.
 *
 * DRIVING still renders nothing, box included: §15.2's withdrawal is not "an invisible
 * skeleton", it is no skeleton, and reserving space for one would leave a hole on a
 * screen that has deliberately stopped asking for attention.
 */
export function useSkeletonGate() {
  const waited = ref(false);
  const { isDriving } = useDriverState();
  const timer = setTimeout(() => {
    waited.value = true;
  }, SKELETON_DELAY_MS);
  onUnmounted(() => clearTimeout(timer));
  return {
    reserve: computed(() => !isDriving.value),
    visible: computed(() => waited.value && !isDriving.value),
  };
}
