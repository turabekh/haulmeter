// AI-CONTEXT: §11.3 — "Preset choice persists per state (RESTING→Tonight)".
//
// The Map surface held its preset in a bare `ref("drive")`, so every visit reset to
// Drive: a driver who parked for the night and opened the map to find a shower was
// handed the fuel-and-scales view, every time, however many times they had switched
// to Tonight. The Food FILTERS in the same file have been persisted since they
// shipped, which is what makes this a miss rather than a decision — the pattern was
// already there, one screen over.
//
// PER STATE rather than one global value, because the spec's own parenthesis is a
// rule about which preset belongs to which situation: Tonight is the right answer
// while resting and the wrong one while rolling. A single remembered preset would
// carry the night's choice into the morning's drive.
//
// This lives in `core/` (§19) so the rule is testable arithmetic rather than something
// asserted through a mounted surface.
const PRESET_KEY = "longhaul.map_preset";

export const DEFAULT_PRESET_BY_STATE = {
  driving: "drive",
  resting: "tonight",
  on_site: "work",
  idle: "drive",
};

export function readPresets() {
  try {
    const stored = JSON.parse(localStorage.getItem(PRESET_KEY));
    // a corrupt or hand-edited value falls back rather than throwing a map away
    if (!stored || typeof stored !== "object") return { ...DEFAULT_PRESET_BY_STATE };
    return { ...DEFAULT_PRESET_BY_STATE, ...stored };
  } catch {
    return { ...DEFAULT_PRESET_BY_STATE };
  }
}

export function rememberPreset(state, preset) {
  const next = { ...readPresets(), [state]: preset };
  try {
    localStorage.setItem(PRESET_KEY, JSON.stringify(next));
  } catch {
    /* private mode — the choice holds for this session only */
  }
  return next;
}

export function presetFor(state) {
  return readPresets()[state] ?? DEFAULT_PRESET_BY_STATE.idle;
}
