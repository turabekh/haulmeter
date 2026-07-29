// AI-CONTEXT: HTTP client for the LONGHAUL API. Base URL is the LOCKED api port
// 8008. Auth is an F1 session bearer token; it persists to localStorage so a
// session survives reload (a phone app the driver doesn't re-log every trip).
// isAuthenticated gates the app (router guard); callers still fall back to
// fixtures when a request fails offline. This module is the ONLY place the UI
// talks to the backend — swap-friendly (§19).
import { ref, computed } from "vue";

// AI-CONTEXT: WHOSE localhost? (§23 entry 92)
//
// This was the literal string "http://localhost:8008", which is correct in dev and
// wrong everywhere else: in a browser, `localhost` is the DEVICE running the browser.
// Deployed, a driver's phone would have asked ITSELF for the API and failed every
// request. The bug is invisible locally, because locally the two are the same machine.
//
// Deployments set `VITE_API_BASE=/api` and the reverse proxy routes that prefix to the
// API — SAME ORIGIN, which means no CORS preflight, no allowlist to keep in step with
// a domain, and no mixed-content trap when the page is https and the API is not. The
// dev default is unchanged, so `make up` behaves exactly as before.
export const API_BASE = import.meta.env?.VITE_API_BASE ?? "http://localhost:8008";
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
// AI-CONTEXT: the DOCK the armed stop is at (§23 entry 82). Deliberately not
// persisted: a stale facility id would mark the wrong pin as "your stop" on a map,
// and `fetchActiveLoad` re-establishes it on every mount that needs it. The stop id
// is persisted because the Meter must survive a cold start; this is only ever a
// decoration on a screen that has just fetched.
export const activeStopFacilityId = ref(null);
export function setActiveStop(id) {
  activeStopId.value = id;
  if (!id) activeStopFacilityId.value = null;
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

// AI-CONTEXT: §10.2's empty-state action — "Add a load" by rate-con photo, which PRD
// §108 calls the PRIMARY way a load is created. It returns a DRAFT and creates
// nothing: M4-FR4 specifies a driver-confirm step, because a machine read of a
// photographed contract is a proposal and only the driver holds both the paper and
// the phone. Not queued offline — there is nothing useful to show a driver who
// photographs a rate con in a dead zone except the manual form they already have.
export async function importRateCon({ contentB64, filename, contentType } = {}) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/load/import`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      content_b64: contentB64,
      filename: filename ?? null,
      content_type: contentType ?? null,
    }),
  });
  if (!resp.ok) throw new Error(`import failed: ${resp.status}`);
  return resp.json();
}

// AI-CONTEXT: a finished load, still reachable. Nothing asked this before: the only
// read was /load/active (the ONE armed stop), so ending a load orphaned its evidence
// log, condition captures and stop-scoped BOL — all still in the database with no
// route reaching them. Cached like every other read, because history is exactly the
// thing a driver wants at a truck stop with no signal.
export async function fetchLoadHistory() {
  return apiGet("/load/history", "load_history");
}

export async function arriveAtStop(stopId) {
  const resp = await fetch(`${API_BASE}/load/${stopId}/arrive`, {
    method: "POST",
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`arrive failed: ${resp.status}`);
  return resp.json();
}

// AI-CONTEXT: F3's inbound seam, and deliberately NOT a `queuedPost`.
//
// Every other write in this file queues through F12 when the signal drops, because a
// photograph taken in a dead zone is still true an hour later. A POSITION is not: the
// server evaluates a ping against the geofence using SERVER time (PRD §7.3), so a
// replayed one would be judged as happening now and could fabricate an ENTER at a
// dock the driver left this morning. A ping that cannot be sent is dropped.
//
// That loses transitions in dead zones, which is real and logged as debt — but a lost
// EXIT is a gap, and a fabricated one is a lie in an evidence chain.
export async function sendLocationPing({ lat, lon, accuracyM, speedMps, mode } = {}) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/location/ping`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      lat,
      lon,
      client_time: new Date().toISOString(),
      accuracy_m: accuracyM ?? null,
      speed_mps: speedMps ?? null,
      mode: mode ?? null,
    }),
  });
  if (!resp.ok) throw new Error(`ping failed: ${resp.status}`);
  return resp.json();
}

