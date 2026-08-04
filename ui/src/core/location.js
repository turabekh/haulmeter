// AI-CONTEXT: the client half of F3, which had never existed.
//
// F3's server side has been complete since the Foundation — geofence evaluation,
// ENTER/EXIT/DWELL_TICK, clock-skew recording, trace storage — and nothing in the app
// ever sent it a position. The only `evaluate_ping` call in application code was
// `POST /load/{stop}/arrive` passing the FACILITY'S OWN coordinates, so the running
// product could produce an ENTER and could never produce an EXIT. Everything
// downstream of EXIT was quietly computing over nothing: F3's dwell pairing walks
// ENTER->EXIT, so M2's dwell statistics had no samples, and M3's departure was always
// null. Measured before this was written: every facility a real driver had touched
// carried ENTER and zero EXIT.
//
// This module is the sensor. It is in `core/` because that is where business logic
// lives (§19) — the UI layer only reads its refs.
//
// ADAPTIVE SAMPLING is PRD §7.3's, and it is a battery budget (≤5%/day) rather than a
// preference: significant-change while the driver is just driving, high-accuracy only
// while a stop is armed, which is exactly when a wrong boundary crossing costs money.
import { ref } from "vue";
import { sendLocationPing, isAuthenticated, activeStopId } from "./api.js";
import { observeMotion, observePresence } from "./state.js";

// how far and how often a fix has to move before it is worth a request. The armed
// numbers are tighter because that is when ±3 minutes of arrival detection (PRD §7.3)
// is being judged; the idle numbers exist to keep the radio asleep.
const IDLE_MIN_METERS = 250;
const IDLE_MIN_MS = 5 * 60 * 1000;
const ARMED_MIN_METERS = 50;
const ARMED_MIN_MS = 60 * 1000;

// AI-CONTEXT: how far apart two fixes must be before they describe a DIRECTION.
//
// A parked truck has no heading, and GPS jitter at a standstill is a few metres in a
// random direction every second — so deriving a bearing from every pair would spin
// the corridor through all four quadrants while the driver sits at a dock. Below this
// the last known heading is kept instead, on the same reasoning `effectiveSpeed`
// already applies to a missing speed: an unknown reading is not evidence of a change.
const MIN_HEADING_METERS = 15;

// §15.5: "if background permission is lost, the app shows a single persistent
// Load-tab card explaining exactly what stops working, with a one-tap fix — never
// nags beyond that card." This ref is that card's whole state.
//   unknown  — not asked yet
//   granted  — positions are flowing
//   denied   — the driver said no, or the OS revoked it
//   unavailable — no geolocation at all (desktop browser, hardware off)
export const permission = ref("unknown");
export const lastFix = ref(null);
// the events the server reported for our own movement, newest last. A surface can
// watch this to react to an EXIT without polling the meter.
export const lastEvents = ref([]);

let watchId = null;
let lastFixAt = null;
let watchedHighAccuracy = null;
let lastSentAt = 0;
let lastSentAt_lat = null;
let lastSentAt_lon = null;
// the last heading we were able to establish, held across fixes that cannot supply
// one (a red light, a dock, a device that never reports `coords.heading`)
let lastHeading = null;

// equirectangular approximation — a few metres of error over the distances that
// matter here, and it avoids a trig-heavy haversine on every single fix.
export function metersBetween(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = Math.PI / 180;
  const x = (lon2 - lon1) * toRad * Math.cos(((lat1 + lat2) / 2) * toRad);
  const y = (lat2 - lat1) * toRad;
  return Math.sqrt(x * x + y * y) * R;
}

// initial bearing from one point to another, degrees clockwise from true north —
// the same convention `coords.heading` uses and the same one F11's corridor cone is
// measured in, so a derived heading and a device-reported one are interchangeable.
export function bearingBetween(lat1, lon1, lat2, lon2) {
  const toRad = Math.PI / 180;
  const phi1 = lat1 * toRad;
  const phi2 = lat2 * toRad;
  const dLon = (lon2 - lon1) * toRad;
  const y = Math.sin(dLon) * Math.cos(phi2);
  const x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLon);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

function armed() {
  return !!activeStopId.value;
}

export function samplingMode() {
  return armed() ? "high_accuracy" : "significant_change";
}

// AI-CONTEXT: the throttle is what makes this a sampler rather than a firehose.
// `watchPosition` fires as often as the OS pleases; without this the app would POST
// on every fix and spend the battery budget in an afternoon.
export function shouldSend(fix, now) {
  const minMs = armed() ? ARMED_MIN_MS : IDLE_MIN_MS;
  const minM = armed() ? ARMED_MIN_METERS : IDLE_MIN_METERS;
  if (lastSentAt_lat === null) return true; // the first fix always goes
  if (now - lastSentAt >= minMs) return true;
  return metersBetween(lastSentAt_lat, lastSentAt_lon, fix.lat, fix.lon) >= minM;
}

// AI-CONTEXT: many devices report `coords.speed` as null — desktop browsers always,
// phones often on the first fix — and §5's DRIVING trigger is a speed. Deriving it
// from displacement over elapsed time keeps the state machine alive on those devices
// instead of leaving every driver permanently IDLE, which is the failure this whole
// deriver exists to end.
function effectiveSpeed(coords, fix, now) {
  if (typeof coords.speed === "number" && !Number.isNaN(coords.speed)) return coords.speed;
  const prev = lastFix.value;
  if (!prev || !lastFixAt) return null;
  const seconds = (now - lastFixAt) / 1000;
  if (seconds <= 0) return null;
  return metersBetween(prev.lat, prev.lon, fix.lat, fix.lon) / seconds;
}

