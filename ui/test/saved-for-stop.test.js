// AI-CONTEXT: §11.4's "save for stop", which had nothing behind it.
//
// "all taps deferred-safe (queue 'save for stop' instead of opening flows)". The
// corridor cards were `<li>` elements — not controls at all — so the clause was
// VACUOUSLY satisfied: there were no taps to make safe. A driver who passed a lot they
// wanted had no way to keep it, and by the time they stopped it was thirty miles behind
// them and they no longer knew its name.
//
// Where saved things land was an owner decision (§22 makes navigation structure
// never-improvise): a chip on the Map tab that appears once STOPPED, opening a sheet.
//
// What these hold:
// · A corridor tap opens NO flow. That is the entire requirement, and the easiest one
//   to regress by "helpfully" navigating somewhere.
// · Saving is idempotent — a gloved double-tap at speed is one intention, and must not
//   toggle the row back off where the driver cannot see it happen.
// · It persists, because the gap between the tap and the stop is the point.
// · §11.7 — the sheet shows no saved status and no saved distance. Both were true
//   thirty miles ago, and a lot that read `empty` at 60 mph is exactly the one that
//   fills while you drive to it.
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import CorridorStack from "../src/core/components/CorridorStack.vue";
import { saved, saveForStop, unsave, isSaved, clearSaved } from "../src/core/saved.js";
import en from "../src/core/i18n/en.json";

const KEY = "longhaul.saved_for_stop";

function entry(over = {}) {
  return {
    facility_id: "f-1",
    name: "Pilot #77",
    facility_type: "truck_stop",
    distance_m: 5400,
    status: "full",
    badges: [],
    ...over,
  };
}

describe("§11.4 — the corridor tap defers instead of opening a flow", () => {
  it("makes each card a real control, which it never was", () => {
    const w = mount(CorridorStack, { props: { entries: [entry()] } });
    expect(w.find(".corridor__tap").element.tagName).toBe("BUTTON");
  });

  it("emits save and nothing else — no route, no sheet, no confirm", () => {
    const w = mount(CorridorStack, { props: { entries: [entry()] } });
    w.find(".corridor__tap").trigger("click");
    expect(w.emitted("save")).toHaveLength(1);
    // `save` is the ONLY thing this component may ask its parent to do while the truck
    // is moving. Asserted against the declared contract rather than the emitted list,
    // because a native `click` bubbles through the wrapper and would mask a regression.
    expect(CorridorStack.emits).toEqual(["save"]);
  });

  it("marks a saved card so the tap has visible feedback without a prompt", () => {
    const w = mount(CorridorStack, {
      props: { entries: [entry()], savedIds: ["f-1"] },
    });
    expect(w.find(".corridor__saved").exists()).toBe(true);
    expect(w.find(".corridor__tap").attributes("aria-pressed")).toBe("true");
  });

  it("leaves an unsaved card unmarked", () => {
    const w = mount(CorridorStack, { props: { entries: [entry()], savedIds: [] } });
    expect(w.find(".corridor__saved").exists()).toBe(false);
    expect(w.find(".corridor__tap").attributes("aria-pressed")).toBe("false");
  });

  it("names the action in the accessible label, not just the facility", () => {
    const w = mount(CorridorStack, { props: { entries: [entry()] } });
    expect(w.find(".corridor__tap").attributes("aria-label")).toContain(en["saved.mark"]);
  });

  it("keeps the scale and food lines read-only — they have nothing to defer", () => {
    const w = mount(CorridorStack, {
      props: {
        entries: [],
        scales: [{ facility_id: "s-1", name: "Scale", distance_m: 9000, status: "closed" }],
      },
    });
    expect(w.findAll("button")).toHaveLength(0);
  });
});

describe("the saved queue", () => {
  beforeEach(() => {
    localStorage.removeItem(KEY);
    clearSaved();
  });

  it("keeps what was tapped", () => {
    saveForStop({ id: "f-1", label: "Pilot #77" });
    expect(saved.value).toHaveLength(1);
    expect(isSaved("f-1")).toBe(true);
  });

  it("is idempotent — a double-tap at speed is one intention", () => {
    // and crucially it does NOT toggle: a driver who taps twice must not end up with
    // the opposite of what they asked for, thirty miles from anywhere
    saveForStop({ id: "f-1", label: "Pilot #77" });
    saveForStop({ id: "f-1", label: "Pilot #77" });
    expect(saved.value).toHaveLength(1);
    expect(isSaved("f-1")).toBe(true);
  });

  it("persists, because surviving the gap to the stop is the whole point", () => {
    saveForStop({ id: "f-1", label: "Pilot #77" });
    expect(JSON.parse(localStorage.getItem(KEY))).toHaveLength(1);
  });

  it("removes on request and stays removed", () => {
    saveForStop({ id: "f-1", label: "Pilot #77" });
    unsave("f-1");
    expect(saved.value).toEqual([]);
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual([]);
  });

  it("survives a corrupt stored value rather than throwing a map away", async () => {
    localStorage.setItem(KEY, "{not json");
    const fresh = await import("../src/core/saved.js?corrupt");
    expect(fresh.saved.value).toEqual([]);
  });

  it("refuses an item with no id — an unidentifiable save is unactionable", () => {
    saveForStop({ label: "Nowhere" });
    expect(saved.value).toEqual([]);
  });

  it("records WHEN it was tapped, which is the one fact that does not decay", () => {
    saveForStop({ id: "f-1", label: "Pilot #77", at: 1000 });
    expect(saved.value[0].at).toBe(1000);
  });
});

describe("§11.7 — a saved row states nothing that has gone stale", () => {
  it("carries the tap time, not the status or the distance it was saved with", () => {
    // the payload deliberately holds only what stays true: what kind of place it is
    // and where. A status and a distance were facts about a moment already gone.
    saveForStop({
      id: "f-1",
      label: "Pilot #77",
      payload: { facility_type: "truck_stop", lat: 32.9, lon: -96.8 },
    });
    const row = saved.value[0];
    expect(row.payload).not.toHaveProperty("status");
    expect(row.payload).not.toHaveProperty("distance_m");
    expect(row.at).toBeTypeOf("number");
  });

  it("says so in the sheet's own words", () => {
    expect(en["saved.hint"]).toMatch(/true when you tapped, not now/);
  });
});
