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
// AND transactional evidence (condition photos, incidents) must work offline
// (§15.1). A queuedPost that hits a dead zone is stored to localStorage and
// replayed on reconnect. Each queued write carries a STABLE idempotency key,
// generated once and re-sent on every replay: the F12 backend (offline.ingest)
// dedupes by (account, key), so even a write that reached the server before the
// dead zone applies exactly once — no duplicate evidence chain. Sync is silent;
// a subtle count on the status strip is the only tell.
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
function newOpId() {
  try {
    return crypto.randomUUID();
  } catch {
    return `op-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}
function postHeaders(opId) {
  const h = headers();
  if (opId) h["Idempotency-Key"] = opId; // honored by F12-wired endpoints (§15.1)
  return h;
}
function enqueue(path, body, opId) {
  const q = readQueue();
  q.push({ path, body, opId });
  saveQueue(q);
}

async function queuedPost(path, body) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const opId = newOpId(); // stable across replays -> exactly-once at the server
  let resp;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: postHeaders(opId),
      body: JSON.stringify(body),
    });
  } catch {
    online.value = false; // dead zone — save it to the phone
    enqueue(path, body, opId);
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
          headers: postHeaders(item.opId), // same key -> the server dedupes the replay
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

// resume point: the driver's current armed stop server-side, so a fresh device
// (no persisted activeStopId) can re-open The Meter. Adopts it as the active stop.
export async function fetchActiveLoad() {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/load/active`, { headers: headers() });
  if (!resp.ok) throw new Error(`active load ${resp.status}`);
  const data = await resp.json();
  if (data.stop_id) setActiveStop(data.stop_id);
  return data.stop_id;
}

export async function endActiveLoad(stopId) {
  // durable end: mark the stop departed server-side, then drop local state
  try {
    await fetch(`${API_BASE}/load/${stopId}/end`, { method: "POST", headers: headers() });
  } catch {
    /* offline — local clear still happens; server stays armed until next end */
  }
  setActiveStop(null);
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
  if (!resp.ok) {
    const err = new Error(`book failed: ${resp.status}`);
    err.status = resp.status; // 409 = spot already taken for those nights
    throw err;
  }
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

// AI-CONTEXT: F14 admin console reads/toggles (platform_admin gated server-side;
// a 403 surfaces as "no access"). Not part of the driver app.
export async function fetchAdminFlags() {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/admin/flags`, { headers: headers() });
  if (!resp.ok) throw new Error(`admin flags ${resp.status}`);
  return resp.json();
}
export async function fetchAdminViews() {
  const resp = await fetch(`${API_BASE}/admin/views`, { headers: headers() });
  if (!resp.ok) throw new Error(`admin views ${resp.status}`);
  return resp.json();
}
export async function fetchModeration() {
  const resp = await fetch(`${API_BASE}/admin/moderation`, { headers: headers() });
  if (!resp.ok) throw new Error(`moderation ${resp.status}`);
  return resp.json();
}
export async function toggleFlag(key, enable) {
  const resp = await fetch(`${API_BASE}/admin/flags/${key}/${enable ? "enable" : "disable"}`, {
    method: "POST",
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`toggle ${resp.status}`);
  return resp.json();
}
export async function decideModeration(itemId, approve) {
  const resp = await fetch(`${API_BASE}/admin/moderation/${itemId}/decide`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ approve }),
  });
  if (!resp.ok) throw new Error(`decide ${resp.status}`);
  return resp.json();
}
export async function fetchAnalytics() {
  const resp = await fetch(`${API_BASE}/admin/analytics`, { headers: headers() });
  if (!resp.ok) throw new Error(`analytics ${resp.status}`);
  return resp.json();
}
export async function fetchConfig(scope = "global") {
  const resp = await fetch(`${API_BASE}/admin/config?scope=${encodeURIComponent(scope)}`, {
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`config ${resp.status}`);
  return resp.json();
}
export async function saveConfig(key, value, scope = "global") {
  const resp = await fetch(`${API_BASE}/admin/config`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ key, value, scope }),
  });
  if (!resp.ok) throw new Error(`save config ${resp.status}`);
  return resp.json();
}
export async function fetchAuditLog() {
  const resp = await fetch(`${API_BASE}/admin/audit`, { headers: headers() });
  if (!resp.ok) throw new Error(`audit ${resp.status}`);
  return resp.json();
}

// AI-CONTEXT: Public Scorecard reads — the ONLY unauthenticated fetchers (no
// token required; aggregate/min-sample data only, §13). Backs the public portal.
export async function searchFacilities(q = "") {
  const query = new URLSearchParams({ q, limit: 25 });
  const resp = await fetch(`${API_BASE}/public/facilities?${query}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!resp.ok) throw new Error(`facilities ${resp.status}`);
  return resp.json();
}
export async function fetchScorecard(facilityId) {
  const resp = await fetch(`${API_BASE}/public/facility/${facilityId}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!resp.ok) throw new Error(`scorecard ${resp.status}`);
  return resp.json();
}

// AI-CONTEXT: Property-Owner portal read (M6-FR5, the supply side). Session
// required; the owner's listings + bookings + accrued payable (F7 owner_payable).
// Payout SETTLEMENT is the deferred Stripe/Connect seam — this is the view only.
export async function fetchOwnerDashboard() {
  return apiGet(`/owner/dashboard`, `owner-dashboard`);
}
export async function createOwnerProperty(name, lat, lon) {
  const resp = await fetch(`${API_BASE}/owner/property`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ name, lat, lon }),
  });
  if (!resp.ok) throw new Error(`create property ${resp.status}`);
  return resp.json();
}
export async function addOwnerSpot(propertyId, label, priceCentsPerNight) {
  const resp = await fetch(`${API_BASE}/owner/property/${propertyId}/spot`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ label, price_cents_per_night: priceCentsPerNight }),
  });
  if (!resp.ok) throw new Error(`add spot ${resp.status}`);
  return resp.json();
}
export async function updateOwnerSpot(spotId, patch) {
  const resp = await fetch(`${API_BASE}/owner/spot/${spotId}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify(patch),
  });
  if (!resp.ok) throw new Error(`update spot ${resp.status}`);
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

export async function startConditionCapture(stopId, phase = "delivery") {
  const resp = await fetch(`${API_BASE}/protection/condition/start`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ stop_id: stopId, phase }),
  });
  if (!resp.ok) throw new Error(`condition start failed: ${resp.status}`);
  return resp.json();
}

export async function addConditionPhoto(captureId, prompt, contentB64 = null) {
  // F12: a photo taken in a dead zone queues with an idempotency key and appends
  // to the hash-chain exactly once on reconnect (offline.ingest dedupes replays)
  return queuedPost(`/protection/condition/${captureId}/photo`, {
    prompt,
    content_b64: contentB64,
  });
}

export async function fileIncident(kind, note) {
  return queuedPost("/protection/incident", { kind, note });
}

export async function submitReview(facilityId, ratings, text) {
  // F12: a review written offline queues and syncs on reconnect
  return queuedPost(`/facility/${facilityId}/review`, { ratings, text });
}