// AI-CONTEXT: WHICH WAY THE TRUCK IS POINTING, which this sensor never recorded.
//
// `coords.heading` was dropped on the floor along with any way to derive one, so the
// only heading in the product was the literal `0` two API calls defaulted to — due
// north. A driver westbound on I-40 was served the scales and the food NORTH of them,
// and `GET /map/corridor`, which requires a heading, was never called at all: there
// was nothing to pass it. Corridor mode ran on a fixture instead.
//
// Devices report `heading` as null or NaN whenever they cannot establish one, which
// on many phones is most of the time, so displacement between fixes is the fallback —
// the same shape as `effectiveSpeed` above, for the same reason.
function effectiveHeading(coords, fix) {
  if (typeof coords.heading === "number" && !Number.isNaN(coords.heading)) return coords.heading;
  const prev = lastFix.value;
  if (!prev) return lastHeading;
  if (metersBetween(prev.lat, prev.lon, fix.lat, fix.lon) < MIN_HEADING_METERS) return lastHeading;
  return bearingBetween(prev.lat, prev.lon, fix.lat, fix.lon);
}

async function onFix(position) {
  permission.value = "granted";
  const now = Date.now();
  const fix = {
    lat: position.coords.latitude,
    lon: position.coords.longitude,
    accuracyM: position.coords.accuracy ?? null,
    speedMps: position.coords.speed ?? null,
  };
  // both derivations read the PREVIOUS fix, so they run before it is replaced below
  fix.headingDeg = effectiveHeading(position.coords, fix);
  lastHeading = fix.headingDeg;
  // SM-4: the state machine owns the decision; this only hands it the reading.
  observeMotion({ speedMps: effectiveSpeed(position.coords, fix, now), now });
  lastFixAt = now;
  lastFix.value = fix;
  // arming can change between fixes (the driver starts a load), and the watch has to
  // be re-opened to change accuracy — the browser fixes options at watch time
  if (watchedHighAccuracy !== armed()) restart();
  if (!isAuthenticated.value || !shouldSend(fix, now)) return;
  // AI-CONTEXT: the throttle is claimed BEFORE the await, not after it.
  //
  // Recording it on success meant every fix arriving while the first request was
  // still in flight also passed `shouldSend` — so a burst of fixes became a burst of
  // POSTs, which is precisely what the battery budget exists to stop. Claiming it on
  // ATTEMPT also means a failed send does not immediately retry against a network
  // that is already down; the next fix simply tries again on its own schedule.
  lastSentAt = now;
  lastSentAt_lat = fix.lat;
  lastSentAt_lon = fix.lon;
  try {
    const res = await sendLocationPing({ ...fix, mode: samplingMode() });
    // §5's ON_SITE is "inside an armed stop's geofence", and the server is the only
    // thing that knows: geofence radii live in F2 and the evaluation in F3. Every
    // ping now answers it as a STATE rather than only as a crossing — the edges below
    // fire once and are gone, so a client that listened only for them lost ON_SITE on
    // the next reload and could never get it back.
    if (res && typeof res.present === "boolean") observePresence(res.present);
    if (res && res.events && res.events.length) {
      lastEvents.value = res.events;
      // the edges still run: they are what an EXIT-driven surface reacts to, and they
      // arrive in the same response that just settled the state above.
      for (const event of res.events) {
        if (event.event_type === "ENTER") observeMotion({ present: true });
        if (event.event_type === "EXIT") observeMotion({ present: false });
      }
    }
  } catch {
    // offline, or the session expired. Deliberately NOT queued — see
    // api.js sendLocationPing: a replayed position is evaluated at server-now and
    // would fabricate a boundary crossing.
  }
}

function onError(err) {
  // 1 = PERMISSION_DENIED in the W3C geolocation spec. The other codes (position
  // unavailable, timeout) are transient and must not light up §15.5's card — that
  // card is for a permission the driver has to restore, not for a bad sky view.
  if (err && err.code === 1) permission.value = "denied";
}

function restart() {
  stopLocationReporting();
  startLocationReporting();
}

export function startLocationReporting() {
  if (typeof navigator === "undefined" || !navigator.geolocation) {
    permission.value = "unavailable";
    return;
  }
  if (watchId !== null) return;
  watchedHighAccuracy = armed();
  watchId = navigator.geolocation.watchPosition(onFix, onError, {
    enableHighAccuracy: watchedHighAccuracy,
    maximumAge: watchedHighAccuracy ? 0 : IDLE_MIN_MS,
    timeout: 30000,
  });
}

export function stopLocationReporting() {
  if (watchId !== null && typeof navigator !== "undefined" && navigator.geolocation) {
    navigator.geolocation.clearWatch(watchId);
  }
  watchId = null;
}

// the §15.5 "one-tap fix". A page cannot open the OS settings screen, so the honest
// action is to ask again — which is what re-arming the watch does, and what a
// Capacitor build will route to the system prompt.
export function retryLocationPermission() {
  permission.value = "unknown";
  restart();
}

// test seam: the throttle keeps module state, and a suite that does not reset it
// reads the previous test's last position.
export function __resetForTests() {
  stopLocationReporting();
  lastFixAt = null;
  lastSentAt = 0;
  lastSentAt_lat = null;
  lastSentAt_lon = null;
  lastHeading = null;
  permission.value = "unknown";
  lastFix.value = null;
  lastEvents.value = [];
}
