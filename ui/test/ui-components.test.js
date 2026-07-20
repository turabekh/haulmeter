// AI-CONTEXT: Component tests for the M1 shell + Map surface. Assert the design
// laws that are testable in jsdom: exactly 5 labeled tabs & no hamburger
// (NAV-1), preset chips (§11.3), facility card single primary CTA + report, and
// DRIVING → Corridor mode (§11.4).
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import TabBar from "../src/core/components/TabBar.vue";
import PresetChips from "../src/core/components/PresetChips.vue";
import FacilityCard from "../src/core/components/FacilityCard.vue";
import MapSurface from "../src/surfaces/MapSurface.vue";
import FacilityProfileSurface from "../src/surfaces/FacilityProfileSurface.vue";
import TheMeter from "../src/core/components/TheMeter.vue";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import MoneySurface from "../src/surfaces/MoneySurface.vue";
import DocsSurface from "../src/surfaces/DocsSurface.vue";
import BookingSurface from "../src/surfaces/BookingSurface.vue";
import FuelSurface from "../src/surfaces/FuelSurface.vue";
import LoadCalcSurface from "../src/surfaces/LoadCalcSurface.vue";
import { routes } from "../src/router.js";
import { useDriverState, DriverState } from "../src/core/state.js";

const routerStub = { global: { stubs: { "router-link": { template: "<a class='rl'><slot/></a>" } } } };

function testRouter() {
  return createRouter({ history: createMemoryHistory(), routes });
}

describe("TabBar (design-prd §4 NAV-1)", () => {
  it("renders exactly 5 labeled tabs and no hamburger", () => {
    const w = mount(TabBar, routerStub);
    const tabs = w.findAll(".tab");
    expect(tabs).toHaveLength(5);
    const text = w.text();
    for (const label of ["Map", "Load", "Money", "Docs", "More"]) {
      expect(text).toContain(label);
    }
    expect(w.html().toLowerCase()).not.toContain("hamburger");
  });
});

describe("PresetChips (design-prd §11.3)", () => {
  it("offers the four presets and emits selection", async () => {
    const w = mount(PresetChips, { props: { modelValue: "drive" } });
    const chips = w.findAll(".chip");
    expect(chips).toHaveLength(4);
    await chips[1].trigger("click");
    expect(w.emitted()["update:modelValue"][0]).toEqual(["tonight"]);
  });
});

describe("FacilityCard (design-prd §10.1)", () => {
  it("shows Navigate as the primary CTA and emits navigate", async () => {
    const pin = {
      facility_id: "f-1",
      name: "Loves #212",
      status: "some",
      badges: [{ kind: "fuel_price", value: 4.19 }],
      freshness: { reported_at: new Date().toISOString(), sample_size: 3 },
    };
    const router = testRouter();
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [router] } });
    expect(w.text()).toContain("Navigate");
    expect(w.text()).toContain("View facility");
    expect(w.text()).toContain("$4.19");
    await w.find(".cta").trigger("click");
    expect(w.emitted().navigate).toBeTruthy();
  });
});

describe("FacilityCard — bookable parking (M6, §227 / §12.2)", () => {
  it("leads with a Book CTA that names the price and emits book", async () => {
    const pin = {
      facility_id: "f-3",
      name: "Yardline Secured Parking",
      facility_type: "parking_property",
      status: "empty",
      badges: [{ kind: "bookable", value: 2400, spot_id: "spot-f3-a1" }],
      freshness: { reported_at: new Date().toISOString(), sample_size: 1 },
    };
    const router = testRouter();
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [router] } });
    // §12.2: the primary button says exactly what happens, with the one price
    expect(w.find(".cta").text()).toContain("Book spot");
    expect(w.find(".cta").text()).toContain("$24.00");
    await w.find(".cta").trigger("click");
    expect(w.emitted().book).toBeTruthy();
    expect(w.emitted().book[0][0].facility_id).toBe("f-3");
    // Navigate stays available, demoted to secondary
    expect(w.text()).toContain("Navigate");
  });
});

