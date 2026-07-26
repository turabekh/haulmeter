// AI-CONTEXT: deciding whether to GO — the half of the food flow that was missing.
//
// The sheet told a driver a cook existed and then offered them no way to act on it:
// no distance, no lot name, and no navigate. What these defend:
//
// · **No location, no distance.** The map holds a default position until the first
//   real fix. A distance measured from that default would be confidently wrong, so
//   the origin is withheld and nothing renders — never a placeholder, never a guess.
// · **Whole miles.** A direct line rendered to one decimal implies routing precision
//   a straight line does not have. Truck routing is PRD §17 Q9 and open, so nothing
//   here may imply an arrival time either.
// · **Navigate is the primary action**, because the sheet is read while deciding
//   whether to go, and a crowd-contribution affordance must not outrank it.
// · **The lot is named**, because a sheet that cannot say where a cook is standing
//   cannot honestly offer to take anyone there.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import VendorSheet from "../src/core/components/VendorSheet.vue";
import FacilityCard from "../src/core/components/FacilityCard.vue";
import MapSurface from "../src/surfaces/MapSurface.vue";
import MapCanvas from "../src/core/components/MapCanvas.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import { useDriverState, DriverState } from "../src/core/state.js";
import { formatMiles } from "../src/core/presentation.js";
import { windowLabel } from "../src/core/vendors.js";
import en from "../src/core/i18n/en.json";

const HOUR = 3600 * 1000;
const testRouter = () => createRouter({ history: createMemoryHistory(), routes });
const mountSheet = (props) => mount(VendorSheet, { props, global: { plugins: [testRouter()] } });

function appearance(over = {}) {
  const now = Date.now();
  return {
    vendor_id: "v-1",
    name: "Ana's Tamales",
    facility_id: "f-1",
    facility_name: "Loves 212",
    lat: 43.07,
    lon: -89.4,
    starts_at: new Date(now - HOUR).toISOString(),
    ends_at: new Date(now + 3 * HOUR).toISOString(),
    bucket: 1,
    distance_m: 4828, // 3.0 mi
    sold_out: false,
    verify_status: "verified",
    offerings: [{ name: "Tamales", price_cents: 1200 }],
    presence: null,
    ...over,
  };
}

function sheet(over = {}) {
  return {
    vendor_id: "v-1",
    name: "Ana's Tamales",
    verify_status: "verified",
    languages: ["es", "en"],
    halal_claim: "not_claimed",
    halal_disclosure: "No halal claim",
    shows_up: { confirmed: 19, published: 20 },
    appearances: [appearance()],
    reviews: { average: null, reviewers: 0, items: [] },
    ...over,
  };
}

beforeEach(() => useDriverState().setState(DriverState.IDLE));
afterEach(() => {
  vi.unstubAllGlobals();
  logout();
});

describe("the miles formatter (one source for every distance)", () => {
  it("renders a direct distance in whole miles", () => {
    expect(formatMiles(4828)).toBe("3");
    expect(formatMiles(1609)).toBe("1");
  });

  it("keeps a decimal only for a corridor distance, which is measured along a road", () => {
    expect(formatMiles(4828, { precise: true })).toBe("3.0");
  });

  it("returns nothing for nothing, so a caller cannot render a zero it was never given", () => {
    expect(formatMiles(null)).toBe(null);
    expect(formatMiles(undefined)).toBe(null);
  });
});

describe("the window, not just its end", () => {
  it("says when a cook OPENS if they have not started", () => {
    const now = Date.now();
    const got = windowLabel(
      new Date(now + 2 * HOUR).toISOString(),
      new Date(now + 6 * HOUR).toISOString(),
      now,
    );
    expect(got.key).toBe("vendor.opens");
  });

  it("gives both ends once they are open, so 'Today' stops being ambiguous", () => {
    const now = Date.now();
    const got = windowLabel(
      new Date(now - HOUR).toISOString(),
      new Date(now + 3 * HOUR).toISOString(),
      now,
    );
    expect(got.key).toBe(null);
    expect(got.value).toContain("–");
  });
});

