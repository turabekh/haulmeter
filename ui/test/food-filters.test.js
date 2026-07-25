// AI-CONTEXT: §11.3 "More filters" as tests — the sheet the constitution specified
// in v1.0 and nobody had built.
//
// What these defend:
// · The halal chip names WHO is claiming. A bare "Halal" would be the platform
//   asserting something it has not checked, which §23 forbids.
// · Search is bounded by the view, and the UI says so — otherwise an empty result
//   reads as "nobody anywhere cooks this".
// · "No cooks here" and "your filter hid them" are DIFFERENT facts with different
//   next actions. Showing the first when the second is true makes a driver stop
//   looking.
// · Forbidden #11 / §11.4 — the sheet never opens while DRIVING, and filters already
//   set keep narrowing the corridor.
// · The client never filters locally: it asks the server, which applies the quality
//   laws first.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import MoreFiltersSheet from "../src/core/components/MoreFiltersSheet.vue";
import MapSurface from "../src/surfaces/MapSurface.vue";
import { setToken, logout } from "../src/core/api.js";
import { useDriverState, DriverState } from "../src/core/state.js";
import en from "../src/core/i18n/en.json";

const FILTERS_KEY = "longhaul.food_filters";

let requests;
function stubFetch(entries = []) {
  requests = [];
  global.fetch = vi.fn((url) => {
    const u = String(url);
    requests.push(u);
    const path = u.replace("http://localhost:8008", "").split("?")[0];
    const body =
      path === "/vendors/appearances"
        ? entries
        : path === "/vendors/corridor"
          ? entries
          : path === "/map/overlay"
            ? { pins: [], clusters: [] }
            : [];
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
  });
}

beforeEach(() => {
  localStorage.removeItem(FILTERS_KEY);
  setToken("t");
});
afterEach(() => {
  logout();
  localStorage.removeItem(FILTERS_KEY);
  useDriverState().setState(DriverState.IDLE);
  vi.restoreAllMocks();
});

// --- the sheet itself ---
describe("More filters sheet (§11.3)", () => {
  it("names WHO is claiming halal, never a bare 'Halal' chip", () => {
    // the platform makes no halal claim of its own (§23); the cook does, and the
    // label says so
    const w = mount(MoreFiltersSheet);
    const chips = w.findAll(".chip").map((c) => c.text());
    expect(chips).toContain(en["vendor.halal_claim.self_declared"]);
    expect(chips).toContain(en["vendor.halal_claim.certified"]);
    expect(chips).not.toContain("Halal");
  });

  it("says plainly that it does not check the claim itself", () => {
    const w = mount(MoreFiltersSheet);
    expect(w.text()).toContain(en["filters.halal_hint"]);
    expect(w.text()).toContain("We do not check it ourselves");
  });

  it("says the search is bounded by the view", () => {
    // otherwise an empty result reads as "nobody anywhere cooks this"
    const w = mount(MoreFiltersSheet);
    expect(w.text()).toContain(en["filters.in_view"]);
  });

  it("labels each language in its own language", () => {
    // a Punjabi speaker scanning for Punjabi looks for ਪੰਜਾਬੀ, whatever language
    // the app happens to be in
    const w = mount(MoreFiltersSheet);
    const chips = w.findAll(".chip").map((c) => c.text());
    expect(chips).toContain("ਪੰਜਾਬੀ");
    expect(chips).toContain("Soomaali");
    expect(chips).not.toContain("Punjabi");
  });

  it("pre-selects nothing — a default filter would silently hide vendors", () => {
    const w = mount(MoreFiltersSheet);
    expect(w.findAll(".chip--on")).toHaveLength(0);
  });

  it("toggles a chip off when tapped again", async () => {
    const w = mount(MoreFiltersSheet);
    const chip = w.findAll(".chip")[0];
    await chip.trigger("click");
    expect(w.findAll(".chip--on")).toHaveLength(1);
    await chip.trigger("click");
    expect(w.findAll(".chip--on")).toHaveLength(0);
  });

  it("emits the chosen filters on apply", async () => {
    const w = mount(MoreFiltersSheet);
    await w.findAll(".chip")[0].trigger("click"); // self_declared
    w.vm.draft.q = "  tamales  ";
    await w.find(".cta").trigger("click");

    const [emitted] = w.emitted("update:modelValue").at(-1);
    expect(emitted).toEqual({ q: "tamales", language: "", halal: "self_declared" });
    expect(w.emitted("close")).toBeTruthy();
  });

  it("offers Clear only when something is actually filtering", async () => {
    const w = mount(MoreFiltersSheet);
    expect(w.findAll(".cta")).toHaveLength(1); // apply only
    await w.findAll(".chip")[0].trigger("click");
    expect(w.findAll(".cta")).toHaveLength(2);
  });
});

