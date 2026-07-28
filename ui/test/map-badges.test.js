// AI-CONTEXT: §11.2's badge slots, which were specified and never drawn.
//
// "Badge slots: price (fuel), $ (bookable), clock (dwell risk)." The overlay has
// serialized `fuel_net` and `bookable` since the marketplace modules landed, and
// MapCanvas rendered exactly one badge — food. So the Fuel preset painted a screen of
// stations each carrying a price and displayed none of them: comparing two pumps meant
// opening two sheets, which is the opposite of what a price layer is for.
//
// What these hold:
// · The two slots that HAVE data render; the one that does not (clock / dwell risk)
//   stays empty rather than being invented (§11.7).
// · §11.5 — labels below the zoom threshold do not appear, and two labels never
//   overlap. A dropped label is a layout decision, so it must not drop the FACT: the
//   price stays in the pin's accessible name either way.
// · §11.2 — the 44 dp target survives everything added to it.
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import MapCanvas from "../src/core/components/MapCanvas.vue";
import { placeLabels, PRICE_LABEL_MIN_ZOOM } from "../src/core/presentation.js";
import en from "../src/core/i18n/en.json";

function pin(over = {}) {
  return {
    facility_id: "f-1",
    name: "QuikFuel",
    facility_type: "fuel_station",
    shape: "circle",
    lat: 32.78,
    lon: -96.8,
    status: null,
    badges: [],
    freshness: null,
    ...over,
  };
}
const fuelBadge = (net = 394, indicative = false) => ({
  kind: "fuel_net",
  net,
  gross: 419,
  savings: 25,
  indicative,
});

describe("§11.2 price slot — the figure the fuel layer exists for", () => {
  it("draws the net price on a station's pin", () => {
    const w = mount(MapCanvas, { props: { pins: [pin({ badges: [fuelBadge()] })] } });
    expect(w.find(".pin__price").text()).toBe("$3.94");
  });

  it("keeps the tilde on an indicative price, so an estimate cannot read as a quote", () => {
    const w = mount(MapCanvas, {
      props: { pins: [pin({ badges: [fuelBadge(362, true)] })] },
    });
    expect(w.find(".pin__price").text()).toBe("~$3.62");
  });

  it("draws no price for a facility that has none", () => {
    const w = mount(MapCanvas, { props: { pins: [pin({ facility_type: "truck_stop" })] } });
    expect(w.find(".pin__price").exists()).toBe(false);
  });

  it("puts the price in the pin's accessible name too", () => {
    // §11.5's declutter is a LAYOUT rule. Applying it to assistive text would
    // withhold the fact rather than tidy the screen.
    const w = mount(MapCanvas, { props: { pins: [pin({ badges: [fuelBadge()] })] } });
    expect(w.find(".pin").attributes("aria-label")).toBe("QuikFuel · $3.94");
  });

  it("leaves an unpriced pin's accessible name as just its name", () => {
    const w = mount(MapCanvas, { props: { pins: [pin({ facility_type: "truck_stop" })] } });
    expect(w.find(".pin").attributes("aria-label")).toBe("QuikFuel");
  });
});

describe("§11.2 $ slot — a bookable lot says so on the map", () => {
  it("marks a pin carrying a bookable badge", () => {
    const w = mount(MapCanvas, {
      props: {
        pins: [
          pin({
            facility_type: "parking_property",
            badges: [{ kind: "bookable", value: 2400, spot_id: "s-1" }],
          }),
        ],
      },
    });
    const badge = w.find(".pin__badge--book");
    expect(badge.exists()).toBe(true);
    expect(badge.attributes("aria-label")).toBe(en["facility.book"]);
  });

  it("shows food and $ on opposite shoulders, so a bookable lot with a cook shows both", () => {
    const w = mount(MapCanvas, {
      props: {
        pins: [
          pin({
            facility_type: "parking_property",
            has_food: true,
            badges: [{ kind: "bookable", value: 2400 }],
          }),
        ],
      },
    });
    expect(w.findAll(".pin__badge")).toHaveLength(2);
    expect(w.find(".pin__badge--book").exists()).toBe(true);
  });

  it("does not mark a lot with no bookable badge — a full lot is not bookable", () => {
    const w = mount(MapCanvas, {
      props: { pins: [pin({ facility_type: "parking_property" })] },
    });
    expect(w.find(".pin__badge--book").exists()).toBe(false);
  });
});

