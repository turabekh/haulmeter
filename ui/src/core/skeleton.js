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

export function useSkeletonGate() {
  const waited = ref(false);
  const { isDriving } = useDriverState();
  const timer = setTimeout(() => {
    waited.value = true;
  }, SKELETON_DELAY_MS);
  onUnmounted(() => clearTimeout(timer));
  return computed(() => waited.value && !isDriving.value);
}