// --- the map surface ---
describe("Food filters on the map", () => {
  it("shows the filters affordance only on the Food preset", async () => {
    stubFetch();
    const w = mount(MapSurface, { global: { stubs: { RouterLink: true } } });
    await flushPromises();
    expect(w.find(".filters-chip").exists()).toBe(false);

    w.vm.preset = "food";
    await flushPromises();
    expect(w.find(".filters-chip").exists()).toBe(true);
  });

  it("sends the filters to the SERVER rather than filtering locally", async () => {
    // a client that held everything and hid some of it would be one bug away from
    // showing a driver a lapsed listing
    stubFetch();
    const w = mount(MapSurface, { global: { stubs: { RouterLink: true } } });
    await flushPromises();

    w.vm.filters = { q: "tamales", language: "pa", halal: "self_declared" };
    await flushPromises();

    const call = requests.find((u) => u.includes("/vendors/appearances") && u.includes("q="));
    expect(call).toBeTruthy();
    expect(call).toContain("q=tamales");
    expect(call).toContain("language=pa");
    expect(call).toContain("halal=self_declared");
  });

  it("survives a reload, because the choice must reach DRIVING", async () => {
    localStorage.setItem(FILTERS_KEY, JSON.stringify({ q: "", language: "so", halal: "" }));
    stubFetch();
    const w = mount(MapSurface, { global: { stubs: { RouterLink: true } } });
    await flushPromises();
    expect(w.vm.filters.language).toBe("so");
  });

  it("distinguishes 'no cooks here' from 'your filter hid them'", async () => {
    stubFetch();
    const w = mount(MapSurface, { global: { stubs: { RouterLink: true } } });
    w.vm.preset = "food";
    await flushPromises();
    // unfiltered: the Q-7 recruitment line
    expect(w.text()).toContain(en["vendor.none_nearby"]);
    expect(w.text()).not.toContain(en["filters.none_match"]);

    w.vm.filters = { q: "sushi", language: "", halal: "" };
    await flushPromises();
    // filtered: a different fact, and a different next action
    expect(w.text()).toContain(en["filters.none_match"]);
    expect(w.text()).toContain(en["filters.clear"]);
    expect(w.text()).not.toContain(en["vendor.none_nearby"]);
  });

  it("clears the filter from the empty state", async () => {
    stubFetch();
    const w = mount(MapSurface, { global: { stubs: { RouterLink: true } } });
    w.vm.preset = "food";
    w.vm.filters = { q: "sushi", language: "", halal: "" };
    await flushPromises();

    await w.find(".food-empty__cta").trigger("click");
    await flushPromises();
    expect(w.vm.filters).toEqual({ q: "", language: "", halal: "" });
  });

  it("never opens the sheet while DRIVING (Forbidden #11)", async () => {
    stubFetch();
    const w = mount(MapSurface, { global: { stubs: { RouterLink: true } } });
    await flushPromises();

    useDriverState().setState(DriverState.DRIVING);
    w.vm.filtering = true;
    await flushPromises();
    // no keyboard at speed — the sheet stays shut however `filtering` got set
    expect(w.findAll("input[type='search']")).toHaveLength(0);
  });

  it("keeps narrowing the corridor with filters set while stopped", async () => {
    stubFetch();
    const w = mount(MapSurface, { global: { stubs: { RouterLink: true } } });
    await flushPromises();
    w.vm.filters = { q: "", language: "", halal: "self_declared" };
    await flushPromises();

    useDriverState().setState(DriverState.DRIVING);
    await flushPromises();

    const corridor = requests.filter((u) => u.includes("/vendors/corridor"));
    expect(corridor.length).toBeGreaterThan(0);
    expect(corridor.at(-1)).toContain("halal=self_declared");
  });
});