// AI-CONTEXT: this slot was empty ON PURPOSE until M2-FR3 existed (§23 entry 87) —
// `m02.detention_risk` was a stub returning `basis: "m3_pending"`, so there was nothing
// to draw and drawing anything would have been the fake confidence §11.7 forbids. It
// has a signal now, and the SERVER decides whether the mark is warranted: the sample
// floor and the threshold live with the data, so the canvas draws what it is handed.
describe("§11.2 clock slot — a dock that runs long", () => {
  const riskBadge = { kind: "dwell_risk", value: 0.72, sample_size: 11, basis: "tracked_stops" };

  it("marks a receiver the server flagged", () => {
    const w = mount(MapCanvas, {
      props: {
        pins: [pin({ facility_type: "shipper_receiver", name: "Harvest Foods DC",
                     badges: [riskBadge] })],
      },
    });
    expect(w.find(".pin__badge--dwell").exists()).toBe(true);
    expect(w.find(".pin__badge--dwell").attributes("aria-label")).toBe(en["facility.dwell_risk"]);
  });

  it("draws nothing for a receiver the server did not flag", () => {
    // below the sample floor or under the threshold, the badge simply is not sent —
    // the client never re-derives the decision
    const w = mount(MapCanvas, {
      props: { pins: [pin({ facility_type: "shipper_receiver", name: "Harvest Foods DC" })] },
    });
    expect(w.findAll(".pin__badge")).toHaveLength(0);
    expect(w.find(".pin__price").exists()).toBe(false);
  });

  it("keeps the clock clear of the other two slots", () => {
    // no facility type carries all three today, but the shoulders must not collide
    // if one ever does
    const w = mount(MapCanvas, {
      props: {
        pins: [pin({ facility_type: "shipper_receiver", has_food: true,
                     badges: [riskBadge, { kind: "bookable", value: 2400 }] })],
      },
    });
    expect(w.findAll(".pin__badge")).toHaveLength(3);
  });
});

// AI-CONTEXT: these test the RULE, not the render. A mounted canvas has no viewport
// and no zoom in a test runner, so every assertion above runs the "no live map" path —
// which means the threshold and the overlap test would have shipped unexercised had
// they stayed inside the component. §19 says logic lives in core/; this is why.
describe("§11.5 declutter — labels appear at zoom, and never on top of each other", () => {
  const at = (id, x, y) => ({ id, label: "$3.94", x, y });

  it("draws nothing below the zoom threshold", () => {
    const shown = placeLabels([at("a", 100, 100)], { zoom: PRICE_LABEL_MIN_ZOOM - 1 });
    expect(shown).toEqual({});
  });

  it("draws at the threshold itself", () => {
    const shown = placeLabels([at("a", 100, 100)], { zoom: PRICE_LABEL_MIN_ZOOM });
    expect(shown).toEqual({ a: "$3.94" });
  });

  it("drops the second of two labels that would overlap", () => {
    // 6 px apart: two price plates on top of each other, which costs a driver their
    // trust in both figures
    const shown = placeLabels([at("a", 100, 100), at("b", 106, 100)], { zoom: 12 });
    expect(shown).toEqual({ a: "$3.94" });
  });

  it("keeps both when they clear each other", () => {
    const shown = placeLabels([at("a", 100, 100), at("b", 400, 400)], { zoom: 12 });
    expect(Object.keys(shown).sort()).toEqual(["a", "b"]);
  });

  it("keeps the FIRST — the order the server ranked them in", () => {
    // the nearest station keeps its figure; the one behind it loses the label only,
    // never the pin and never the tap
    const shown = placeLabels([at("near", 100, 100), at("far", 102, 102)], { zoom: 12 });
    expect(shown).toEqual({ near: "$3.94" });
  });

  it("ignores the threshold where there is no map to have a zoom", () => {
    // the placeholder canvas: no viewport, and never enough pins to collide
    const shown = placeLabels([{ id: "a", label: "$3.94" }], { zoom: null });
    expect(shown).toEqual({ a: "$3.94" });
  });

  it("skips items with nothing to say", () => {
    const shown = placeLabels([{ id: "a", label: null, x: 1, y: 1 }], { zoom: 12 });
    expect(shown).toEqual({});
  });
});

describe("§11.2 — everything added to a pin leaves its target alone", () => {
  it("keeps the 44 dp hit area with a price and two badges on it", () => {
    const w = mount(MapCanvas, {
      props: {
        pins: [
          pin({
            has_food: true,
            badges: [fuelBadge(), { kind: "bookable", value: 2400 }],
          }),
        ],
      },
    });
    // the label is decoration on top of the button, never a competing target
    expect(w.find(".pin__price").attributes("aria-hidden")).toBe("true");
    expect(w.find(".pin").element.tagName).toBe("BUTTON");
  });
});
