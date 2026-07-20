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
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const q = new URLSearchParams({ lat, lon, radius_m: radiusM, preset });
  const resp = await fetch(`${API_BASE}/map/overlay?${q}`, { headers: headers() });
  if (!resp.ok) throw new Error(`overlay failed: ${resp.status}`);
  return resp.json();
}

export async function report(facilityId, signalType, value) {
  const resp = await fetch(`${API_BASE}/map/report`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ facility_id: facilityId, signal_type: signalType, value }),
  });
  if (!resp.ok) throw new Error(`report failed: ${resp.status}`);
  return resp.json();
}

export async function fetchProfile(facilityId) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/facility/${facilityId}/profile`, { headers: headers() });
  if (!resp.ok) throw new Error(`profile failed: ${resp.status}`);
  return resp.json();
}

export async function fetchWallet() {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/protection/wallet`, { headers: headers() });
  if (!resp.ok) throw new Error(`wallet failed: ${resp.status}`);
  return resp.json();
}

export async function fetchOwed() {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/accessorial/owed`, { headers: headers() });
  if (!resp.ok) throw new Error(`owed failed: ${resp.status}`);
  return resp.json();
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

export async function fetchEarnings() {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/money/earnings`, { headers: headers() });
  if (!resp.ok) throw new Error(`earnings failed: ${resp.status}`);
  return resp.json();
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
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/community/points`, { headers: headers() });
  if (!resp.ok) throw new Error(`points failed: ${resp.status}`);
  return resp.json();
}

export async function fetchQuestions(facilityId) {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/community/questions/${facilityId}`, { headers: headers() });
  if (!resp.ok) throw new Error(`questions failed: ${resp.status}`);
  return resp.json();
}

export async function askQuestion(facilityId, text) {
  const resp = await fetch(`${API_BASE}/community/questions`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ facility_id: facilityId, text }),
  });
  if (!resp.ok) throw new Error(`ask failed: ${resp.status}`);
  return resp.json();
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

export async function submitReview(facilityId, ratings, text) {
  const resp = await fetch(`${API_BASE}/facility/${facilityId}/review`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ ratings, text }),
  });
  if (!resp.ok) throw new Error(`review failed: ${resp.status}`);
  return resp.json();
}