// AI-CONTEXT: M5-FR1's correction. NOT queued offline: the driver is fixing a value
// they are about to act on, and a correction that lands silently an hour later — after
// they have already arrived against the wrong window — is worse than one that visibly
// did not happen.
export async function correctAppointment(stopId, appointment, appointmentEnd = null) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/load/${stopId}/appointment`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify({ appointment, appointment_end: appointmentEnd }),
  });
  if (!resp.ok) throw new Error(`appointment failed: ${resp.status}`);
  return resp.json();
}

// AI-CONTEXT: address -> coordinates, so a dock is filed where it actually is.
// Never queued: the driver is confirming a place before creating a load, and a
// coordinate that arrives an hour later has nothing left to attach to.
export async function geocodeAddress(address) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/location/geocode`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ address }),
  });
  if (!resp.ok) throw new Error(`geocode failed: ${resp.status}`);
  return resp.json();
}

export async function fetchMeter(stopId) {
  return apiGet(`/load/${stopId}/meter`, `meter:${stopId}`);
}

export async function fetchClaim(stopId) {
  return apiGet(`/load/${stopId}/claim`, `claim:${stopId}`);
}

export async function fetchEvidence(stopId) {
  return apiGet(`/load/${stopId}/evidence`, `evidence:${stopId}`);
}

// F6: the real captured image for one evidence photo. Bearer auth can't ride a
// bare <img src>, so fetch the bytes and hand back an object URL the caller shows
// and later revokes. Returns null if unavailable (offline / not yet served).
export async function fetchEvidencePhoto(stopId, artifactId) {
  if (typeof fetch === "undefined" || !token.value) return null;
  try {
    const resp = await fetch(`${API_BASE}/load/${stopId}/evidence/photo/${artifactId}`, {
      headers: headers(),
    });
    if (!resp.ok) return null;
    return URL.createObjectURL(await resp.blob());
  } catch {
    return null;
  }
}

