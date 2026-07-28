// AI-CONTEXT: Corridor mode's CONTENT (design-prd §11.4), which was a fixture.
//
// `MapSurface` passed a hardcoded `SAMPLE_CORRIDOR` — "Pilot #77 · full · 3.4 mi" and
// two more — into the one screen a driver sees at 65 mph and cannot check anything on.
// Meanwhile `GET /map/corridor` had existed since M1 shipped with nothing calling it.
// The fixture also carried a `status` the endpoint did not return, which is why the
// fix was never a prop swap: a fixture whose shape does not match its endpoint hides
// the endpoint, exactly as the sample load's "07:00" hid a live ISO timestamp.
//
// What these hold:
// · The fixture cannot come back — asserted at the source, because the next person to
//   need placeholder data will reach for the same drawer.
// · §11.7 — an unreported facility says so rather than rendering as though nobody
//   needed to ask. Silence in a stack of three reads as "fine" at speed.
// · §11.4's third figure — the price — renders, and an indicative one keeps its tilde
//   so a regional estimate cannot harden into a quote just by being in Mono.
// · Forbidden #11 / §13.4 — nothing in the stack is interactive while moving.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { mount } from "@vue/test-utils";
import CorridorStack from "../src/core/components/CorridorStack.vue";
import * as fixtures from "../src/core/fixtures.js";
import en from "../src/core/i18n/en.json";
import { messages, LAUNCH_LOCALES } from "../src/core/i18n/index.js";

const read = (p) => readFileSync(resolve(__dirname, "..", p), "utf8");

function entry(over = {}) {
  return {
    facility_id: "f-1",
    name: "Pilot #77",
    facility_type: "truck_stop",
    distance_m: 5400,
    status: null,
    reported_at: null,
    sample_size: 0,
    badges: [],
    ...over,
  };
}

describe("§23 entry 81 — the corridor is served, not invented", () => {
  it("no longer ships a corridor fixture at all", () => {
    // removed rather than left unused: an exported placeholder is one import away
    // from being back on the screen a driver cannot verify
    expect(fixtures.SAMPLE_CORRIDOR).toBeUndefined();
    expect(read("src/core/fixtures.js")).not.toMatch(/^export const SAMPLE_CORRIDOR/m);
  });

  it("wires the surface to the endpoint that was never called", () => {
    const src = read("src/surfaces/MapSurface.vue");
    expect(src).toMatch(/fetchCorridor/);
    expect(src).not.toMatch(/SAMPLE_CORRIDOR/);
  });

  it("sends the driver's real heading, never a hardcoded north", () => {
    // the defect was two calls defaulting to 0 and a third that could not be made
    const src = read("src/surfaces/MapSurface.vue");
    expect(src).toMatch(/headingDeg/);
    expect(src).not.toMatch(/heading_deg:\s*0\b/);
  });
});

describe("CorridorStack — §11.7 honesty in the stack", () => {
  it("says nobody has reported rather than rendering silence as a status", () => {
    const w = mount(CorridorStack, { props: { entries: [entry()] } });
    expect(w.text()).toContain(en["facility.no_report"]);
  });

  it("shows a status pill when there is one, and then no unknown line", () => {
    const w = mount(CorridorStack, { props: { entries: [entry({ status: "full" })] } });
    expect(w.text()).toContain(en["map.status.full"]);
    expect(w.text()).not.toContain(en["facility.no_report"]);
  });

  it("carries §11.4's price for a station that has one", () => {
    const w = mount(CorridorStack, {
      props: {
        entries: [
          entry({
            facility_type: "fuel_station",
            name: "QuikFuel",
            badges: [{ kind: "fuel_net", net: 394, indicative: false }],
          }),
        ],
      },
    });
    expect(w.text()).toContain("$3.94");
    expect(w.text()).not.toContain("~$3.94");
  });

  it("keeps the tilde on an indicative price, so an estimate stays an estimate", () => {
    const w = mount(CorridorStack, {
      props: {
        entries: [
          entry({
            facility_type: "fuel_station",
            badges: [{ kind: "fuel_net", net: 362, indicative: true }],
          }),
        ],
      },
    });
    expect(w.text()).toContain("~$3.62");
  });

  it("shows no price for a facility that has no price badge", () => {
    const w = mount(CorridorStack, { props: { entries: [entry()] } });
    expect(w.text()).not.toMatch(/\$/);
  });

  // AI-CONTEXT: this assertion used to read "nothing in the stack is a control", which
  // was true and is no longer: §11.4's deferred-safe tap (§23 entry 83) makes each
  // ENTRY a button. The invariant it was protecting is unchanged — nothing here opens a
  // flow — so it is restated rather than deleted. The scale and food lines stay inert,
  // because neither has anything to defer.
  it("opens no flow at speed: no links, and only the deferrable rows are controls", () => {
    const w = mount(CorridorStack, {
      props: {
        entries: [entry({ status: "full" })],
        scales: [{ facility_id: "s-1", name: "Scale", distance_m: 9000, status: "closed" }],
        vendors: [],
      },
    });
    expect(w.findAll("a")).toHaveLength(0); // nothing navigates
    // one control, and it is the entry's save — not the scale, not a vendor line
    expect(w.findAll("button")).toHaveLength(1);
    expect(w.find("button").classes()).toContain("corridor__tap");
  });
});

describe("the corridor's two honest empty states carry all six locales", () => {
  it("has a sentence for no-heading and for an empty stretch everywhere", () => {
    for (const locale of LAUNCH_LOCALES) {
      for (const key of ["corridor.no_heading", "corridor.empty"]) {
        expect(messages[locale][key], `${locale} is missing ${key}`).toBeTruthy();
      }
    }
  });
});
