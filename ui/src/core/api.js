// AI-CONTEXT: HTTP client for the LONGHAUL API. Base URL is the LOCKED api port
// 8008. Auth is an F1 session bearer token; it persists to localStorage so a
// session survives reload (a phone app the driver doesn't re-log every trip).
// isAuthenticated gates the app (router guard); callers still fall back to
// fixtures when a request fails offline. This module is the ONLY place the UI
// talks to the backend — swap-friendly (§19).
import { ref, computed } from "vue";

export const API_BASE = "http://localhost:8008";
const SESSION_KEY = "longhaul.session";

function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY)) || {};
  } catch {
    return {};
  }
}
const _stored = loadSession();
const token = ref(_stored.token || null);
export const account = ref(_stored.account_id || null);
export const email = ref(_stored.email || null);
export const isAuthenticated = computed(() => !!token.value);

function persist() {
  try {
    if (token.value) {
      localStorage.setItem(
        SESSION_KEY,
        JSON.stringify({ token: token.value, account_id: account.value, email: email.value }),
      );
    } else {
      localStorage.removeItem(SESSION_KEY);
    }
  } catch {
    /* private mode / no storage — session stays in memory */
  }
}

export function setToken(value) {
  token.value = value;
  persist();
}

export function logout() {
  token.value = null;
  account.value = null;
  email.value = null;
  persist();
  clearCache(); // a new driver never sees the last one's cached reads
  saveQueue([]); // ...nor inherits their unsynced writes
}

function _adopt(data, userEmail) {
  token.value = data.token;
  account.value = data.account_id;
  email.value = userEmail ?? email.value;
  persist();
  return data;
}

function headers() {
  const h = { "Content-Type": "application/json" };
  if (token.value) h.Authorization = `Bearer ${token.value}`;
  return h;
}

// AI-CONTEXT: F12 read-cache — the driver app's defining constraint is dead
// zones (design-prd §15.1: offline is a MODE, not an error). A successful GET is
// cached to localStorage; when the network drops, the last-known REAL data is
// served (not a generic fixture) and `online` flips so the status strip tells
// the honest truth. A server error (4xx/5xx) is NOT offline — it rethrows so the
// caller can fall back. Writes/queuing are the F12 backend seam (later pass).
export const online = ref(true);
const CACHE_PREFIX = "longhaul.cache.";

function writeCache(key, data) {
  try {
    localStorage.setItem(CACHE_PREFIX + key, JSON.stringify(data));
  } catch {
    /* storage full / private mode — cache is best-effort */
  }
}
function readCache(key) {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + key);
    return raw == null ? undefined : JSON.parse(raw);
  } catch {
    return undefined;
  }
}
function clearCache() {
  try {
    for (const k of Object.keys(localStorage)) {
      if (k.startsWith(CACHE_PREFIX)) localStorage.removeItem(k);
    }
  } catch {
    /* nothing to clear */
  }
}

async function apiGet(path, cacheKey) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  let resp;
  try {
    resp = await fetch(`${API_BASE}${path}`, { headers: headers() });
  } catch (netErr) {
    // a genuine network failure — go offline, serve the cache if we have it
    online.value = false;
    const cached = cacheKey && readCache(cacheKey);
    if (cached !== undefined && cached !== false) return cached;
    throw netErr;
  }
  if (!resp.ok) throw new Error(`${path} ${resp.status}`); // server error, not offline
  const data = await resp.json();
  online.value = true;
  if (cacheKey) writeCache(cacheKey, data);
  return data;
}

// AI-CONTEXT: F12 write-queue — field captures (status reports, reviews, Q&A)
// must work offline (§15.1: "everything saves to your phone"). A queuedPost that
// hits a dead zone is stored to localStorage and replayed on reconnect; queued
// items were never sent, so at-least-once replay is effectively once. Sync is
// silent (no toast parade); a subtle count on the status strip is the only tell.
const QUEUE_KEY = "longhaul.write_queue";
function readQueue() {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY)) || [];
  } catch {
    return [];
  }
}
export const pendingWrites = ref(readQueue().length);
function saveQueue(q) {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(q));
  } catch {
    /* best-effort */
  }
  pendingWrites.value = q.length;
}
function enqueue(path, body) {
  const q = readQueue();
  q.push({ path, body });
  saveQueue(q);
}

async function queuedPost(path, body) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  let resp;
  try {
    resp = await fetch(`${API_BASE}${path}`, { method: "POST", headers: headers(), body: JSON.stringify(body) });
  } catch {
    online.value = false; // dead zone — save it to the phone
    enqueue(path, body);
    return { queued: true };
  }
  if (!resp.ok) throw new Error(`${path} ${resp.status}`); // server rejected — caller handles
  online.value = true;
  flushQueue(); // opportunistic: we're back online, drain anything waiting
  return resp.json();
}