// resume point: the driver's current armed stop server-side, so a fresh device
// (no persisted activeStopId) can re-open The Meter. Adopts it as the active stop.
export async function fetchActiveLoad() {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/load/active`, { headers: headers() });
  if (!resp.ok) throw new Error(`active load ${resp.status}`);
  const data = await resp.json();
  if (data.stop_id) setActiveStop(data.stop_id);
  // the FACILITY too, so the Map tab can tell the driver's own dock from every other
  // receiver on the screen (§11.3's Work preset, §10.1's contextual CTA)
  activeStopFacilityId.value = data.facility_id ?? null;
  return data.stop_id;
}

// AI-CONTEXT: leaving a stop ADVANCES the route (§23 entry 69).
//
// This dropped local state unconditionally, which was right when a load was one dock
// and wrong the moment it became a route: departing the pickup cleared the tab while
// the delivery sat `pending` and unreachable. The server names the next stop; the
// client switches to it and only clears when there is nothing left to run.
export async function endActiveLoad(stopId) {
  let nextStopId = null;
  try {
    const resp = await fetch(`${API_BASE}/load/${stopId}/end`, {
      method: "POST",
      headers: headers(),
    });
    if (resp.ok) nextStopId = (await resp.json()).next_stop_id ?? null;
  } catch {
    /* offline — the local switch still happens; the server stays armed until next end */
  }
  setActiveStop(nextStopId);
  return nextStopId;
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

export async function register(email, password, authority = null) {
  const resp = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ email, password, authority }),
  });
  if (resp.status === 409) throw new Error("email_taken");
  if (!resp.ok) throw new Error(`register failed: ${resp.status}`);
  return _adopt(await resp.json(), email);
}

export async function fetchMe() {
  // F1: who's signed in + their operating-authority verification state
  const resp = await fetch(`${API_BASE}/auth/me`, { headers: headers() });
  if (!resp.ok) throw new Error(`me failed: ${resp.status}`);
  return resp.json();
}

export async function verifyAuthority({ mcNumber, dotNumber }) {
  // F1: back the self-declared authority with an FMCSA MC#/DOT lookup
  const resp = await fetch(`${API_BASE}/auth/verify-authority`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ mc_number: mcNumber || null, dot_number: dotNumber || null }),
  });
  if (resp.status === 403) throw new Error("verification_disabled");
  if (!resp.ok) throw new Error(`verify failed: ${resp.status}`);
  return resp.json();
}

// PRIMARY: viewport bbox — the map fetches exactly what's in view (pan/zoom driven).
// SECONDARY: point + radius (corridor / nearby). `signal` lets a newer viewport
// fetch abort the in-flight one, so a fast pan never paints stale pins. Bypasses the
// offline cache on purpose — per-viewport payloads are transient; offline falls back
// to fixtures in the caller.
export async function fetchOverlay({ bbox, lat, lon, radiusM = 8000, preset = "drive", signal } = {}) {
  const params = { preset };
  if (bbox) {
    params.min_lat = bbox.min_lat;
    params.min_lon = bbox.min_lon;
    params.max_lat = bbox.max_lat;
    params.max_lon = bbox.max_lon;
  } else {
    params.lat = lat;
    params.lon = lon;
    params.radius_m = radiusM;
  }
  const resp = await fetch(`${API_BASE}/map/overlay?${new URLSearchParams(params)}`, {
    headers: headers(),
    signal,
  });
  if (!resp.ok) throw new Error(`overlay failed: ${resp.status}`);
  return resp.json();
}

export async function report(facilityId, signalType, value) {
  // F12: a status report in a dead zone queues to the phone and syncs later
  return queuedPost("/map/report", { facility_id: facilityId, signal_type: signalType, value });
}

export async function confirmFuelPrice(facilityId, priceCentsPerGal) {
  // M7-FR5: crowd diesel-price confirmation; queues offline (F12) and syncs later
  return queuedPost("/fuel/confirm-price", {
    facility_id: facilityId,
    price_cents_per_gal: priceCentsPerGal,
  });
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

// AI-CONTEXT: §11.4's corridor stack, finally asked for.
//
// This endpoint has existed since M1 shipped and no client function reached it — the
// Map surface handed CorridorStack a hardcoded `SAMPLE_CORRIDOR` instead, so DRIVING
// showed three invented facilities with invented parking statuses. Not queued and not
// cached: a corridor is a statement about where the driver is RIGHT NOW, and a
// replayed one describes a stretch of road they have already passed.
export async function fetchCorridor({ lat, lon, headingDeg, preset = "drive" } = {}) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const q = new URLSearchParams({ lat, lon, heading_deg: headingDeg, preset });
  const resp = await fetch(`${API_BASE}/map/corridor?${q}`, { headers: headers() });
  if (!resp.ok) throw new Error(`corridor failed: ${resp.status}`);
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

export async function addConditionPhoto(captureId, prompt, contentB64 = null, contentType = null) {
  // F12: a photo taken in a dead zone queues with an idempotency key and appends
  // to the hash-chain exactly once on reconnect (offline.ingest dedupes replays)
  return queuedPost(`/protection/condition/${captureId}/photo`, {
    prompt,
    content_b64: contentB64,
    content_type: contentType,
  });
}

export async function fileIncident(kind, note) {
  return queuedPost("/protection/incident", { kind, note });
}

export async function submitReview(facilityId, ratings, text) {
  // F12: a review written offline queues and syncs on reconnect
  return queuedPost(`/facility/${facilityId}/review`, { ratings, text });
}

// --- M13 Vendor Network (discovery only; no payment path exists) ---

// AI-CONTEXT: today's appearances are cached to the phone so the food layer still
// renders in a dead zone (§15.1 — offline is a mode, not an error). The cache is
// scoped to the day it was written: stale food data is exactly the "dead content"
// Q-1 exists to prevent, so an old cache is dropped rather than shown.
const VENDOR_CACHE_KEY = "longhaul.vendor_appearances";

function cacheAppearances(entries) {
  try {
    localStorage.setItem(
      VENDOR_CACHE_KEY,
      JSON.stringify({ day: new Date().toDateString(), entries }),
    );
  } catch {
    /* best-effort */
  }
}

export function cachedAppearances() {
  try {
    const raw = JSON.parse(localStorage.getItem(VENDOR_CACHE_KEY));
    if (!raw || raw.day !== new Date().toDateString()) return [];
    return raw.entries || [];
  } catch {
    return [];
  }
}

// AI-CONTEXT: §11.3 food filters ride the SAME bbox request. They narrow what the
// server already decided is discoverable; the client never filters locally, because a
// client that held everything and hid some of it would be one bug away from showing a
// driver a lapsed listing.
function withFilters(params, filters) {
  for (const key of ["q", "language", "halal"]) {
    const value = filters?.[key];
    if (value) params.set(key, value);
  }
  return params;
}

export async function fetchVendorAppearances({ bbox, filters, origin, signal } = {}) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const q = withFilters(
    new URLSearchParams({
      min_lat: bbox.min_lat,
      min_lon: bbox.min_lon,
      max_lat: bbox.max_lat,
      max_lon: bbox.max_lon,
    }),
    filters,
  );
  // the driver's OWN position, sent only when they have actually shared one. The
  // map holds a default until the first fix; sending that would print a confident
  // distance measured from a place the driver has never been.
  if (origin?.lat != null && origin?.lon != null) {
    q.set("lat", origin.lat);
    q.set("lon", origin.lon);
  }
  const resp = await fetch(`${API_BASE}/vendors/appearances?${q}`, {
    headers: headers(),
    signal,
  });
  if (!resp.ok) throw new Error(`vendor appearances failed: ${resp.status}`);
  const entries = await resp.json();
  cacheAppearances(entries);
  return entries;
}

export async function fetchVendorsAt(facilityId, { allVendors = false } = {}) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const q = allVendors ? "?all_vendors=true" : "";
  const resp = await fetch(`${API_BASE}/vendors/at/${facilityId}${q}`, { headers: headers() });
  if (!resp.ok) throw new Error(`vendors at facility failed: ${resp.status}`);
  return resp.json();
}

export async function fetchVendorSheet(vendorId) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/vendors/${vendorId}`, { headers: headers() });
  if (!resp.ok) throw new Error(`vendor sheet failed: ${resp.status}`);
  return resp.json();
}