describe("the vendor sheet decides a detour", () => {
  it("names the lot each appearance is at", () => {
    const w = mountSheet({ sheet: sheet() });
    expect(w.find(".vs__lot").text()).toBe("Loves 212");
  });

  it("shows the distance in whole miles and says once that it is direct", () => {
    const w = mountSheet({ sheet: sheet() });
    expect(w.find(".vs__miles").text()).toBe(`3 ${en["unit.mi"]}`);
    expect(w.text()).toContain(en["vendor.distance_direct"]);
  });

  it("shows no distance at all, and no caption, when the driver shared no location", () => {
    const w = mountSheet({ sheet: sheet({ appearances: [appearance({ distance_m: null })] }) });
    expect(w.find(".vs__miles").exists()).toBe(false);
    expect(w.text()).not.toContain(en["vendor.distance_direct"]);
    // and nothing invents a dash or a zero in its place
    expect(w.text()).not.toContain(` 0 ${en["unit.mi"]}`);
  });

  it("makes Navigate the PRIMARY action and Here now secondary", () => {
    const w = mountSheet({ sheet: sheet() });
    const primary = w.findAll(".cta").filter((b) => !b.classes().some((c) => c.startsWith("cta--")));
    expect(primary).toHaveLength(1);
    expect(primary[0].text()).toContain(en["vendor.navigate"]);

    const hereNow = w.findAll(".cta").find((b) => b.text().includes(en["vendor.here_now"]));
    expect(hereNow.classes()).toContain("cta--secondary");
  });

  it("navigates to the appearance the driver TAPPED, not merely the next one", () => {
    const tapped = appearance({
      facility_id: "f-2",
      facility_name: "Pilot 88",
      lat: 44.1,
      lon: -88.2,
    });
    const w = mountSheet({ sheet: sheet(), target: tapped });
    w.findAll(".cta").find((b) => b.text().includes(en["vendor.navigate"])).trigger("click");
    expect(w.emitted("navigate")[0][0].facility_id).toBe("f-2");
  });

  it("offers no Navigate when it holds no coordinates — a button that goes nowhere is worse", () => {
    const w = mountSheet({
      sheet: sheet({ appearances: [appearance({ lat: null, lon: null })] }),
    });
    expect(w.text()).not.toContain(en["vendor.navigate"]);
  });

  it("never promises an arrival time (§17 Q9 is open)", () => {
    const w = mountSheet({ sheet: sheet() });
    const text = w.text().toLowerCase();
    for (const forbidden of ["eta", "arrive", "arrival", "minutes away", "you'll make"]) {
      expect(text).not.toContain(forbidden);
    }
  });

  it("stays read-only while DRIVING — no navigate, no confirm (Forbidden #11)", () => {
    useDriverState().setState(DriverState.DRIVING);
    const w = mountSheet({ sheet: sheet() });
    expect(w.text()).not.toContain(en["vendor.navigate"]);
    expect(w.text()).not.toContain(en["vendor.here_now"]);
    // reading is still fine: the lot and the window are there at a glance
    expect(w.find(".vs__lot").text()).toBe("Loves 212");
  });
});

describe("the facility card's food rows", () => {
  const pin = {
    facility_id: "f-1",
    name: "Loves 212",
    facility_type: "truck_stop",
    status: "open",
    lat: 43.07,
    lon: -89.4,
    badges: [],
  };

  it("carries the distance next to the window", () => {
    const w = mount(FacilityCard, {
      props: { pin, vendors: [appearance()] },
      global: { plugins: [testRouter()] },
    });
    expect(w.find(".vendor__miles").text()).toContain(`3 ${en["unit.mi"]}`);
  });

  it("renders no distance when there is none to render", () => {
    const w = mount(FacilityCard, {
      props: { pin, vendors: [appearance({ distance_m: null })] },
      global: { plugins: [testRouter()] },
    });
    expect(w.find(".vendor__miles").exists()).toBe(false);
  });
});