let _flushing = false;
export async function flushQueue() {
  if (_flushing || typeof fetch === "undefined" || !token.value) return;
  _flushing = true;
  try {
    const q = readQueue();
    while (q.length) {
      const item = q[0];
      try {
        await fetch(`${API_BASE}${item.path}`, {
          method: "POST",
          headers: headers(),
          body: JSON.stringify(item.body),
        });
      } catch {
        online.value = false; // still offline — stop, keep the rest queued
        break;
      }
      online.value = true;
      q.shift(); // drop on success OR server-rejection (don't retry a bad write forever)
      saveQueue(q);
    }
  } finally {
    _flushing = false;
  }
}

// AI-CONTEXT: the driver's active stop (behind The Meter) persists across
// reloads so the Load tab reopens on the running clock.
const ACTIVE_STOP_KEY = "longhaul.active_stop";
function loadActiveStop() {
  try {
    return localStorage.getItem(ACTIVE_STOP_KEY);
  } catch {
    return null;
  }
}
export const activeStopId = ref(loadActiveStop());
export function setActiveStop(id) {
  activeStopId.value = id;
  try {
    if (id) localStorage.setItem(ACTIVE_STOP_KEY, id);
    else localStorage.removeItem(ACTIVE_STOP_KEY);
  } catch {
    /* private mode — active stop stays in memory */
  }
}

export async function createActiveLoad(payload) {
  const resp = await fetch(`${API_BASE}/load`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`create load failed: ${resp.status}`);
  const data = await resp.json();
  setActiveStop(data.stop_id);
  return data;
}

export async function arriveAtStop(stopId) {
  const resp = await fetch(`${API_BASE}/load/${stopId}/arrive`, {
    method: "POST",
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`arrive failed: ${resp.status}`);
  return resp.json();
}

export async function fetchMeter(stopId) {
  return apiGet(`/load/${stopId}/meter`, `meter:${stopId}`);
}

export async function sendDetentionNotice(stopId) {
  const resp = await fetch(`${API_BASE}/load/${stopId}/notice`, {
    method: "POST",
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`notice failed: ${resp.status}`);
  return resp.json();
}

export async function generateClaim(stopId) {
  const resp = await fetch(`${API_BASE}/load/${stopId}/claim`, {
    method: "POST",
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`claim failed: ${resp.status}`);
  return resp.json();
}

export async function login(email, password) {
  const resp = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) throw new Error(`login failed: ${resp.status}`);
  return _adopt(await resp.json(), email);
}

export async function register(email, password) {
  const resp = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ email, password }),
  });
  if (resp.status === 409) throw new Error("email_taken");
  if (!resp.ok) throw new Error(`register failed: ${resp.status}`);
  return _adopt(await resp.json(), email);
}

export async function fetchOverlay({ lat, lon, radiusM = 8000, preset = "drive" }) {
  const q = new URLSearchParams({ lat, lon, radius_m: radiusM, preset });
  return apiGet(`/map/overlay?${q}`, `overlay:${preset}`);
}

export async function report(facilityId, signalType, value) {
  // F12: a status report in a dead zone queues to the phone and syncs later
  return queuedPost("/map/report", { facility_id: facilityId, signal_type: signalType, value });
}

export async function fetchProfile(facilityId) {
  return apiGet(`/facility/${facilityId}/profile`, `profile:${facilityId}`);
}

export async function fetchWallet() {
  return apiGet(`/protection/wallet`, `wallet`);
}

export async function fetchOwed() {
  return apiGet(`/accessorial/owed`, `owed`);
}

export async function fetchBookable({ lat, lon, radiusM = 8000 }) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const q = new URLSearchParams({ lat, lon, radius_m: radiusM });
  const resp = await fetch(`${API_BASE}/parking/bookable?${q}`, { headers: headers() });
  if (!resp.ok) throw new Error(`bookable failed: ${resp.status}`);
  return resp.json();
}

export async function bookSpot({ spotId, startAt, endAt }) {
  const resp = await fetch(`${API_BASE}/parking/book`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ spot_id: spotId, start_at: startAt, end_at: endAt }),
  });
  if (!resp.ok) throw new Error(`book failed: ${resp.status}`);
  return resp.json();
}

export async function fetchFuelCorridor({ lat, lon, headingDeg = 0, maxDistanceM = 40000, gallons = 100 }) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const q = new URLSearchParams({
    lat,
    lon,
    heading_deg: headingDeg,
    max_distance_m: maxDistanceM,
    gallons,
  });
  const resp = await fetch(`${API_BASE}/fuel/corridor?${q}`, { headers: headers() });
  if (!resp.ok) throw new Error(`fuel corridor failed: ${resp.status}`);
  return resp.json();
}

// AI-CONTEXT: the fleet-portal's selected fleet persists across reloads.
const ACTIVE_FLEET_KEY = "longhaul.active_fleet";
export const activeFleetId = ref((() => {
  try {
    return localStorage.getItem(ACTIVE_FLEET_KEY);
  } catch {
    return null;
  }
})());
export function setActiveFleet(id) {
  activeFleetId.value = id;
  try {
    if (id) localStorage.setItem(ACTIVE_FLEET_KEY, id);
    else localStorage.removeItem(ACTIVE_FLEET_KEY);
  } catch {
    /* private mode — active fleet stays in memory */
  }
}

