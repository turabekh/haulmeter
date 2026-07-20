// AI-CONTEXT: HTTP client for the M1 API. Base URL is the LOCKED api port 8008.
// Auth is an F1 session bearer token held in memory (a login surface lands with
// F1 UI; until then callers fall back to fixtures when there's no token). This
// module is the ONLY place the UI talks to the backend — swap-friendly (§19).
import { ref } from "vue";

export const API_BASE = "http://localhost:8008";
const token = ref(null);

export function setToken(value) {
  token.value = value;
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
  const data = await resp.json();
  setToken(data.token);
  return data;
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

export async function fetchOwed() {
  if (typeof fetch === "undefined" || !token.value) throw new Error("no session");
  const resp = await fetch(`${API_BASE}/accessorial/owed`, { headers: headers() });
  if (!resp.ok) throw new Error(`owed failed: ${resp.status}`);
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