export async function fetchCorridorVendors({ lat, lon, headingDeg = 0, filters } = {}) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  // filters chosen while stopped keep applying while moving (§11.4 — no keyboard
  // at speed, so the choice has to have been made earlier to be useful at all)
  const q = withFilters(new URLSearchParams({ lat, lon, heading_deg: headingDeg }), filters);
  const resp = await fetch(`${API_BASE}/vendors/corridor?${q}`, { headers: headers() });
  if (!resp.ok) throw new Error(`vendor corridor failed: ${resp.status}`);
  return resp.json();
}

// E3.1: weigh stations on the current heading. The server returns an empty list while
// the layer flag is off, so there is no client-side gate to keep in sync — a driver
// simply never receives a layer they have not been given.
export async function fetchScalesAhead({ lat, lon, headingDeg = 0 } = {}) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const q = new URLSearchParams({ lat, lon, heading_deg: headingDeg });
  const resp = await fetch(`${API_BASE}/map/scales-ahead?${q}`, { headers: headers() });
  if (!resp.ok) throw new Error(`scales ahead failed: ${resp.status}`);
  return resp.json();
}

export async function confirmVendor(vendorId, facilityId, { present = true, soldOut = false } = {}) {
  // F12: a confirmation made in a dead zone queues and applies exactly once on
  // reconnect, like every other crowd contribution
  return queuedPost(`/vendors/${vendorId}/confirm`, {
    facility_id: facilityId,
    present,
    sold_out: soldOut,
  });
}

export async function setFoodAlerts(optedIn) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/vendors/alerts/opt-in`, {
    method: "PUT",
    headers: headers(),
    body: JSON.stringify({ opted_in: optedIn }),
  });
  if (!resp.ok) throw new Error(`alert pref failed: ${resp.status}`);
  return resp.json();
}

export async function muteVendor(vendorId) {
  return queuedPost(`/vendors/${vendorId}/mute`, {});
}

// following a cook. One tap records the vendor, turns the food-alert class ON, and
// clears any older mute on it — the server does all three, so the UI never has to
// remember to (see F8 follow_subject).
export async function followVendor(vendorId) {
  return queuedPost(`/vendors/${vendorId}/follow`, {});
}

export async function unfollowVendor(vendorId) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/vendors/${vendorId}/follow`, {
    method: "DELETE",
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`unfollow failed: ${resp.status}`);
  return resp.json();
}