export async function fetchMyFleets() {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/fleet/mine`, { headers: headers() });
  if (!resp.ok) throw new Error(`my fleets failed: ${resp.status}`);
  return resp.json();
}

export async function createFleet(name) {
  const resp = await fetch(`${API_BASE}/fleet`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ name }),
  });
  if (!resp.ok) throw new Error(`create fleet failed: ${resp.status}`);
  const data = await resp.json();
  setActiveFleet(data.fleet_id);
  return data;
}

export async function fetchFleetReport(fleetId) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/fleet/${fleetId}/report`, { headers: headers() });
  if (!resp.ok) throw new Error(`fleet report failed: ${resp.status}`);
  return resp.json();
}

export async function fetchFleetClaims(fleetId) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/fleet/${fleetId}/claims`, { headers: headers() });
  if (!resp.ok) throw new Error(`fleet claims failed: ${resp.status}`);
  return resp.json();
}

export async function fetchEarnings() {
  return apiGet(`/money/earnings`, `earnings`);
}

export async function fetchFuelAnalytics() {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/fuel/analytics`, { headers: headers() });
  if (!resp.ok) throw new Error(`fuel analytics failed: ${resp.status}`);
  return resp.json();
}

export async function issuePumpCode({ stationId, gallons }) {
  const resp = await fetch(`${API_BASE}/fuel/pump-code`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ station_id: stationId, gallons }),
  });
  if (!resp.ok) throw new Error(`pump-code failed: ${resp.status}`);
  return resp.json();
}

export async function calcTrueProfit(payload) {
  const resp = await fetch(`${API_BASE}/intel/true-profit`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`true-profit failed: ${resp.status}`);
  return resp.json();
}

export async function fetchDetentionRisk(facilityId, freeTimeMinutes = 120) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const q = new URLSearchParams({ free_time_minutes: freeTimeMinutes });
  const resp = await fetch(`${API_BASE}/intel/detention-risk/${facilityId}?${q}`, {
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`detention-risk failed: ${resp.status}`);
  return resp.json();
}

export async function fetchAppointmentHours(facilityId) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/intel/appointment-hours/${facilityId}`, {
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`appointment-hours failed: ${resp.status}`);
  return resp.json();
}

export async function fetchPoints() {
  return apiGet(`/community/points`, `points`);
}

export async function fetchQuestions(facilityId) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/community/questions/${facilityId}`, { headers: headers() });
  if (!resp.ok) throw new Error(`questions failed: ${resp.status}`);
  return resp.json();
}

export async function fetchNearbyHandoffs({ lat, lon, radiusM = 8000 }) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const q = new URLSearchParams({ lat, lon, radius_m: radiusM });
  const resp = await fetch(`${API_BASE}/community/handoff/nearby?${q}`, { headers: headers() });
  if (!resp.ok) throw new Error(`handoffs failed: ${resp.status}`);
  return resp.json();
}

export async function broadcastHandoff(facilityId, leavingInMinutes = 15) {
  const resp = await fetch(`${API_BASE}/community/handoff`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ facility_id: facilityId, leaving_in_minutes: leavingInMinutes }),
  });
  if (!resp.ok) throw new Error(`broadcast failed: ${resp.status}`);
  return resp.json();
}

export async function claimHandoff(handoffId) {
  const resp = await fetch(`${API_BASE}/community/handoff/${handoffId}/claim`, {
    method: "POST",
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`claim failed: ${resp.status}`);
  return resp.json();
}

export async function askQuestion(facilityId, text) {
  // F12: a facility question posted offline queues and syncs on reconnect
  return queuedPost("/community/questions", { facility_id: facilityId, text });
}

export async function askVoice(text, driving = false) {
  const resp = await fetch(`${API_BASE}/voice/ask`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ text, driving }),
  });
  if (!resp.ok) throw new Error(`voice failed: ${resp.status}`);
  return resp.json();
}

export async function auditSettlement({ carrier, periodStart, periodEnd, lines }) {
  const resp = await fetch(`${API_BASE}/money/settlements/audit`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      carrier,
      period_start: periodStart,
      period_end: periodEnd,
      lines,
    }),
  });
  if (!resp.ok) throw new Error(`audit failed: ${resp.status}`);
  return resp.json();
}

export async function draftMessage({ kind, facts, tone }) {
  const resp = await fetch(`${API_BASE}/voice/draft`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ kind, facts, tone }),
  });
  if (!resp.ok) throw new Error(`draft failed: ${resp.status}`);
  return resp.json();
}

export async function fetchSleepPlan({ lat, lon, hosMinutesRemaining, headingDeg = 0 }) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const q = new URLSearchParams({
    lat,
    lon,
    hos_minutes_remaining: hosMinutesRemaining,
    heading_deg: headingDeg,
  });
  const resp = await fetch(`${API_BASE}/intel/sleep?${q}`, { headers: headers() });
  if (!resp.ok) throw new Error(`sleep failed: ${resp.status}`);
  return resp.json();
}

export async function submitReview(facilityId, ratings, text) {
  // F12: a review written offline queues and syncs on reconnect
  return queuedPost(`/facility/${facilityId}/review`, { ratings, text });
}
