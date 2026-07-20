// AI-CONTEXT: The driver state machine (design-prd §5) lives HERE and nowhere
// else (SM-4). State is derived from F3 motion/geofence signals + time; it
// reshapes what surfaces foreground, never blocks access. DRIVING flips
// glance-mode app-wide by stamping data-state="driving" on the root, which the
// tokens pick up (§6.2 T-1 type bump). Screens read this; they never re-derive it.
import { ref, computed } from "vue";

export const DriverState = {
  IDLE: "idle",
  DRIVING: "driving",
  ON_SITE: "on_site",
  RESTING: "resting",
};

const state = ref(DriverState.IDLE);

function setState(next) {
  state.value = next;
  const root = document.documentElement;
  if (next === DriverState.DRIVING) root.setAttribute("data-state", "driving");
  else root.removeAttribute("data-state");
}

export function useDriverState() {
  return {
    state,
    isDriving: computed(() => state.value === DriverState.DRIVING),
    isResting: computed(() => state.value === DriverState.RESTING),
    isOnSite: computed(() => state.value === DriverState.ON_SITE),
    setState,
  };
}
