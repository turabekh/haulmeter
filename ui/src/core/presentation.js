// AI-CONTEXT: Pure presentation logic for map data (design-prd §11). The server
// (F11/M1) returns SEMANTIC data — status strings, shapes, freshness — and this
// maps them to token names + honest labels. Colors are token CSS variables, so
// components never hardcode hex (§6). Freshness is always shown for crowd data
// and never faked (§11.7). Kept as a framework-free module (swappable UI, §19).

// parking status -> the semantic accent token + a colorblind-safe label (C-1)
export const PARKING_STATUS = {
  empty: { token: "--ledger-500", label: "Empty", labelKey: "map.status.empty" },
  some: { token: "--marker-500", label: "Some", labelKey: "map.status.some" },
  full: { token: "--flare-500", label: "Full", labelKey: "map.status.full" },
};

// E3.1 weigh-station status. The valence is INVERTED against every other status in
// the system, and deliberately so: a CLOSED scale is the good news — the driver rolls
// past — while an OPEN one is the thing they must act on. Tokens follow the meaning,
// not the word, so `closed` takes the ledger (good) token and `open` the marker
// (attention) one. Logged as a design-prd §23 decision precisely because reading the
// colors the other way round would tell a driver the opposite of the truth. C-1 still
// holds: the pill always carries its label, so color is never the only signal.
export const WEIGH_STATUS = {
  closed: { token: "--ledger-500", label: "Closed", labelKey: "map.status.closed" },
  open: { token: "--marker-500", label: "Open", labelKey: "map.status.open" },
};

const ALL_STATUS = { ...PARKING_STATUS, ...WEIGH_STATUS };

export function statusPresentation(status) {
  return ALL_STATUS[status] ?? { token: "--text-3", label: "Unknown", labelKey: "map.status.unknown" };
}

// which crowd signal a facility's status belongs to — the client half of the same
// rule F11 applies server-side. A scale is asked whether it is OPEN; everything else
// is asked how FULL it is. Asking a weigh station about parking would collect a
// reading that means nothing about it.
export const SCALE_TYPES = new Set(["weigh_station", "scale"]);

export function statusReportFor(facilityType) {
  if (SCALE_TYPES.has(facilityType)) {
    return {
      signal: "weigh_station_status",
      questionKey: "map.report.question_scale",
      options: Object.keys(WEIGH_STATUS).map((s) => ({ status: s, token: WEIGH_STATUS[s].token })),
    };
  }
  return {
    signal: "parking_fullness",
    questionKey: "map.report.question",
    options: Object.keys(PARKING_STATUS).map((s) => ({ status: s, token: PARKING_STATUS[s].token })),
  };
}