// M5-FR2/FR4. EXPORT is a live render of the chain — the driver's own copy, always
// current. It needs the server, and that is fine: an export is not a promise to
// anyone, so when there is no signal we simply do not claim one was produced.
export async function exportProtectionPack(kind, ref) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/protection/${kind}/${ref}/export`, { headers: headers() });
  if (!resp.ok) throw new Error(`export failed: ${resp.status}`);
  const blob = await resp.blob();
  // the server names the file; fall back so a download is never called "download"
  const disposition = resp.headers.get("Content-Disposition") || "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  return { url: URL.createObjectURL(blob), filename: match ? match[1] : `${kind}-${ref}.pdf` };
}

// SHARE pins what is sent, so it queues like any other write (F12). §15.1: the
// driver is told once, quietly, that it will go when there is signal — and nothing
// announces it when it does.
export async function shareProtectionPack(kind, ref, recipient = null) {
  return queuedPost(`/protection/${kind}/${ref}/share`, { recipient });
}

// M5-FR3's missing writer. Queued like every other capture (§15.1) — a credential
// photographed at a scale house with no signal is exactly the case this exists for.
export async function captureDocument({ docType, contentB64, filename, contentType, expiresOn, stopId } = {}) {
  return queuedPost("/protection/documents", {
    doc_type: docType,
    content_b64: contentB64,
    filename: filename ?? null,
    content_type: contentType ?? null,
    expires_on: expiresOn || null,
    stop_id: stopId ?? null,
  });
}

// the document itself. Held as an object URL by the caller, which revokes it —
// inspection mode may open several in a row and leaking a blob per tap on a phone
// that is already low on memory is not acceptable.
export async function fetchDocumentBytes(documentId) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/protection/documents/${documentId}`, {
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`document ${resp.status}`);
  return URL.createObjectURL(await resp.blob());
}

// what filing this type would archive, asked BEFORE the capture. A driver should
// not learn their old CDL was replaced by noticing it is gone.
export async function fetchWouldReplace(docType) {
  return apiGet(`/protection/documents/replaces/${docType}`, `replaces:${docType}`);
}

// corrects what was recorded ABOUT a document. The bytes are never edited —
// replacing the image is a new capture, which supersedes.
export async function editDocument(documentId, { docType, expiresOn } = {}) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/protection/documents/${documentId}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify({ doc_type: docType ?? null, expires_on: expiresOn || null }),
  });
  if (!resp.ok) throw new Error(`edit failed: ${resp.status}`);
  return resp.json();
}

export async function fetchDocumentTypes() {
  return apiGet("/protection/documents/types", "doc_types");
}

// AI-CONTEXT: removal, restore, and the archive they move between.
//
// Both writes go through the F12 queue because a driver clearing a dead permit at a
// fuel desk has the same connectivity as one photographing a CDL at a scale house.
// Neither needs the idempotency bookkeeping a capture does: the SERVER makes them
// idempotent — a second archive returns the existing state and never rewrites why a
// document was archived — so a replay out of the dead-zone queue is simply true again.
export async function archiveDocument(documentId) {
  return queuedPost(`/protection/documents/${documentId}/archive`, {});
}

export async function restoreDocument(documentId) {
  return queuedPost(`/protection/documents/${documentId}/restore`, {});
}

export async function fetchArchivedDocuments() {
  return apiGet("/protection/documents/archive", "doc_archive");
}

export async function suggestACook(lat, lon) {
  // Q-7: the empty state's affordance records WHERE drivers want food — the demand
  // half of the vendor recruitment loop. Queued offline like any other contribution.
  return queuedPost("/vendors/suggest", { lat, lon });
}

