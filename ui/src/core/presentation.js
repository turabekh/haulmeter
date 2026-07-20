// AI-CONTEXT: Pure presentation logic for map data (design-prd §11). The server
// (F11/M1) returns SEMANTIC data — status strings, shapes, freshness — and this
// maps them to token names + honest labels. Colors are token CSS variables, so
// components never hardcode hex (§6). Freshness is always shown for crowd data
// and never faked (§11.7). Kept as a framework-free module (swappable UI, §19).

// parking status -> the semantic accent token + a colorblind-safe label (C-1)
export const PARKING_STATUS = {
  empty: { token: "--ledger-500", label: "Empty" },
  some: { token: "--marker-500", label: "Some" },
  full: { token: "--flare-500", label: "Full" },
};

export function statusPresentation(status) {
  return PARKING_STATUS[status] ?? { token: "--text-3", label: "Unknown" };
}

// design-prd §11.7: relative age, subtle, honest ("40m · 3 drivers")
export function freshnessLabel(freshness, nowMs) {
  if (!freshness || !freshness.reported_at) return null;
  const ageMs = nowMs - new Date(freshness.reported_at).getTime();
  const mins = Math.max(0, Math.round(ageMs / 60000));
  const age = mins < 60 ? `${mins}m` : `${Math.round(mins / 60)}h`;
  const n = freshness.sample_size ?? 0;
  const who = n === 1 ? "1 driver" : `${n} drivers`;
  return `${age} · ${who}`;
}

// §11.7: statuses older than 4h are "stale" and render hollow (never fake confidence)
export const STALE_AFTER_MS = 4 * 60 * 60 * 1000;
export function isStale(freshness, nowMs) {
  if (!freshness || !freshness.reported_at) return true;
  return nowMs - new Date(freshness.reported_at).getTime() > STALE_AFTER_MS;
}

// §11.2 pin shapes are a data classification from facility type
export const PIN_SHAPES = new Set(["circle", "square", "diamond", "small_square"]);

// dwell durations as tabular "Hh Mm" (Mono figures, §6.2 T-2)
export function formatDwell(seconds) {
  if (seconds == null) return null;
  const total = Math.round(seconds / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}
