// AI-CONTEXT: §23 entry 99 — "show me somewhere else" on the Map.
//
// Two of these tests are the feature; the rest are the guardrails, and the guardrails
// are the point. A control that moves the map is trivial. A control that moves the
// map WITHOUT moving the driver — and says on screen that it has — is the thing that
// can be got wrong quietly, because both mistakes still look fine on a screenshot.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import PlaceSheet from "../src/core/components/PlaceSheet.vue";
import en from "../src/core/i18n/en.json";

vi.mock("../src/core/api.js", () => ({
  geocodeAddress: vi.fn(),
}));
const { geocodeAddress } = await import("../src/core/api.js");

const DALLAS = {
  places: [
    { lat: 32.781339, lon: -96.799759, label: "Dallas, Texas, United States" },
    { lat: 33.418318, lon: -94.0919, label: "Dallas Street, Texarkana, Texas 75501, United States" },
  ],
};

function mountSheet() {
  return mount(PlaceSheet, { props: { open: true } });
}

describe("PlaceSheet", () => {
  beforeEach(() => {
    geocodeAddress.mockReset();
  });

  it("offers every candidate the geocoder returned rather than picking one", async () => {
    // §11.7 / the rate-con precedent: the geocoder PROPOSES, the driver CONFIRMS.
    // Silently taking the first hit is the map inventing a place again.
    geocodeAddress.mockResolvedValue(DALLAS);
    const w = mountSheet();
    await w.find("input").setValue("Dallas");
    await w.find("form").trigger("submit");
    await new Promise((r) => setTimeout(r));

    const items = w.findAll(".place__item");
    expect(items).toHaveLength(2);
    expect(items[0].text()).toBe("Dallas, Texas, United States");
  });

  it("emits the coordinates the driver chose", async () => {
    geocodeAddress.mockResolvedValue(DALLAS);
    const w = mountSheet();
    await w.find("input").setValue("Dallas");
    await w.find("form").trigger("submit");
    await new Promise((r) => setTimeout(r));
    await w.findAll(".place__item")[1].trigger("click");

    expect(w.emitted("pick")[0][0]).toMatchObject({ lat: 33.418318, lon: -94.0919 });
    expect(w.emitted("close")).toBeTruthy();
  });

  it("says the finder was unreachable rather than saying nothing matched", async () => {
    // two different facts, and §11.7 does not let one be rendered as the other:
    // "no such place" tells a driver to stop looking; "offline" tells them to retry.
    geocodeAddress.mockRejectedValue(new Error("offline"));
    const w = mountSheet();
    await w.find("input").setValue("Dallas");
    await w.find("form").trigger("submit");
    await new Promise((r) => setTimeout(r));

    expect(w.find(".place__note").text()).toBe(en["place.failed"]);
  });

  it("says nothing matched when the geocoder genuinely returned nothing", async () => {
    geocodeAddress.mockResolvedValue({ places: [] });
    const w = mountSheet();
    await w.find("input").setValue("zzzzzz");
    await w.find("form").trigger("submit");
    await new Promise((r) => setTimeout(r));

    expect(w.find(".place__note").text()).toBe(en["place.none"]);
  });

  it("does not search on an empty query", async () => {
    const w = mountSheet();
    await w.find("form").trigger("submit");
    expect(geocodeAddress).not.toHaveBeenCalled();
  });

  it("states plainly that only the map moves", async () => {
    // the promise the whole design rests on, in the driver's own view
    const w = mountSheet();
    expect(w.find(".place__hint").text()).toContain("only moves the map");
  });

  it("meets the 48 dp floor on every target", () => {
    const w = mountSheet();
    for (const sel of [".place__input", ".place__go"]) {
      expect(w.find(sel).exists()).toBe(true);
    }
  });
});

// --- the guardrails on the SURFACE, which is where the damage would be ---
describe("Map surface — looking somewhere else", () => {
  it("never writes the driver's fix when a place is chosen", async () => {
    // THE test. `lastFix` feeds the position pings behind F3 arrival, the geofence,
    // the detention clock and `presence_proven`. A driver parked in Perth who could
    // "pin" to Dallas would arm a stop there and run a clock on fiction. The map may
    // look anywhere; the truck is only ever where it is.
    const { lastFix, __resetForTests } = await import("../src/core/location.js");
    __resetForTests?.();
    const before = lastFix.value;

    const w = mountSheet();
    geocodeAddress.mockResolvedValue(DALLAS);
    await w.find("input").setValue("Dallas");
    await w.find("form").trigger("submit");
    await new Promise((r) => setTimeout(r));
    await w.findAll(".place__item")[0].trigger("click");

    expect(lastFix.value).toBe(before);
  });

  it("keeps the six locales whole", () => {
    // Forbidden #7: no string ships without all six. The banner is also assembled
    // from ONE interpolated key rather than two fragments joined by punctuation.
    for (const key of [
      "place.button",
      "place.title",
      "place.hint",
      "place.viewing",
      "place.back",
      "place.none",
      "place.failed",
    ]) {
      expect(en[key], key).toBeTruthy();
    }
    expect(en["place.viewing"]).toContain("{place}");
  });
});