export async function saveEquipment({ plateState, plateNumber, unitNumber, vin } = {}) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/auth/equipment`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify({
      plate_state: plateState,
      plate_number: plateNumber,
      unit_number: unitNumber,
      vin,
    }),
  });
  if (resp.status === 422) throw new Error("invalid_vin");
  if (!resp.ok) throw new Error(`equipment save failed: ${resp.status}`);
  return resp.json();
}

// --- M13 Session B: reviews, promotions, reports, service centres ---

export async function fetchFacilityPromotions(facilityId) {
  // a SEPARATE call from fetchVendorsAt on purpose: the ranked list and the
  // promoted slot never arrive together, so the UI cannot blend them (Q-3)
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/vendors/promotions/at/${facilityId}`, {
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`promotions failed: ${resp.status}`);
  return resp.json();
}

export async function reviewVendor(vendorId, rating, text = null) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/vendors/${vendorId}/review`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ rating, text }),
  });
  if (resp.status === 409) throw new Error("review_too_soon");
  if (!resp.ok) throw new Error(`review failed: ${resp.status}`);
  return resp.json();
}

export async function reportVendor(vendorId, reason, note = null) {
  return queuedPost(`/vendors/${vendorId}/report`, { reason, note });
}

export async function reportReview(reviewId, reason, note = null) {
  return queuedPost(`/vendors/reviews/${reviewId}/report`, { reason, note });
}

export async function fetchServiceCenter(facilityId) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/vendors/service-center/${facilityId}`, {
    headers: headers(),
  });
  if (resp.status === 404) return null; // unclaimed facilities stay plain POIs
  if (!resp.ok) throw new Error(`service center failed: ${resp.status}`);
  return resp.json();
}

// --- FR8 vendor portal (§18) ---
// AI-CONTEXT: an impersonation token applies to the VENDOR PORTAL only. Admin calls
// keep the operator's own session — the server rejects an impersonation token on
// /admin by design, and sending one there would break the console the moment an
// operator entered "view as".
function portalHeaders() {
  try {
    const imp = JSON.parse(localStorage.getItem("longhaul.impersonation"));
    if (imp?.token) {
      return { "Content-Type": "application/json", Authorization: `Bearer ${imp.token}` };
    }
  } catch {
    /* not impersonating */
  }
  return headers();
}

async function portalGet(path) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/vendor${path}`, { headers: portalHeaders() });
  if (!resp.ok) throw new Error(`${path} ${resp.status}`);
  return resp.json();
}

async function portalSend(path, method, body) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/vendor${path}`, {
    method,
    headers: portalHeaders(),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    // the Q-4 floor answers a refused publish with the EXACT missing fields, so a
    // cook can fix them in one pass. Throwing away the body would turn that into
    // "something went wrong", which is the failure the floor exists to avoid.
    const err = new Error(`${path} ${resp.status}`);
    err.status = resp.status;
    try {
      err.detail = (await resp.json())?.detail ?? null;
    } catch {
      err.detail = null;
    }
    throw err;
  }
  return resp.json();
}

export const fetchVendorProfile = () => portalGet("/profile");
export const fetchVendorSchedule = () => portalGet("/appearances");
export const fetchVendorPromotions = () => portalGet("/promotions");
export const fetchVendorAnalytics = () => portalGet("/analytics");
export const saveVendorProfile = (body) => portalSend("/profile", "PATCH", body);
export const createVendorPromotion = (body) => portalSend("/promotions", "POST", body);
export const cancelVendorPromotion = (id) => portalSend(`/promotions/${id}`, "DELETE");
// whole_series cancels every remaining occurrence of a weekly schedule, and the
// server notifies the drivers who were told about each one
export const cancelVendorAppearance = (id, wholeSeries = false) =>
  portalSend(`/appearances/${id}${wholeSeries ? "?whole_series=true" : ""}`, "DELETE");

// the standing menu. Editing a price here changes what is advertised NEXT — every
// published window keeps its own snapshot (see m13 menu.py).
export const fetchVendorMenu = (includeInactive = false) =>
  portalGet(`/menu${includeInactive ? "?include_inactive=true" : ""}`);