describe("the map only sends a position it actually has", () => {
  const foodCalls = (stub) =>
    stub.mock.calls.filter((c) => String(c[0]).includes("/vendors/appearances"));

  it("asks for appearances WITHOUT an origin before any location fix", async () => {
    setToken("tok-food");
    const stub = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
    );
    vi.stubGlobal("fetch", stub);
    mount(MapSurface, { global: { plugins: [testRouter()] } });
    await flushPromises();

    const calls = foodCalls(stub);
    expect(calls.length).toBeGreaterThan(0);
    // the map holds a default centre until the driver is located; sending it would
    // print a distance measured from a place they have never been
    expect(String(calls[0][0])).not.toMatch(/[?&]lat=/);
  });

  it("sends the origin once the driver has actually been located", async () => {
    setToken("tok-food");
    const stub = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
    );
    vi.stubGlobal("fetch", stub);
    const w = mount(MapSurface, { global: { plugins: [testRouter()] } });
    await flushPromises();

    w.findComponent(MapCanvas).vm.$emit("located", { lat: 43.07, lon: -89.4 });
    await flushPromises();
    w.findComponent(MapCanvas).vm.$emit("bounds", {
      min_lat: 42.9, min_lon: -89.6, max_lat: 43.2, max_lon: -89.2,
    });
    await new Promise((r) => setTimeout(r, 350)); // the bounds debounce
    await flushPromises();

    const last = String(foodCalls(stub).at(-1)[0]);
    expect(last).toMatch(/[?&]lat=43\.07/);
    expect(last).toMatch(/[?&]lon=-89\.4/);
  });
});

// following: the consent the flow never had. Before this the only vendor
// notification went to drivers who had already CONFIRMED a cook in person, so the
// loop was closed to exactly the people it should have been opening for.
describe("following a cook", () => {
  it("says what one tap turns on, before it is tapped", () => {
    const w = mountSheet({ sheet: sheet({ following: false }) });
    const follow = w.findAll(".cta").find((b) => b.text().includes(en["vendor.follow"]));
    expect(follow).toBeTruthy();
    // E-D1: the control supplying the consent must name what it enables, and the
    // caps in the same breath — "we will tell you" must not read as "we will pester"
    expect(w.text()).toContain(en["vendor.follow_note"]);
    expect(en["vendor.follow_note"].toLowerCase()).toContain("one a day");
  });

  it("reads as Following once it is on, and offers to stop", async () => {
    const w = mountSheet({ sheet: sheet({ following: true }) });
    const button = w.findAll(".cta").find((b) => b.text().includes(en["vendor.following"]));
    expect(button.attributes("aria-pressed")).toBe("true");
    expect(w.text()).toContain(en["vendor.follow_on_note"]);
    expect(w.text()).not.toContain(en["vendor.follow_note"]);

    await button.trigger("click");
    expect(w.emitted("unfollow")).toBeTruthy();
    expect(w.emitted("follow")).toBeFalsy();
  });

  it("emits follow when it is off", async () => {
    const w = mountSheet({ sheet: sheet({ following: false }) });
    await w.findAll(".cta").find((b) => b.text().includes(en["vendor.follow"])).trigger("click");
    expect(w.emitted("follow")).toBeTruthy();
  });

  it("never outranks Navigate — following is not the reason a driver opened this", () => {
    const w = mountSheet({ sheet: sheet({ following: false }) });
    const primary = w.findAll(".cta").filter((b) => !b.classes().some((c) => c.startsWith("cta--")));
    expect(primary).toHaveLength(1);
    expect(primary[0].text()).toContain(en["vendor.navigate"]);
  });

  it("does not render while DRIVING (Forbidden #11)", () => {
    useDriverState().setState(DriverState.DRIVING);
    const w = mountSheet({ sheet: sheet({ following: false }) });
    expect(w.text()).not.toContain(en["vendor.follow"]);
    expect(w.text()).not.toContain(en["vendor.following"]);
  });
});
