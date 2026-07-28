// AI-CONTEXT: the Map tab and the Load tab, which knew nothing about each other.
//
// §10.1 gives the facility sheet a three-rung contextual CTA — "Book / Navigate / Arm
// stop" — and the third rung had never existed: a `shipper_receiver` pin offered
// Navigate and stopped there. So a driver looking at the Work preset could not tell
// their OWN dock from every other warehouse in the county, and the two surfaces that
// are about the same load could not reach each other in either direction.
//
// §11.3 also says "preset choice persists per state (RESTING→Tonight)" and the preset
// was a bare ref: every visit reset to Drive, including the one a driver makes after
// parking for the night.
//
// What these hold:
// · The armed dock's card leads with the stop, and Navigate stays reachable — the
//   ladder decides what is LOUDEST, never what is permitted (the §10.2 rule, applied
//   to the surface §10.1 governs).
// · An ordinary receiver is untouched, so the map does not start claiming every
//   warehouse is the driver's.
// · The preset is remembered per driver state, and RESTING opens on Tonight.
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import FacilityCard from "../src/core/components/FacilityCard.vue";
import { routes } from "../src/router.js";
import en from "../src/core/i18n/en.json";

function dock(over = {}) {
  return {
    facility_id: "f-dock",
    name: "Harvest Foods DC",
    facility_type: "shipper_receiver",
    shape: "diamond",
    lat: 32.78,
    lon: -96.8,
    status: null,
    badges: [],
    freshness: null,
    ...over,
  };
}

function card(props) {
  return mount(FacilityCard, {
    props,
    global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] },
  });
}

describe("§10.1 — the third CTA, which never existed", () => {
  it("leads with the stop when the pin is the dock the driver is working", () => {
    const w = card({ pin: dock(), isActiveStop: true });
    expect(w.find(".cta").text()).toContain(en["facility.your_stop"]);
    // the modifier names which rung won. It is what the layout harness keys its
    // `ready` selector on, so a card that stopped rendering this rung would fail
    // there rather than silently measuring a different card.
    expect(w.find(".cta--stop").exists()).toBe(true);
  });

  it("emits open-stop rather than opening a flow on the map", () => {
    // NAV-5 cross-link: the Load tab owns the Meter, the arrive CTA and the
    // checklist. Two screens telling a driver about one stop is the thing to avoid.
    const w = card({ pin: dock(), isActiveStop: true });
    w.find(".cta").trigger("click");
    expect(w.emitted("open-stop")).toBeTruthy();
  });

  it("keeps Navigate reachable underneath — the ladder ranks, it does not gate", () => {
    const w = card({ pin: dock(), isActiveStop: true });
    const labels = w.findAll("button").map((b) => b.text());
    expect(labels.some((l) => l.includes(en["facility.navigate"]))).toBe(true);
  });

  it("leaves an ordinary receiver exactly as it was", () => {
    const w = card({ pin: dock(), isActiveStop: false });
    expect(w.find(".cta").text()).toContain(en["facility.navigate"]);
    expect(w.text()).not.toContain(en["facility.your_stop"]);
    expect(w.find(".cta--nav").exists()).toBe(true);
    expect(w.find(".cta--stop").exists()).toBe(false);
  });

  it("does not claim a truck stop is a dock just because a load is running", () => {
    // the flag is a facility-id comparison, so it can only ever be true for one pin
    const w = card({ pin: dock({ facility_type: "truck_stop" }), isActiveStop: false });
    expect(w.text()).not.toContain(en["facility.your_stop"]);
  });
});

describe("§11.3 — the preset survives the drive", () => {
  const KEY = "longhaul.map_preset";
  beforeEach(() => localStorage.removeItem(KEY));

  // the surface reads and writes this map directly; the behaviour under test is the
  // contract between the two, which is what a driver actually experiences
  it("defaults RESTING to Tonight, which is the spec's own example", async () => {
    const { DEFAULT_PRESET_BY_STATE } = await import("../src/core/map-presets.js");
    expect(DEFAULT_PRESET_BY_STATE.resting).toBe("tonight");
  });

  it("remembers a different preset per state rather than one global choice", async () => {
    const { readPresets, rememberPreset } = await import("../src/core/map-presets.js");
    rememberPreset("resting", "fuel");
    expect(readPresets().resting).toBe("fuel");
    // the state a driver did NOT change keeps its own answer
    expect(readPresets().driving).toBe("drive");
  });

  it("survives a reload, which is the whole point", async () => {
    const { readPresets, rememberPreset } = await import("../src/core/map-presets.js");
    rememberPreset("resting", "food");
    expect(JSON.parse(localStorage.getItem(KEY)).resting).toBe("food");
    expect(readPresets().resting).toBe("food");
  });

  it("falls back to the defaults when storage is unreadable", async () => {
    const { readPresets, DEFAULT_PRESET_BY_STATE } = await import("../src/core/map-presets.js");
    localStorage.setItem(KEY, "not json");
    expect(readPresets()).toEqual(DEFAULT_PRESET_BY_STATE);
  });
});
