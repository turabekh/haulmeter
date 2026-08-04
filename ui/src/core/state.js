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
  if (state.value === next) return;
  state.value = next;
  const root = document.documentElement;
  if (next === DriverState.DRIVING) root.setAttribute("data-state", "driving");
  else root.removeAttribute("data-state");
}

// AI-CONTEXT: THE DERIVER — the half of §5 that never existed (§23 entry 61).
//
// This file's own header has said "state is derived from F3 motion/geofence signals"
// since it was written, and nothing derived anything: `setState` was called from
// tests and from no other line in the app. So DriverState was permanently IDLE in
// production and EVERY DRIVING behaviour in the product was unreachable — §10.2's
// Meter-only glance, §11.4 Corridor mode, §10.3's read-only Money, §10.4's inspection
// confirm, and the withdrawal guards on seven surfaces. All correct, all inert.
//
// It is buildable now because F3 grew an inbound seam this session: `/location/ping`
// carries `speed_mps`, so "sustained motion above walking speed" finally has an input.
//
// SM-4 puts the logic here and nowhere else; `core/location.js` senses and calls in,
// which keeps the dependency one-way (location -> state) and leaves every screen a
// reader.

// §5's trigger is "above WALKING speed". Brisk walking is ~1.8 m/s and a jog ~3;
// 2.5 m/s (~5.6 mph) sits above walking without waiting for highway speed, because a
// truck crawling out of a yard is already driving.
export const WALKING_SPEED_MPS = 2.5;
// "SUSTAINED" is the other half of the trigger, and the reason there are two
// thresholds is SM-1: transitions must be calm. One GPS spike must not flip the app
// into glance mode, and a red light must not flip it back out — leaving takes longer
// than entering, so a stop-and-go mile does not strobe the type scale.
export const DRIVING_SUSTAIN_MS = 60_000;
export const STOPPED_SUSTAIN_MS = 90_000;

let movingSince = null;
let stoppedSince = null;
let onSite = false;

function settled(next) {
  // DRIVING outranks ON_SITE: a driver rolling through a large geofence is driving,
  // and §5 gives ON_SITE to a truck that has stopped at the dock.
  if (next === DriverState.DRIVING) return setState(DriverState.DRIVING);
  setState(onSite ? DriverState.ON_SITE : DriverState.IDLE);
}

/** Feed one motion sample. `speedMps` may be null when the device does not report it. */
export function observeMotion({ speedMps = null, present = null, now = Date.now() } = {}) {
  if (present !== null) onSite = present;

  // an unknown speed is not evidence of stopping. Holding the current state is the
  // honest response — the alternative silently drops out of glance mode on any device
  // whose geolocation omits `speed`.
  if (speedMps === null || Number.isNaN(speedMps)) {
    if (state.value !== DriverState.DRIVING) settled(state.value);
    return state.value;
  }

  if (speedMps >= WALKING_SPEED_MPS) {
    stoppedSince = null;
    movingSince ??= now;
    if (now - movingSince >= DRIVING_SUSTAIN_MS) settled(DriverState.DRIVING);
    return state.value;
  }

  movingSince = null;
  stoppedSince ??= now;
  if (state.value === DriverState.DRIVING) {
    if (now - stoppedSince >= STOPPED_SUSTAIN_MS) settled(null);
    return state.value;
  }
  settled(null);
  return state.value;
}

/** Feed the CURRENT presence fact — "inside an armed geofence, yes or no".
 *
 * AI-CONTEXT: separate from `observeMotion` because presence and motion arrive from
 * different places on different schedules, and presence used to arrive ONLY as an
 * ENTER edge. `onSite` is module state: a reload set it back to false with no edge
 * left to restore it, and the "I've arrived" fallback never produced an edge at all,
 * so ON_SITE was reachable in tests and effectively unreachable in a truck. Every
 * ping now carries the steady state (`/location/ping` -> `present`).
 *
 * DRIVING still outranks it — SM-1's calm transitions mean a truck rolling through a
 * large yard geofence does not flip to ON_SITE mid-manoeuvre; the next settled motion
 * sample picks the presence up.
 */
export function observePresence(present) {
  onSite = present === true;
  if (state.value === DriverState.DRIVING) return state.value;
  settled(null);
  return state.value;
}

// RESTING is deliberately NOT derived here. §5 triggers it on "stationary >20 min at a
// PARKING-TYPE facility, evening window", and the client has no facility type for the
// place it is sitting in — the ping response names a facility id, not what it is.
// Deriving it from time alone would put the app in RESTING at a receiver at 7pm and
// mute notifications to P0 while a driver waits on a dock. Logged as debt rather than
// guessed.

export function __resetStateForTests() {
  movingSince = null;
  stoppedSince = null;
  onSite = false;
  setState(DriverState.IDLE);
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
