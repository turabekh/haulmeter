// AI-CONTEXT: E3.1 weigh stations in the driver UI (design-prd §22.3 DoD).
//
// What these defend, in order of how much it would cost to get wrong:
// · The INVERTED valence. `closed` is the good news for a driver and takes the
//   ledger token; `open` takes the marker token. Reading these the ordinary way
//   round would tell a driver the opposite of the truth at 65 mph.
// · C-1 — the pill always carries a label, in the driver's language, so colour is
//   never the only signal.
// · §11.7 — an unreported scale says "no recent report" rather than rendering as
//   though someone had said it was shut.
// · Forbidden #11 / §13.4 — a scale line in corridor mode is read-only.
// · The question and the SIGNAL come from one place, so a scale's answer can never
//   be filed as a parking reading.
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import CorridorStack from "../src/core/components/CorridorStack.vue";
import ReportSheet from "../src/core/components/ReportSheet.vue";
import StatusPill from "../src/core/components/StatusPill.vue";
import FacilityCard from "../src/core/components/FacilityCard.vue";
import { routes } from "../src/router.js";
import {
  PARKING_STATUS,
  WEIGH_STATUS,
  SCALE_TYPES,
  statusPresentation,
  statusReportFor,
} from "../src/core/presentation.js";
import en from "../src/core/i18n/en.json";
import { messages, LAUNCH_LOCALES } from "../src/core/i18n/index.js";

const LOCALES = LAUNCH_LOCALES;

function scalePin(over = {}) {
  return {
    facility_id: "f-1",
    name: "I-90 Weigh Station EB",
    facility_type: "weigh_station",
    shape: "small_square",
    lat: 43.25,
    lon: -89.4,
    status: null,
    badges: [],
    freshness: null,
    ...over,
  };
}

function router() {
  return createRouter({ history: createMemoryHistory(), routes });
}

// --- the inverted valence ---
describe("weigh-station status semantics (§23 decision)", () => {
  it("gives CLOSED the good-news token and OPEN the attention one", () => {
    // deliberately inverted against parking: a closed scale means roll on
    expect(WEIGH_STATUS.closed.token).toBe("--ledger-500");
    expect(WEIGH_STATUS.open.token).toBe("--marker-500");
  });

  it("leaves the parking vocabulary exactly as it was", () => {
    expect(PARKING_STATUS.empty.token).toBe("--ledger-500");
    expect(PARKING_STATUS.some.token).toBe("--marker-500");
    expect(PARKING_STATUS.full.token).toBe("--flare-500");
  });

  it("resolves both vocabularies through one lookup", () => {
    expect(statusPresentation("closed").token).toBe("--ledger-500");
    expect(statusPresentation("full").token).toBe("--flare-500");
    expect(statusPresentation("nonsense").token).toBe("--text-3");
  });

  it("uses only existing tokens — no colour is invented for this layer (§6)", () => {
    const known = new Set(["--ledger-500", "--marker-500", "--flare-500", "--text-3"]);
    for (const v of Object.values(WEIGH_STATUS)) expect(known.has(v.token)).toBe(true);
  });
});

// --- C-1: the label carries the meaning ---
describe("the status pill never relies on colour alone (C-1)", () => {
  it("renders a translated label beside the colour", () => {
    const w = mount(StatusPill, { props: { status: "closed" } });
    expect(w.text()).toBe(en["map.status.closed"]);
    expect(w.attributes("style")).toContain("--ledger-500");
  });

  it("keys every status label to a real string, so nothing renders as a raw key", () => {
    // locale-completeness.test.js proves the six locales agree; what it cannot know
    // is which keys the CODE reaches for. This closes that gap.
    for (const p of [...Object.values(WEIGH_STATUS), ...Object.values(PARKING_STATUS)]) {
      expect(p.labelKey, "every status needs a translated label (C-1)").toBeTruthy();
      for (const loc of LOCALES) {
        expect(messages[loc][p.labelKey], `${loc} missing ${p.labelKey}`).toBeTruthy();
      }
    }
    expect(statusPresentation("nonsense").labelKey).toBe("map.status.unknown");
    for (const loc of LOCALES) expect(messages[loc]["map.status.unknown"]).toBeTruthy();
  });
});