export const addVendorMenuItem = (body) => portalSend("/menu", "POST", body);
export const saveVendorMenuItem = (id, body) => portalSend(`/menu/${id}`, "PATCH", body);
export const retireVendorMenuItem = (id) => portalSend(`/menu/${id}`, "DELETE");

export const publishVendorAppearance = (body) => portalSend("/appearances", "POST", body);
export const editVendorPromotion = (id, body) => portalSend(`/promotions/${id}`, "PATCH", body);
// the vendor's own documents. Named apart from the ADMIN reader below, which takes
// a vendor id — one asks "mine", the other asks "theirs".
export const fetchMyDocuments = () => portalGet("/documents");
export const uploadVendorDocument = (body) => portalSend("/documents", "POST", body);
export const fetchVendorReputation = () => portalGet("/reputation");

// FR7 — claiming a service centre. The search exists because every other facility
// lookup in the product is geographic and a claimant sits at a desk with a business
// name. Rows carry the facility's own name, address and ingested services, so the
// portal never asks anyone to recognise their site from an id.
export const fetchClaimableFacilities = (q) =>
  portalGet(`/claimable?q=${encodeURIComponent(q)}`);
export const fetchVendorClaims = () => portalGet("/claims");
export const submitFacilityClaim = (body) => portalSend("/claims", "POST", body);
// curation is ADDITIVE — the response echoes the union so the portal can show the
// addition alongside what ingestion already knew (E3.2)
export const curateFacilityClaim = (id, body) => portalSend(`/claims/${id}`, "PATCH", body);

// self-serve signup (owner decision: open, guarded by the Q-4 floor and the tier
// ladder rather than by an approval queue). Not a portal path — it is the ordinary
// M13 route a signed-in account uses to become a vendor.
export async function registerVendor(body) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/vendors/register`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = new Error(`register ${resp.status}`);
    err.status = resp.status;
    try {
      err.detail = (await resp.json())?.detail ?? null;
    } catch {
      err.detail = null;
    }
    throw err;
  }
  return resp.json();
}

// --- Admin Console 2.0 sections ---
async function adminGet(path) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/admin${path}`, { headers: headers() });
  if (!resp.ok) throw new Error(`${path} ${resp.status}`);
  return resp.json();
}

export const fetchAdminOverview = () => adminGet("/overview");
export const fetchAdminIngest = () => adminGet("/ingest");
export const fetchJobHistory = (job) => adminGet(`/jobs/${job}`);
export const fetchConfigScopes = () => adminGet("/config/scopes");
export const fetchVendorDocuments = (id) => adminGet(`/vendors/${id}/documents`);
export const fetchAdminClaims = (disputedOnly = false) =>
  adminGet(`/claims${disputedOnly ? "?disputed_only=true" : ""}`);
export const fetchReporterRecord = (id) => adminGet(`/reporters/${id}`);

export function fetchAuditFiltered({ action, targetKind, targetKey, limit } = {}) {
  const q = new URLSearchParams();
  if (action) q.set("action", action);
  if (targetKind) q.set("target_kind", targetKind);
  if (targetKey) q.set("target_key", targetKey);
  if (limit) q.set("limit", limit);
  const qs = q.toString();
  return adminGet(`/audit${qs ? `?${qs}` : ""}`);
}

export async function resolveReport(contentKind, contentRef, { approve, frivolous = false, reason = null }) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(
    `${API_BASE}/admin/moderation/report/${contentKind}/${contentRef}/resolve`,
    {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ approve, frivolous, reason }),
    },
  );
  if (!resp.ok) throw new Error(`resolve failed: ${resp.status}`);
  return resp.json();
}

export async function decideVendor(vendorId, body) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/admin/vendors/${vendorId}/decide`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`vendor decide failed: ${resp.status}`);
  return resp.json();
}

export async function decideClaim(claimId, approve, reason = null) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/admin/claims/${claimId}/decide`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ approve, reason }),
  });
  if (!resp.ok) throw new Error(`claim decide failed: ${resp.status}`);
  return resp.json();
}

export const fetchAdminVendors = () => adminGet("/vendors");