describe("BookingSurface — checkout (M6, NAV-3 / one final price)", () => {
  async function mountAt(query) {
    const router = testRouter();
    router.push({ path: "/book/spot-f3-a1", query });
    await router.isReady();
    const w = mount(BookingSurface, { global: { plugins: [router] } });
    await flushPromises();
    return w;
  }

  it("shows ONE final price = nightly × nights, verb persists into confirm", async () => {
    const w = await mountAt({ name: "Yardline Secured Parking", nightly: "2400" });
    expect(w.find(".total__figure").text()).toBe("$24.00"); // 1 night default
    // add a night -> the single total tracks; no fees appear (line 344)
    const plus = w.findAll(".stepper__btn").at(1);
    await plus.trigger("click");
    expect(w.find(".stepper__value").text()).toBe("2");
    expect(w.find(".total__figure").text()).toBe("$48.00");
    expect(w.find(".cta").text()).toContain("Book spot");
    expect(w.find(".cta").text()).toContain("$48.00");
  });

  it("confirm resolves to a Booked confirmation carrying the same figure", async () => {
    // no session/offline: the POST is rejected; the checkout still resolves
    const fetchStub = vi.fn().mockRejectedValue(new Error("no session"));
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = await mountAt({ name: "Yardline Secured Parking", nightly: "2400" });
      await w.find(".cta").trigger("click");
      await flushPromises();
      expect(w.text()).toContain("Booked");
      expect(w.find(".done__figure").text()).toBe("$24.00");
      expect(w.text()).toContain("1 Nights"); // nights + property summary
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("FacilityCard — fuel-network station (M7, §11.2 / §12.2)", () => {
  it("shows the NET price + savings and leads with Fuel here, emits fuel", async () => {
    const pin = {
      facility_id: "f-5",
      name: "TA Travel Center",
      facility_type: "fuel_station",
      status: null,
      badges: [
        { kind: "fuel_net", gross: 419, net: 394, savings: 25, is_network: true, station_ref: "station-f5" },
      ],
      freshness: { reported_at: new Date().toISOString(), sample_size: 4 },
    };
    const router = testRouter();
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [router] } });
    expect(w.find(".fac__fuel-figure").text()).toBe("$3.94"); // net, Mono
    expect(w.find(".fac__save").text()).toContain("25"); // savings called out
    expect(w.find(".cta").text()).toContain("Fuel here");
    await w.find(".cta").trigger("click");
    expect(w.emitted().fuel).toBeTruthy();
    expect(w.emitted().fuel[0][0].facility_id).toBe("f-5");
    expect(w.text()).toContain("Navigate"); // stays as secondary
  });
});

describe("FuelSurface — pump-code flow (M7, NAV-3 / §8.7 one net price)", () => {
  async function mountAt(query) {
    const router = testRouter();
    router.push({ path: "/fuel/station-f5", query });
    await router.isReady();
    const w = mount(FuelSurface, { global: { plugins: [router] } });
    await flushPromises();
    return w;
  }

  it("shows net price, savings that track gallons, and issues a code", async () => {
    const fetchStub = vi.fn().mockRejectedValue(new Error("no session"));
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = await mountAt({ name: "TA Travel Center", gross: "419", net: "394", savings: "25" });
      expect(w.find(".price__figure").text()).toBe("$3.94"); // net, ledger-green Mono
      expect(w.find(".totals__save").text()).toBe("$12.50"); // 25c * 50 gal default
      expect(w.find(".totals__figure").text()).toBe("$197.00"); // 394c * 50 gal
      // +10 gallons -> savings + total track
      await w.findAll(".stepper__btn").at(1).trigger("click");
      expect(w.find(".stepper__value").text()).toBe("60");
      expect(w.find(".totals__save").text()).toBe("$15.00");
      // get a code (offline -> station-derived fallback)
      await w.find(".cta").trigger("click");
      await flushPromises();
      expect(w.find(".done__code").exists()).toBe(true);
      expect(w.text()).toContain("Show this at the pump");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("MoneySurface — fuel savings row (M7-FR4, design-prd §238)", () => {
  it("surfaces savings-to-date in ledger-green Mono (fixture)", async () => {
    const w = mount(MoneySurface);
    await flushPromises();
    expect(w.find(".savings").exists()).toBe(true);
    expect(w.find(".savings__amount").text()).toBe("$362.50"); // 36250c saved
    expect(w.find(".savings").text()).toContain("1450"); // gallons in Mono
    // the receivables list is unchanged — still exactly three rows
    expect(w.findAll(".row")).toHaveLength(3);
    w.unmount();
  });
});

describe("LoadCalcSurface — true-profit calculator (M8-FR1, §11.7 basis)", () => {
  async function mountCalc() {
    const router = testRouter();
    router.push("/load/calc");
    await router.isReady();
    const w = mount(LoadCalcSurface, { global: { plugins: [router] } });
    await flushPromises();
    return w;
  }

  it("computes an honest offline net (revenue − tolls) with basis shown", async () => {
    const fetchStub = vi.fn().mockRejectedValue(new Error("no session"));
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = await mountCalc();
      // defaults: revenue $2000, miles 500, tolls $30
      await w.find("form").trigger("submit");
      await flushPromises();
      expect(w.find(".result__figure").text()).toBe("$1,970.00"); // 2000 − 30 offline
      expect(w.find(".result__figure").classes()).toContain("pos"); // clears -> ledger-green
      expect(w.find(".result__rpm").text()).toContain("$3.94"); // 197000c / 500 mi
      expect(w.text()).toContain("tracked stops"); // basis line always present
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("flags a load that does not clear in flare", async () => {
    const fetchStub = vi.fn().mockRejectedValue(new Error("no session"));
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = await mountCalc();
      const inputs = w.findAll(".field__input");
      await inputs.at(0).setValue(20); // revenue $20
      await inputs.at(2).setValue(30); // tolls $30 -> net negative
      await w.find("form").trigger("submit");
      await flushPromises();
      expect(w.find(".result__figure").classes()).toContain("neg");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("FacilityProfileSurface — M8 intel (FR6 risk + FR2 fastest hour)", () => {
  it("shows the detention-risk % and fastest hour with basis (fixture)", async () => {
    const router = testRouter();
    router.push("/facility/f-1");
    await router.isReady();
    const w = mount(FacilityProfileSurface, { global: { plugins: [router] } });
    await flushPromises();
    const text = w.text();
    expect(text).toContain("Detention risk");
    expect(w.find(".risk__figure").text()).toBe("43%");
    expect(w.find(".risk__figure").classes()).toContain("hot"); // >=40% -> flare
    expect(text).toContain("Fastest hour");
    expect(w.find(".best-hour__figure").text()).toBe("06:00");
    w.unmount();
  });
});

describe("The Meter (design-prd §9)", () => {
  it("renders label, Mono figure, and status with the variant color", () => {
    const w = mount(TheMeter, {
      props: { label: "Detention", figure: "$150.00", variant: "accruing", status: "2:00:00 · $75/h" },
    });
    expect(w.find(".meter__label").text()).toBe("Detention");
    expect(w.find(".meter__figure").text()).toBe("$150.00");
    expect(w.find(".meter__figure").attributes("style")).toContain("--ledger-500");
  });
});

describe("LoadSurface / Meter card (design-prd §10.2)", () => {
  it("shows the live Meter (fixture stop is accruing)", () => {
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    expect(w.find(".meter__figure").exists()).toBe(true);
    expect(w.text()).toContain("Detention"); // accruing label
    w.unmount();
  });
});

describe("MoneySurface (M4 Money tab, design-prd §10.3)", () => {
  it("lists receivables with Mono amounts + status pills (fixture)", async () => {
    const w = mount(MoneySurface);
    await flushPromises();
    expect(w.findAll(".row")).toHaveLength(3);
    const text = w.text();
    expect(text).toContain("$150.00"); // detention 15000c, tabular
    expect(text).toContain("Detention"); // jargon stays English (§12.3)
    expect(text).toContain("11d"); // aging in Mono
  });
});

describe("DocsSurface (M5 Docs tab, design-prd §10.4)", () => {
  it("shows inspection button, expiring pills, and the document grid (fixture)", async () => {
    const w = mount(DocsSurface);
    await flushPromises();
    expect(w.find(".inspect").text()).toContain("Inspection mode");
    expect(w.findAll(".doc")).toHaveLength(4);
    expect(w.text()).toContain("CDL"); // acronym stays English (§12.3)
    expect(w.findAll(".pill").length).toBeGreaterThan(0); // expiring-soon strip
  });
});

describe("FacilityProfileSurface (M2, PRD §8.2)", () => {
  it("shows dwell figures with sample size and reviews (fixture fallback)", async () => {
    const router = testRouter();
    router.push("/facility/f-1");
    await router.isReady();
    const w = mount(FacilityProfileSurface, { global: { plugins: [router] } });
    await flushPromises();
    const text = w.text();
    expect(text).toContain("Dock time");
    expect(text).toContain("stops"); // sample size always shown (§11.7)
    expect(w.find(".dwell__figure").exists()).toBe(true);
    expect(text).toContain("Add review");
  });
});

describe("MapSurface (design-prd §10.1 / §11.4)", () => {
  beforeEach(() => useDriverState().setState(DriverState.IDLE));

  it("shows the report chip in IDLE and Corridor mode in DRIVING", async () => {
    const router = testRouter();
    const w = mount(MapSurface, { global: { plugins: [router] } });
    expect(w.find(".report-chip").exists()).toBe(true);
    expect(w.find(".corridor").exists()).toBe(false);

    useDriverState().setState(DriverState.DRIVING);
    await w.vm.$nextTick();
    expect(w.find(".corridor").exists()).toBe(true);
    expect(w.find(".report-chip").exists()).toBe(false);
  });
});
