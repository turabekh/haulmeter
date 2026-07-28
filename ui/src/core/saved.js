// AI-CONTEXT: §11.4's "save for stop", which had nothing behind it.
//
// "all taps deferred-safe (queue 'save for stop' instead of opening flows)". The
// corridor stack's cards were `<li>` elements — not controls at all — so the clause was
// vacuously satisfied: there were no taps to make safe. A driver who passed a lot they
// wanted had no way to keep it, and by the time they stopped it was thirty miles behind
// them and they no longer knew its name.
//
// §10.3 specifies the same mechanism for the Money tab ("actions deferred with 'tonight'
// queue") and it was never built either, so this module is deliberately generic about
// what it holds — a kind and a payload — rather than being a list of facilities.
//
// The destination was an owner decision, logged in §23: navigation structure is a §22
// never-improvise category and there was no existing surface where saved things land.
// Approved shape: a chip on the Map tab that appears once STOPPED, opening a sheet
// (NAV-3). No new route, no new component class.
import { ref } from "vue";

const SAVED_KEY = "longhaul.saved_for_stop";

function read() {
  try {
    const stored = JSON.parse(localStorage.getItem(SAVED_KEY));
    return Array.isArray(stored) ? stored : [];
  } catch {
    return [];
  }
}

function write(items) {
  try {
    localStorage.setItem(SAVED_KEY, JSON.stringify(items));
  } catch {
    /* private mode — the list holds for this session only, which is still the run */
  }
}

// AI-CONTEXT: persisted, because the whole point is surviving the gap between the tap
// and the stop. A tap at 65 mph that a backgrounded app forgot would be worse than no
// tap at all — the driver would believe they had kept the lot.
export const saved = ref(read());

export function isSaved(id) {
  return saved.value.some((item) => String(item.id) === String(id));
}

// AI-CONTEXT: idempotent, and that is the DRIVING requirement rather than tidiness.
// A gloved double-tap on a moving truck is one intention, and the second tap must not
// produce a second row — nor must it toggle the first one off, which would leave the
// driver with the opposite of what they asked for and no way to tell at speed.
export function saveForStop({ id, kind = "facility", label, payload = {}, at = Date.now() }) {
  if (!id || isSaved(id)) return saved.value;
  saved.value = [...saved.value, { id: String(id), kind, label, payload, at }];
  write(saved.value);
  return saved.value;
}

export function unsave(id) {
  saved.value = saved.value.filter((item) => String(item.id) !== String(id));
  write(saved.value);
  return saved.value;
}

export function clearSaved() {
  saved.value = [];
  write(saved.value);
}
