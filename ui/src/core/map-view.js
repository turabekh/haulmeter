// AI-CONTEXT: §23 entry 100 — where the map was last looking.
//
// Owner-reported: "viewing a facility and coming back to the map is acting weird."
// It was. Nothing kept the viewport, so leaving the Map tab destroyed the Mapbox
// instance and returning rebuilt it at the continental default (zoom 3.5, the whole
// United States). The driver then watched it fetch the country, re-acquire GPS and
// fly back — two round trips and a visible jump to arrive where they already were.
//
// The preset next to it has persisted since §23 entry 82, for exactly the reason
// stated there: "the pattern was already there, one screen over." The viewport is the
// same omission a layer down — a driver who pans to the yard they are delivering to
// tomorrow and taps one pin should not be returned to a map of America.
//
// NOT per driver-state, unlike the preset. A preset is a question about the situation
// ("what am I looking FOR"), and the answer legitimately differs between resting and
// rolling. A viewport is a question about the place ("where am I looking"), and the
// place does not become a different place because the truck started moving.
//
// Zoom is clamped and coordinates sanity-checked on read: this is the one input that
// can be hand-edited in devtools, and a NaN centre puts Mapbox into a state a reload
// cannot clear.
const VIEW_KEY = "longhaul.map_view";

// below this the stored view is a continental default worth ignoring — restoring it
// would "remember" the very screen this exists to stop the driver seeing again
export const MIN_REMEMBERED_ZOOM = 5;
export const MAX_ZOOM = 20;

function usable(view) {
  if (!view || typeof view !== "object") return false;
  const { lat, lon, zoom } = view;
  if (![lat, lon, zoom].every((n) => typeof n === "number" && Number.isFinite(n))) return false;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return false;
  return zoom >= MIN_REMEMBERED_ZOOM && zoom <= MAX_ZOOM;
}

export function readView() {
  try {
    const stored = JSON.parse(localStorage.getItem(VIEW_KEY));
    return usable(stored) ? stored : null;
  } catch {
    return null;
  }
}

export function rememberView(lat, lon, zoom) {
  const view = { lat, lon, zoom };
  if (!usable(view)) return null;
  try {
    localStorage.setItem(VIEW_KEY, JSON.stringify(view));
  } catch {
    /* private mode — the view holds for this session only */
  }
  return view;
}

export function __resetForTests() {
  try {
    localStorage.removeItem(VIEW_KEY);
  } catch {
    /* nothing to clear */
  }
}