// --- Admin Console 2.0b: accounts, gates, vendor registration ---
async function adminSend(path, method, body) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/admin${path}`, {
    method,
    headers: headers(),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = new Error(`${path} ${resp.status}`);
    err.status = resp.status;
    try {
      err.detail = (await resp.json()).detail;
    } catch {
      /* no body */
    }
    throw err;
  }
  return resp.json();
}

export function fetchAccounts({ q, role } = {}) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (role) params.set("role", role);
  const qs = params.toString();
  return adminGet(`/accounts${qs ? `?${qs}` : ""}`);
}
export const fetchAccount = (id) => adminGet(`/accounts/${id}`);
export const createAccount = (body) => adminSend("/accounts", "POST", body);
export const editAccount = (id, body) => adminSend(`/accounts/${id}`, "PATCH", body);
export const resetCredential = (id) => adminSend(`/accounts/${id}/reset-credential`, "POST");
export const deactivateAccount = (id) => adminSend(`/accounts/${id}/deactivate`, "POST");
export const reactivateAccount = (id) => adminSend(`/accounts/${id}/reactivate`, "POST");
export const changeRole = (id, body) => adminSend(`/accounts/${id}/roles`, "POST", body);
export const setFlagGate = (key, body) => adminSend(`/flags/${key}/gates`, "POST", body);
export const registerVendorAsAdmin = (body) => adminSend("/vendors", "POST", body);

// --- E-D5 impersonation + decision 7 facilities ---
// AI-CONTEXT: an impersonation token is held SEPARATELY from the admin's own
// session and takes precedence while set, so an operator in "view as" cannot
// accidentally act as themselves — and clearing it restores their own session
// without a re-login.
const IMPERSONATION_KEY = "longhaul.impersonation";
export const impersonation = ref(readImpersonation());

function readImpersonation() {
  try {
    return JSON.parse(localStorage.getItem(IMPERSONATION_KEY));
  } catch {
    return null;
  }
}

export function setImpersonation(value) {
  impersonation.value = value;
  try {
    if (value) localStorage.setItem(IMPERSONATION_KEY, JSON.stringify(value));
    else localStorage.removeItem(IMPERSONATION_KEY);
  } catch {
    /* best-effort */
  }
}

export const fetchVendorDetail = (id) => adminGet(`/vendors/${id}/detail`);
export const startImpersonation = (id) => adminSend(`/vendors/${id}/impersonate`, "POST");
export const endImpersonation = (token) =>
  adminSend("/impersonation/end", "POST", { token });
export const fetchFacilities = (q) => adminGet(`/facilities${q ? `?q=${encodeURIComponent(q)}` : ""}`);
export const createFacility = (body) => adminSend("/facilities", "POST", body);
export const editFacility = (id, body) => adminSend(`/facilities/${id}`, "PATCH", body);
export const mergeFacility = (id, duplicateId) =>
  adminSend(`/facilities/${id}/merge`, "POST", { duplicate_id: duplicateId });
export const facilityDuplicates = (id) => adminGet(`/facilities/${id}/duplicates`);

// E-D5 mode (a): assisted edits made from the console, without impersonating
export const editVendorProfile = (id, body) => adminSend(`/vendors/${id}`, "PATCH", body);
export const assistPublishAppearance = (id, body) =>
  adminSend(`/vendors/${id}/appearances`, "POST", body);
export const assistCancelAppearance = (id, appearanceId) =>
  adminSend(`/vendors/${id}/appearances/${appearanceId}`, "DELETE");
export const assistCreatePromotion = (id, body) =>
  adminSend(`/vendors/${id}/promotions`, "POST", body);
export const assistCancelPromotion = (id, promotionId) =>
  adminSend(`/vendors/${id}/promotions/${promotionId}`, "DELETE");

// AI-CONTEXT: §23 entry 102 — F8's inbox, the first endpoint that lets a driver read
// anything the notification system decided about them.
export async function fetchNotifications() {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/notifications`, { headers: headers() });
  if (!resp.ok) throw new Error(`notifications failed: ${resp.status}`);
  return resp.json();
}

export async function markNotificationRead(id) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/notifications/${id}/read`, {
    method: "POST",
    headers: headers(),
  });
  if (!resp.ok) throw new Error(`mark read failed: ${resp.status}`);
  return resp.json();
}