// --- the report sheet follows the facility ---
describe("the report vocabulary follows what the facility IS", () => {
  it("asks a scale whether it is open, not how full it is", () => {
    const spec = statusReportFor("weigh_station");
    expect(spec.signal).toBe("weigh_station_status");
    expect(spec.options.map((o) => o.status)).toEqual(["closed", "open"]);
  });

  it("still asks everything else about parking", () => {
    for (const type of ["truck_stop", "rest_area", "parking_property", undefined]) {
      const spec = statusReportFor(type);
      expect(spec.signal).toBe("parking_fullness");
      expect(spec.options.map((o) => o.status)).toEqual(["empty", "some", "full"]);
    }
  });

  it("renders the scale question and two glove-sized options", () => {
    const w = mount(ReportSheet, { props: { facilityType: "scale" } });
    expect(w.find(".report__q").text()).toBe(en["map.report.question_scale"]);
    const opts = w.findAll(".report__opt");
    expect(opts).toHaveLength(2);
    expect(opts.map((o) => o.text())).toEqual([en["map.status.closed"], en["map.status.open"]]);
  });

  it("still renders the parking question by default", () => {
    const w = mount(ReportSheet);
    expect(w.find(".report__q").text()).toBe(en["map.report.question"]);
    expect(w.findAll(".report__opt")).toHaveLength(3);
  });

  it("emits the chosen status", async () => {
    const w = mount(ReportSheet, { props: { facilityType: "weigh_station" } });
    await w.findAll(".report__opt")[1].trigger("click");
    expect(w.emitted("report")[0]).toEqual(["open"]);
  });
});

// --- the card ---
describe("the facility card for a scale", () => {
  it("offers the report affordance", () => {
    const w = mount(FacilityCard, {
      props: { pin: scalePin() },
      global: { plugins: [router()] },
    });
    const labels = w.findAll("button").map((b) => b.text());
    expect(labels).toContain(en["map.report"]);
  });

  it("says nobody has reported rather than showing nothing (§11.7)", () => {
    const w = mount(FacilityCard, {
      props: { pin: scalePin() },
      global: { plugins: [router()] },
    });
    expect(w.text()).toContain(en["facility.no_report"]);
    expect(w.findComponent(StatusPill).exists()).toBe(false);
  });

  it("shows the status once a driver has reported one", () => {
    const w = mount(FacilityCard, {
      props: {
        pin: scalePin({
          status: "open",
          freshness: { reported_at: new Date().toISOString(), sample_size: 2 },
        }),
      },
      global: { plugins: [router()] },
    });
    expect(w.findComponent(StatusPill).text()).toBe(en["map.status.open"]);
    expect(w.text()).toContain("2 drivers"); // §11.7 freshness, as everywhere else
    expect(w.text()).not.toContain(en["facility.no_report"]);
  });

  it("leads with Navigate — a scale is not bookable or fuelable", () => {
    const w = mount(FacilityCard, {
      props: { pin: scalePin() },
      global: { plugins: [router()] },
    });
    expect(w.find(".cta").text()).toContain(en["facility.navigate"]);
  });
});

// --- corridor mode ---
describe("scales in corridor mode (§11.4 / Forbidden #11)", () => {
  const ahead = [
    { facility_id: "s-1", name: "Mauston Scale", distance_m: 12000, status: "closed" },
    { facility_id: "s-2", name: "Black River Scale", distance_m: 41000, status: null },
  ];

  it("renders one read-only line per scale, with no tap target", () => {
    const w = mount(CorridorStack, { props: { entries: [], scales: ahead } });
    const lines = w.findAll(".corridor__card--scale");
    expect(lines).toHaveLength(2);
    for (const line of lines) expect(line.find("button").exists()).toBe(false);
  });

  it("puts scales ahead of the other lines — they are the ones with a deadline", () => {
    const w = mount(CorridorStack, {
      props: {
        entries: [{ facility_id: "e-1", name: "Loves", distance_m: 5000, status: "some" }],
        scales: ahead,
      },
    });
    expect(w.findAll(".corridor__card")[0].classes()).toContain("corridor__card--scale");
  });

  it("shows the status pill, and 'no recent report' where there is none", () => {
    const w = mount(CorridorStack, { props: { entries: [], scales: ahead } });
    const lines = w.findAll(".corridor__card--scale");
    expect(lines[0].text()).toContain(en["map.status.closed"]);
    expect(lines[1].text()).toContain(en["facility.no_report"]);
  });

  it("shows miles as a Mono figure, like every other corridor line", () => {
    const w = mount(CorridorStack, { props: { entries: [], scales: ahead } });
    expect(w.find(".corridor__card--scale .corridor__miles").text()).toBe("7.5 mi");
  });

  it("renders nothing when the layer is off (the server sends an empty list)", () => {
    const w = mount(CorridorStack, { props: { entries: [], scales: [] } });
    expect(w.findAll(".corridor__card--scale")).toHaveLength(0);
  });
});

describe("which types count as scales", () => {
  it("covers both the enforcement station and the commercial scale", () => {
    expect(SCALE_TYPES.has("weigh_station")).toBe(true);
    expect(SCALE_TYPES.has("scale")).toBe(true);
    expect(SCALE_TYPES.has("truck_stop")).toBe(false);
  });
});