// design-prd §11.7: relative age, subtle, honest ("40m · 3 drivers"). An
// authoritative feed (TPIMS/DOT) is NOT a driver sample — it's attributed to the
// feed (`labels.feed`), never counted as "N drivers". `freshness.source` is the
// provenance of the CURRENT winning reading (e.g. "tpims"); absent for crowd.
export function freshnessLabel(freshness, nowMs, labels = {}) {
  if (!freshness || !freshness.reported_at) return null;
  const ageMs = nowMs - new Date(freshness.reported_at).getTime();
  const mins = Math.max(0, Math.round(ageMs / 60000));
  const age = mins < 60 ? `${mins}m` : `${Math.round(mins / 60)}h`;
  if (freshness.source) return `${age} · ${labels.feed ?? "official feed"}`;
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

// receivable state -> semantic token (design-prd §10.3 status pills; color+label, C-1)
export const RECEIVABLE_STATUS_TOKEN = {
  invoiced: "--text-2",
  acknowledged: "--shield-500",
  disputed: "--marker-500",
  escalated: "--flare-500",
  recovered: "--ledger-500",
  written_off: "--text-3",
};

export function receivableStatusToken(state) {
  return RECEIVABLE_STATUS_TOKEN[state] ?? "--text-2";
}

// dwell durations as tabular "Hh Mm" (Mono figures, §6.2 T-2)
export function formatDwell(seconds) {
  if (seconds == null) return null;
  const total = Math.round(seconds / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// AI-CONTEXT: miles, in ONE place. The corridor grew two private mile helpers at
// two precisions; a card and a corridor card disagreeing about the same distance is
// the kind of drift nobody notices until a driver does.
//
// `precise` is for a distance measured ALONG a corridor (M1 geometry). The default
// is whole miles, because a map distance is a DIRECT line and a decimal on a
// straight line implies routing precision that no straight line has — truck routing
// is PRD §17 Q9, unresolved, so nothing here may imply an arrival time (§11.7).
const METRES_PER_MILE = 1609.344;

export function formatMiles(distanceM, { precise = false } = {}) {
  if (distanceM == null || Number.isNaN(distanceM)) return null;
  const miles = distanceM / METRES_PER_MILE;
  return precise ? miles.toFixed(1) : String(Math.round(miles));
}

// AI-CONTEXT: §11.5's declutter rule, made enforceable.
//
// "labels appear only >= zoom threshold; overlapping labels never allowed." Both
// halves lived nowhere: the map drew no labels at all, so the rule had never had to
// be true. Now that §11.2's price slot renders one, the rule needs an implementation
// that can be tested rather than a comment claiming it holds — this is §19's reason
// for putting logic in `core/` in the first place.
//
// Placement is GREEDY in the order given, which is the order the server ranked the
// pins, so the nearest/most relevant station keeps its label and a further one behind
// it loses only the figure — never the pin, and never the tap.
export const PRICE_LABEL_MIN_ZOOM = 9;
const LABEL_W = 54;
const LABEL_H = 18;
const LABEL_DY = 20;

export function placeLabels(
  items,
  { zoom = null, width = LABEL_W, height = LABEL_H, dy = LABEL_DY, minZoom = PRICE_LABEL_MIN_ZOOM } = {},
) {
  const shown = {};
  // `zoom: null` means there is no live map to have a zoom — the placeholder canvas,
  // which never carries enough pins to collide. The threshold is a map rule, so it
  // does not apply where there is no map.
  if (zoom !== null && zoom < minZoom) return shown;
  const placed = [];
  for (const item of items) {
    if (!item || !item.label) continue;
    if (item.x == null || item.y == null) {
      shown[item.id] = item.label;
      continue;
    }
    const box = { x: item.x - width / 2, y: item.y + dy, w: width, h: height };
    const hits = placed.some(
      (p) => box.x < p.x + p.w && box.x + box.w > p.x && box.y < p.y + p.h && box.y + box.h > p.y,
    );
    if (hits) continue;
    placed.push(box);
    shown[item.id] = item.label;
  }
  return shown;
}

// AI-CONTEXT: the `Nm` / `Nh` age string on its own, extracted rather than re-written.
// `freshnessLabel` has computed it since §11.7 landed and buried it inside a sentence
// about crowd samples; the saved-for-stop list needs the age of an ACTION the driver
// took, which has no sample size and no feed. Two age formats drifting apart is the
// drift `formatMiles` was consolidated to stop.
export function ageLabel(atMs, nowMs) {
  if (atMs == null) return null;
  const mins = Math.max(0, Math.round((nowMs - atMs) / 60000));
  return mins < 60 ? `${mins}m` : `${Math.round(mins / 60)}h`;
}

// AI-CONTEXT: §11.6 — "night style is the DEFAULT PAIRING WITH DARK THEME".
//
// MapCanvas chose its basemap from `new Date().getHours()`, so the rule was not
// implemented at all: a driver on the dark theme at noon got a light basemap under
// dark chrome, and one on light at 8pm got the reverse. Both are the app disagreeing
// with itself down the middle of the screen — and the map is the daily-open surface,
// so it is the disagreement a driver sees most.
//
// The clock is not a bad proxy, it is the wrong question. §6.1 C-3 makes the theme
// "system setting + manual override", which already encodes time-of-day for the
// drivers who want it and encodes an explicit preference for the drivers who do not.
// Asking the hour a second time overrides the answer they gave.
//
// Pure, so the pairing is testable without a WebGL context — which is the only way it
// would ever have been checked (the harness cannot assert a Mapbox config property).
export function basemapPreset(themeMode, systemPrefersDark) {
  if (themeMode === "dark") return "night";
  if (themeMode === "light") return "day";
  // "system", and dark is primary (§6.1 C-3) — so an unknown preference is night
  return systemPrefersDark === false ? "day" : "night";
}

// AI-CONTEXT: §23 entry 101 — where a live marker sits, as arithmetic.
//
// The map moved markers by writing `top`/`left` into reactive state on every frame of
// a pan, which asked the browser for LAYOUT and Vue for a re-render up to 300 times
// per frame. This is the replacement, and it lives here for the same reason
// `placeLabels` and `basemapPreset` do (§19): a test runner has no WebGL, so a rule
// asserted only through a mounted Mapbox canvas is a rule that ships unexercised.
//
// The centring `translate(-50%, -50%)` is composed here rather than left to the
// stylesheet's own transform, because an element may only have ONE transform — an
// imperative write would otherwise silently drop the centring and hang every pin off
// its own corner, half a puck away from the place it claims to mark.
export function markerTransform(x, y) {
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%)`;
}
