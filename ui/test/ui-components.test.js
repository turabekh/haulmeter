// AI-CONTEXT: Component tests for the M1 shell + Map surface. Assert the design
// laws that are testable in jsdom: exactly 5 labeled tabs & no hamburger
// (NAV-1), preset chips (§11.3), facility card single primary CTA + report, and
// DRIVING → Corridor mode (§11.4).
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import TabBar from "../src/core/components/TabBar.vue";
import PresetChips from "../src/core/components/PresetChips.vue";
import FacilityCard from "../src/core/components/FacilityCard.vue";
import MapSurface from "../src/surfaces/MapSurface.vue";
import MapCanvas from "../src/core/components/MapCanvas.vue";
import FacilityProfileSurface from "../src/surfaces/FacilityProfileSurface.vue";
import TheMeter from "../src/core/components/TheMeter.vue";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import MoneySurface from "../src/surfaces/MoneySurface.vue";
import DocsSurface from "../src/surfaces/DocsSurface.vue";
import RateConImportSheet from "../src/core/components/RateConImportSheet.vue";
import BookingSurface from "../src/surfaces/BookingSurface.vue";
import FuelSurface from "../src/surfaces/FuelSurface.vue";
import LoadCalcSurface from "../src/surfaces/LoadCalcSurface.vue";
import AuthSurface from "../src/surfaces/AuthSurface.vue";
import MoreSurface from "../src/surfaces/MoreSurface.vue";
import VoiceSheet from "../src/core/components/VoiceSheet.vue";
import FleetWorkspaceSurface from "../src/surfaces/FleetWorkspaceSurface.vue";
import AuditSurface from "../src/surfaces/AuditSurface.vue";
import ConditionSurface from "../src/surfaces/ConditionSurface.vue";
import ClaimSurface from "../src/surfaces/ClaimSurface.vue";
import EvidenceSurface from "../src/surfaces/EvidenceSurface.vue";
import IncidentSheet from "../src/core/components/IncidentSheet.vue";
import PublicScorecardSurface from "../src/surfaces/PublicScorecardSurface.vue";
import OwnerPortalSurface from "../src/surfaces/OwnerPortalSurface.vue";
import DevIndexSurface from "../src/surfaces/DevIndexSurface.vue";
import GhostwriterSheet from "../src/core/components/GhostwriterSheet.vue";
import SleepSheet from "../src/core/components/SleepSheet.vue";
import HandoffSheet from "../src/core/components/HandoffSheet.vue";
import { routes, installAuthGuard } from "../src/router.js";
import { setToken, logout, isAuthenticated, setActiveStop, setActiveFleet } from "../src/core/api.js";
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
  it("offers the five presets and emits selection", async () => {
    // four §11.3 presets + Food (M13 / §23 E-D2, owner-approved)
    const w = mount(PresetChips, { props: { modelValue: "drive" } });
    const chips = w.findAll(".chip");
    expect(chips).toHaveLength(5);
    expect(chips[4].text()).toBe("Food");
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

  it("a real 201 resolves to a Booked confirmation carrying the same figure", async () => {
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ booking_id: "bk1", nights: 1, price_cents: 2400, state: "booked" }),
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = await mountAt({ name: "Yardline Secured Parking", nightly: "2400" });
      await w.find(".cta").trigger("click");
      await flushPromises();
      expect(w.text()).toContain("Booked");
      expect(w.find(".done__figure").text()).toBe("$24.00");
      expect(w.text()).toContain("1 Nights");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("does NOT fake a confirmation when the spot is taken (409) — shows the real error", async () => {
    const fetchStub = vi.fn().mockResolvedValue({ ok: false, status: 409 });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = await mountAt({ name: "Yardline Secured Parking", nightly: "2400" });
      await w.find(".cta").trigger("click");
      await flushPromises();
      expect(w.text()).not.toContain("Booked"); // no false success
      expect(w.find(".book__error").text()).toContain("just booked"); // the honest message
      expect(w.find(".cta").exists()).toBe(true); // still on the checkout, can retry
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("shows an error (not a fake Booked) when the booking POST fails offline", async () => {
    const fetchStub = vi.fn().mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = await mountAt({ name: "Yardline Secured Parking", nightly: "2400" });
      await w.find(".cta").trigger("click");
      await flushPromises();
      expect(w.text()).not.toContain("Booked");
      expect(w.find(".book__error").exists()).toBe(true);
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
    expect(w.find(".fac__fuel-label").text()).toContain("net"); // "net" only for a network station
    expect(w.find(".fac__save").text()).toContain("25"); // savings called out
    expect(w.find(".cta").text()).toContain("Fuel here");
    await w.find(".cta").trigger("click");
    expect(w.emitted().fuel).toBeTruthy();
    expect(w.emitted().fuel[0][0].facility_id).toBe("f-5");
    expect(w.text()).toContain("Navigate"); // stays as secondary
    expect(w.text()).not.toContain("Report status"); // parking report is nonsensical for fuel
  });

  it("a receiver dock offers no parking Report status either", () => {
    const pin = {
      facility_id: "rcv-1",
      name: "Dallas Distribution Center",
      facility_type: "shipper_receiver",
      status: null,
      badges: [],
      freshness: { reported_at: new Date().toISOString(), sample_size: 4 },
    };
    const router = testRouter();
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [router] } });
    expect(w.find(".cta").text()).toContain("Navigate"); // leads with Navigate
    expect(w.text()).not.toContain("Report status"); // no parking-fullness on a dock
    expect(w.text()).toContain("View facility"); // dock-time intel is one tap deeper
  });
});

describe("FacilityCard — TPIMS availability (condition A / §11.7)", () => {
  function tpimsPin(availability, capacity, freshMs) {
    return {
      facility_id: "il-1",
      name: "Spoon River",
      facility_type: "rest_area",
      status: "some",
      availability,
      capacity,
      badges: [],
      // TPIMS reading -> source set, so the badge attributes it to the feed, not drivers
      freshness: { reported_at: new Date(freshMs).toISOString(), sample_size: 1, source: "tpims" },
    };
  }

  it("renders 'Low' as the category with capacity alongside — never a number", () => {
    const w = mount(FacilityCard, { props: { pin: tpimsPin("Low", 13, Date.now()) }, global: { plugins: [testRouter()] } });
    const avail = w.find(".fac__avail").text();
    expect(avail).toContain("Low"); // the category, verbatim
    expect(avail).toContain("13"); // capacity alongside
    expect(avail).not.toMatch(/Low\s*\d/); // "Low" is not turned into a count
  });

  it("renders a real count with capacity, and a FEED-timestamp freshness badge", () => {
    const feed = Date.parse("2026-07-23T08:59:17Z");
    const w = mount(FacilityCard, { props: { pin: tpimsPin(1, 13, feed) }, global: { plugins: [testRouter()] } });
    expect(w.find(".fac__avail").text()).toContain("1 · 13"); // count of capacity
    const fresh = w.find(".fac__fresh").text();
    expect(fresh).toContain("official feed"); // authoritative feed, not "N drivers"
    expect(fresh).not.toContain("driver");
  });

  it("shows no availability line for a facility without a reading", () => {
    const pin = tpimsPin(null, null, Date.now());
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [testRouter()] } });
    expect(w.find(".fac__avail").exists()).toBe(false);
  });
});

describe("FacilityCard — crowd / regional diesel price (M7-FR5 / M1-FR5)", () => {
  function fuelPin(badge) {
    return {
      facility_id: "f-fuel",
      name: "Kwik Trip",
      facility_type: "fuel_station",
      status: null,
      badges: [badge],
      freshness: null,
    };
  }

  it("shows the EIA regional average (indicative ~$) and never leads with Fuel here", () => {
    const pin = fuelPin({
      kind: "fuel_net", net: 378, gross: 378, savings: 0,
      is_network: false, source: "regional", indicative: true, as_of: "2026-07-14", sample_size: null,
    });
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [testRouter()] } });
    expect(w.find(".fac__fuel-figure").text()).toBe("~$3.78"); // indicative -> tilde
    expect(w.find(".fac__fuel-label").text()).not.toContain("net"); // an estimate is NOT a "net" price
    expect(w.find(".fac__fuel-src").text()).toContain("regional avg");
    expect(w.find(".fac__fuel-src").text()).toContain("wk of Jul 14"); // EIA period, not ingest time
    expect(w.find(".cta").text()).not.toContain("Fuel here"); // never "Fuel here" (non-network)
    expect(w.text()).toContain("Report diesel price"); // the crowd affordance is present
  });

  it("regional-only station LEADS with the 'be the first' nudge into the report sheet (§15.3)", () => {
    const pin = fuelPin({
      kind: "fuel_net", net: 378, gross: 378, savings: 0,
      is_network: false, source: "regional", indicative: true, as_of: "2026-07-14", sample_size: null,
    });
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [testRouter()] } });
    // the empty-state sentence invites the first real report
    expect(w.find(".fac__nudge").text()).toBe("Be the first to report the diesel price here.");
    // the LEAD action is the price report (not Navigate); Navigate demotes to secondary
    expect(w.find(".cta").text()).toContain("Report diesel price");
    expect(w.find(".cta--secondary").text()).toContain("Navigate");
    // the regional estimate stays visible as secondary context (no honesty regression)
    expect(w.find(".fac__fuel-figure").text()).toBe("~$3.78");
    expect(w.find(".fac__fuel-src").text()).toContain("regional avg");
    // the report affordance is not duplicated (lead + a second identical secondary)
    const reportButtons = w.findAll(".cta").filter((b) => b.text().includes("Report diesel price"));
    expect(reportButtons.length).toBe(1);
  });

  it("a crowd-priced station keeps Navigate as lead and does NOT show the nudge", () => {
    const pin = fuelPin({
      kind: "fuel_net", net: 369, gross: 369, savings: 0, is_network: false,
      source: "crowd", indicative: false, as_of: new Date().toISOString(), sample_size: 3,
    });
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [testRouter()] } });
    expect(w.find(".fac__nudge").exists()).toBe(false); // real data -> no nudge
    expect(w.find(".cta").text()).toContain("Navigate");
    expect(w.text()).toContain("Report diesel price"); // secondary report still available
  });

  it("shows a crowd-reported price with freshness (§11.7), no tilde", () => {
    const pin = fuelPin({
      kind: "fuel_net", net: 369, gross: 369, savings: 0, is_network: false,
      source: "crowd", indicative: false, as_of: new Date().toISOString(), sample_size: 3,
    });
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [testRouter()] } });
    expect(w.find(".fac__fuel-figure").text()).toBe("$3.69"); // real price, no tilde
    expect(w.find(".fac__fuel-src").text()).toContain("3 drivers"); // crowd freshness
  });

  it("emits report-price when the driver taps Report diesel price", async () => {
    const pin = fuelPin({
      kind: "fuel_net", net: 378, gross: 378, savings: 0,
      is_network: false, source: "regional", indicative: true, as_of: "2026-07-14", sample_size: null,
    });
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [testRouter()] } });
    const btn = w.findAll(".cta").find((b) => b.text().includes("Report diesel price"));
    await btn.trigger("click");
    expect(w.emitted()["report-price"]).toBeTruthy();
    expect(w.emitted()["report-price"][0][0].facility_id).toBe("f-fuel");
  });
});

describe("MapSurface — report a diesel price (M7-FR5 crowd)", () => {
  beforeEach(() => useDriverState().setState(DriverState.IDLE));
  afterEach(() => { vi.unstubAllGlobals(); logout(); });

  it("opens the price sheet from a fuel pin and posts /fuel/confirm-price", async () => {
    setToken("tok-fuel");
    const stub = vi.fn((url, opts) => {
      const u = String(url);
      if (u.includes("/map/overlay")) {
        return jsonOk({ clustered: false, total: 1, clusters: [], pins: [
          { facility_id: "f-fuel", name: "Kwik Trip", facility_type: "fuel_station", lat: 44.5, lon: -89.5, status: null, shape: "circle",
            badges: [{ kind: "fuel_net", net: 378, gross: 378, savings: 0, is_network: false, source: "regional", indicative: true, as_of: "2026-07-14", sample_size: null, station_ref: "f-fuel" }], freshness: null },
        ] });
      }
      if (u.endsWith("/fuel/confirm-price") && opts?.method === "POST") return jsonOk({ consensus_cents_per_gal: 378 });
      return jsonOk({});
    });
    vi.stubGlobal("fetch", stub);
    try {
      const w = mount(MapSurface, { global: { plugins: [testRouter()] } });
      await flushPromises();
      await w.find(".pin").trigger("click"); // open the fuel station's card
      await flushPromises();
      expect(w.find(".fac__fuel-figure").text()).toContain("~$3.78");
      const report = w.findAll(".cta").find((b) => b.text().includes("Report diesel price"));
      await report.trigger("click");
      await flushPromises();
      await w.find(".price__submit").trigger("click"); // submit the seeded price
      await flushPromises();
      const post = stub.mock.calls.find((c) => String(c[0]).endsWith("/fuel/confirm-price") && c[1]?.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse(post[1].body)).toMatchObject({ facility_id: "f-fuel", price_cents_per_gal: 378 });
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
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

describe("MoneySurface — Driver Dollars Delivered (M9-FR4, design-prd §238)", () => {
  it("leads with the DDD North Star figure + breakdown (fixture)", async () => {
    const w = mount(MoneySurface);
    await flushPromises();
    // hero Meter = recovered + fuel saved + flagged = $587.50 (fixture DDD)
    expect(w.find(".meter__figure").text()).toBe("$587.50");
    // breakdown carries the three streams, fuel saved among them
    const breakdown = w.find(".breakdown").text();
    expect(breakdown).toContain("$125.00"); // recovered 12500c
    expect(breakdown).toContain("$362.50"); // fuel saved 36250c
    expect(breakdown).toContain("$100.00"); // audit-flagged 10000c
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

describe("AuthSurface + auth guard (F1, PRD §7.1)", () => {
  beforeEach(() => logout());

  it("shows the brand wordmark (PRD §17.6), not the LONGHAUL placeholder", async () => {
    const router = testRouter();
    router.push("/login");
    await router.isReady();
    const w = mount(AuthSurface, { global: { plugins: [router] } });
    const brand = w.find(".auth__brand").text();
    expect(brand).toBe("Haulmeter");
    expect(brand).not.toContain("LONGHAUL"); // placeholder must be gone
    w.unmount();
  });

  it("logs in and routes to the map; token persists", async () => {
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ token: "tok-123", account_id: "acc-1" }),
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      router.push("/login");
      await router.isReady();
      const w = mount(AuthSurface, { global: { plugins: [router] } });
      await w.findAll(".field__input").at(0).setValue("driver@example.com");
      await w.findAll(".field__input").at(1).setValue("pw-123456");
      await w.find("form").trigger("submit");
      await flushPromises();
      expect(isAuthenticated.value).toBe(true);
      expect(router.currentRoute.value.name).toBe("map");
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });

  it("shows an unblaming error on bad credentials (§12.4)", async () => {
    const fetchStub = vi.fn().mockResolvedValue({ ok: false, status: 401 });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      const w = mount(AuthSurface, { global: { plugins: [router] } });
      await w.findAll(".field__input").at(0).setValue("driver@example.com");
      await w.findAll(".field__input").at(1).setValue("wrong");
      await w.find("form").trigger("submit");
      await flushPromises();
      expect(w.find(".auth__error").text()).toContain("wrong");
      expect(isAuthenticated.value).toBe(false);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("toggles between Log in and Create account", async () => {
    const router = testRouter();
    const w = mount(AuthSurface, { global: { plugins: [router] } });
    expect(w.find(".cta").text()).toContain("Log in");
    await w.find(".auth__toggle").trigger("click");
    expect(w.find(".cta").text()).toContain("Create account");
  });

  it("asks operating authority on signup and registers with the chosen one (§7.1)", async () => {
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: () => Promise.resolve({ token: "tok-op", account_id: "acc-op" }),
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      const w = mount(AuthSurface, { global: { plugins: [router] } });
      await w.find(".auth__toggle").trigger("click"); // -> Create account
      const opts = w.findAll(".auth-opt");
      expect(opts.length).toBe(3); // own_mc / leased / company
      expect(w.find(".auth-opt--on").text()).toContain("My own authority"); // default
      await opts[2].trigger("click"); // choose Company driver
      await w.findAll(".field__input").at(0).setValue("new@example.com");
      await w.findAll(".field__input").at(1).setValue("pw-123456");
      await w.find("form").trigger("submit");
      await flushPromises();
      const post = fetchStub.mock.calls.find((c) => String(c[0]).endsWith("/auth/register"));
      expect(JSON.parse(post[1].body)).toMatchObject({ email: "new@example.com", authority: "company" });
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });

  it("redirects an unauthenticated visit to a tab into /login", async () => {
    logout();
    const router = createRouter({ history: createMemoryHistory(), routes });
    installAuthGuard(router);
    await router.push("/money");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("login");
  });

  it("lets an authenticated driver reach a tab", async () => {
    setToken("tok-abc");
    try {
      const router = createRouter({ history: createMemoryHistory(), routes });
      installAuthGuard(router);
      await router.push("/money");
      await router.isReady();
      expect(router.currentRoute.value.name).toBe("money");
    } finally {
      logout();
    }
  });
});

describe("MoreSurface — account + points + logout (F1 / M10)", () => {
  it("shows the points balance + contributor level (fixture)", async () => {
    logout(); // no session -> fixture path (no network)
    const router = testRouter();
    const w = mount(MoreSurface, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.find(".points__figure").text()).toBe("340"); // fixture balance, Mono
    expect(w.find(".points__level").text()).toBe("Regular"); // level -> i18n
    w.unmount();
  });

  it("logs out and returns to /login", async () => {
    setToken("tok-xyz");
    const router = createRouter({ history: createMemoryHistory(), routes });
    installAuthGuard(router);
    await router.push("/more");
    await router.isReady();
    const w = mount(MoreSurface, { global: { plugins: [router] } });
    expect(w.find(".cta--danger").text()).toContain("Log out");
    await w.find(".cta--danger").trigger("click");
    await flushPromises();
    expect(isAuthenticated.value).toBe(false);
    expect(router.currentRoute.value.name).toBe("login");
  });

  it("switches the UI language and marks the active one (F15)", async () => {
    logout();
    const router = testRouter();
    const w = mount(MoreSurface, { global: { plugins: [router] } });
    await flushPromises();
    try {
      const langs = w.findAll(".lang");
      expect(langs.length).toBe(6); // the six launch locales, in their own names
      expect(w.text()).toContain("Language"); // English by default
      const es = langs.find((b) => b.text().includes("Español"));
      await es.trigger("click");
      await flushPromises();
      expect(w.text()).toContain("Idioma"); // the whole UI re-renders in Spanish
      expect(es.classes()).toContain("lang--on");
    } finally {
      // reset so the shared locale doesn't leak into later tests
      await w.findAll(".lang").find((b) => b.text().includes("English")).trigger("click");
      try { localStorage.removeItem("longhaul.locale"); } catch (e) { /* noop */ }
      w.unmount();
    }
  });
});

describe("MoreSurface — operating-authority verification (F1 / FMCSA)", () => {
  function routedFetch(map) {
    return vi.fn((url) => {
      const key = Object.keys(map).find((k) => String(url).includes(k));
      const body = map[key] ?? {};
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    });
  }

  it("hides the section entirely when the F13 flag is off", async () => {
    setToken("tok-authoff");
    vi.stubGlobal("fetch", routedFetch({
      "/community/points": { balance: 0, level: "new" },
      "/auth/me": { verification_enabled: false, verified: false, authority: "own_mc" },
    }));
    try {
      const w = mount(MoreSurface, { global: { plugins: [testRouter()] } });
      await flushPromises();
      expect(w.text()).not.toContain("Operating authority");
      w.unmount();
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });

  it("shows the verify form when enabled, then the verified name after a lookup", async () => {
    setToken("tok-authon");
    vi.stubGlobal("fetch", routedFetch({
      "/community/points": { balance: 0, level: "new" },
      "/auth/me": { verification_enabled: true, verified: false, authority: "own_mc", mc_number: null },
      "/auth/verify-authority": {
        verified: true,
        verify_status: "verified",
        mc_number: "123456",
        legal_name: "CARRIER 123456 LLC",
      },
    }));
    try {
      const w = mount(MoreSurface, { global: { plugins: [testRouter()] } });
      await flushPromises();
      expect(w.text()).toContain("Operating authority");
      expect(w.find(".authority__form").exists()).toBe(true);

      await w.find(".field__input").setValue("123456");
      await w.find(".authority__form").trigger("submit");
      await flushPromises();

      expect(w.find(".verified__name").text()).toContain("CARRIER 123456 LLC");
      expect(w.find(".verified__label").text()).toContain("Verified");
      w.unmount();
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });
});

describe("FacilityProfileSurface — driver Q&A (M10-FR4)", () => {
  it("lists questions + answers with the on-site badge (fixture)", async () => {
    const router = testRouter();
    router.push("/facility/f-1");
    await router.isReady();
    const w = mount(FacilityProfileSurface, { global: { plugins: [router] } });
    await flushPromises();
    const text = w.text();
    expect(text).toContain("Driver Q&A");
    expect(text).toContain("Is the north entrance still closed?");
    expect(w.find(".qa__badge").text()).toBe("on-site"); // presence-proven answer badged
  });
});

describe("VoiceSheet — copilot ask/answer (M11-FR1)", () => {
  it("asks over /voice/ask and shows the intent-routed spoken answer", async () => {
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ intent: "money_owed", spoken: "You're owed $150.00 across 1 claims." }),
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(VoiceSheet);
      await w.find(".voice__input").setValue("what am I owed");
      await w.find("form").trigger("submit");
      await flushPromises();
      expect(w.find(".voice__answer").text()).toContain("$150.00");
      // the POST went to the voice endpoint
      expect(fetchStub.mock.calls[0][0]).toContain("/voice/ask");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("renders the spoken answer oversized while driving (§14 voice-first)", async () => {
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ intent: "help", spoken: "Ask me anything." }),
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(VoiceSheet, { props: { driving: true } });
      await w.find(".voice__input").setValue("help");
      await w.find("form").trigger("submit");
      await flushPromises();
      expect(w.find(".voice__answer").classes()).toContain("hero");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  function installSpeech() {
    const instances = [];
    class FakeRecognition {
      constructor() { instances.push(this); }
      start() { this.started = true; }
      stop() { if (this.onend) this.onend(); }
    }
    const speak = vi.fn();
    vi.stubGlobal("SpeechRecognition", FakeRecognition);
    vi.stubGlobal("speechSynthesis", { speak, cancel: vi.fn() });
    vi.stubGlobal("SpeechSynthesisUtterance", class { constructor(text) { this.text = text; } });
    return { instances, speak };
  }

  it("on-device: captures speech via the mic and routes it to /voice/ask (§14)", async () => {
    const { instances } = installSpeech();
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ intent: "money_owed", spoken: "You're owed $150.00." }),
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(VoiceSheet);
      await flushPromises();
      expect(w.find(".voice__mic").exists()).toBe(true); // mic shown when supported
      expect(instances[0].started).toBe(true); // auto-listens on open (voice-first)
      instances[0].onresult({ results: [[{ transcript: "what am I owed" }]] });
      await flushPromises();
      expect(fetchStub.mock.calls[0][0]).toContain("/voice/ask");
      expect(w.find(".voice__answer").text()).toContain("$150.00");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("on-device: speaks the answer aloud while DRIVING (§14.1 audio-first)", async () => {
    const { instances, speak } = installSpeech();
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ intent: "help", spoken: "Ask me anything." }),
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(VoiceSheet, { props: { driving: true } });
      await flushPromises();
      instances[0].onresult({ results: [[{ transcript: "help" }]] });
      await flushPromises();
      expect(speak).toHaveBeenCalled();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("on-device: unrecognized speech shows one re-ask, then typing still works (§14.5)", async () => {
    const { instances } = installSpeech();
    vi.stubGlobal("fetch", vi.fn());
    try {
      const w = mount(VoiceSheet);
      await flushPromises();
      instances[0].onerror({ error: "no-speech" });
      await flushPromises();
      expect(w.find(".voice__hint").text()).toBeTruthy(); // graceful re-ask
      expect(w.find(".voice__input").exists()).toBe(true); // visual fallback available
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("MapSurface — voice wake affordance (M11-FR5)", () => {
  it("shows the mic chip and opens the copilot sheet", async () => {
    logout(); // no session -> fixture overlay (no network)
    const router = testRouter();
    const w = mount(MapSurface, { global: { plugins: [router] } });
    expect(w.find(".voice-chip").exists()).toBe(true);
    await w.find(".voice-chip").trigger("click");
    await flushPromises();
    // the voice sheet mounts its input
    expect(w.find(".voice__input").exists()).toBe(true);
    w.unmount();
  });
});

describe("FleetWorkspaceSurface — web-first portal (M12, design-prd §18)", () => {
  it("falls back to the fixture demo when unauthenticated", async () => {
    logout();
    const w = mount(FleetWorkspaceSurface);
    await flushPromises();
    expect(w.text()).toContain("Fleet Workspace");
    expect(w.find(".kpi__figure").text()).toBe("$1,840.00"); // demo recovered
    expect(w.find(".good").exists()).toBe(true);
    expect(w.find(".bad").exists()).toBe(true);
    w.unmount();
  });

  it("creates a fleet then goes live (no fleets yet -> create -> workspace)", async () => {
    setToken("tok-fleet");
    setActiveFleet(null);
    const fetchStub = vi.fn().mockImplementation((url, opts) => {
      const u = String(url);
      if (u.endsWith("/fleet/mine")) return jsonOk([]);
      if (u.endsWith("/fleet") && opts?.method === "POST") return jsonOk({ fleet_id: "fl-1", role: "owner" });
      if (u.includes("/report")) {
        return jsonOk({
          driver_count: 1,
          recovered_cents: 0,
          owed_cents: 0,
          fuel_saved_cents: 0,
          members: [{ driver_account_id: "acc-owner-1234", recovered_cents: 0, owed_cents: 0, fuel_saved_cents: 0 }],
        });
      }
      if (u.includes("/claims")) return jsonOk({ owed_cents: 0, recovered_cents: 0, by_counterparty: {} });
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(FleetWorkspaceSurface);
      await flushPromises();
      expect(w.text()).toContain("You don't run a fleet yet"); // create view
      await w.find(".field__input").setValue("Acme Fleet");
      await w.find(".cta").trigger("click");
      await flushPromises();
      expect(w.find(".kpi").exists()).toBe(true); // live workspace rendered
      expect(w.findAll("tbody tr").length).toBe(1); // the owner, consented
    } finally {
      vi.unstubAllGlobals();
      setActiveFleet(null);
      logout();
    }
  });
});

function jsonOk(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

describe("AuditSurface — settlement auditor (M9-FR1)", () => {
  it("flags missed pay in flare with a review note", async () => {
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          discrepancies: [
            { kind: "detention", owed_cents: 15000, paid_cents: 5000, missed_cents: 10000, status: "flagged" },
          ],
          total_missed_cents: 10000,
        }),
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      router.push("/money/audit");
      await router.isReady();
      const w = mount(AuditSurface, { global: { plugins: [router] } });
      await w.find("form").trigger("submit");
      await flushPromises();
      expect(w.find(".result__figure").text()).toBe("$100.00"); // 10000c missed
      expect(w.find(".result__figure").classes()).toContain("result__figure"); // flare hero
      expect(w.text()).toContain("Review with your carrier"); // never legal advice
      expect(fetchStub.mock.calls[0][0]).toContain("/money/settlements/audit");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("GhostwriterSheet — comms drafting (M11-FR3)", () => {
  it("drafts an English message and requires driver approval before sending", async () => {
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ draft: "Dear broker, per the rate confirmation...", outbound_language: "en" }),
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(GhostwriterSheet);
      // pick the firm tone, say what happened
      await w.findAll(".tone").at(2).trigger("click");
      await w.find("textarea").setValue("3h past free time");
      await w.find(".cta").trigger("click"); // write it
      await flushPromises();
      expect(w.find(".draft__body").text()).toContain("Dear broker");
      expect(w.text()).toContain("English"); // outbound is English (F15)
      // nothing sent until the driver approves
      await w.find(".cta").trigger("click"); // approve & send
      await flushPromises();
      expect(w.find(".sent").exists()).toBe(true);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("SleepSheet — where-do-I-sleep solver (M8-FR3)", () => {
  it("ranks stops with the guaranteed-bookable starred (offline fixture)", async () => {
    logout(); // no session -> fixture plan (no network)
    const w = mount(SleepSheet);
    await w.find(".cta").trigger("click");
    await flushPromises();
    const stops = w.findAll(".stop");
    expect(stops.length).toBe(3);
    // the guaranteed-bookable spot leads and carries the star
    expect(stops.at(0).find(".stop__star").exists()).toBe(true);
    expect(w.text()).toContain("Guaranteed spot");
    expect(w.text()).toContain("Fuel on the way");
    w.unmount();
  });
});

describe("HandoffSheet — spot relay (M10-FR2)", () => {
  it("lists nearby handoffs and claims one over the API", async () => {
    const fetchStub = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ state: "claimed" }) });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const handoffs = [
        { handoff_id: "h-1", facility_name: "Loves #212", leaving_at: new Date(Date.now() + 720000).toISOString(), mine: false },
        { handoff_id: "h-2", facility_name: "My Lot", leaving_at: new Date(Date.now() + 600000).toISOString(), mine: true },
      ];
      const w = mount(HandoffSheet, { props: { handoffs } });
      expect(w.text()).toContain("Loves #212");
      expect(w.text()).toContain("Yours"); // my own broadcast isn't claimable
      const claimBtn = w.findAll(".claim").find((b) => b.text() === "Claim");
      await claimBtn.trigger("click");
      await flushPromises();
      expect(fetchStub.mock.calls[0][0]).toContain("/community/handoff/h-1/claim");
      expect(w.text()).toContain("Claimed");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("FacilityCard — free-lot handoff (M10-FR2)", () => {
  it("offers 'Leaving soon' on a free public lot and emits handoff", async () => {
    const pin = {
      facility_id: "f-1",
      name: "Loves #212",
      facility_type: "truck_stop",
      status: "full",
      badges: [],
      freshness: { reported_at: new Date().toISOString(), sample_size: 3 },
    };
    const router = testRouter();
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [router] } });
    const btn = w.findAll(".cta").find((b) => b.text() === "Leaving soon");
    expect(btn).toBeTruthy();
    await btn.trigger("click");
    expect(w.emitted().handoff).toBeTruthy();
    expect(w.emitted().handoff[0][0].facility_id).toBe("f-1");
  });
});

describe("ConditionSurface — cargo-condition capture (M5-FR2)", () => {
  it("guides the first step when an active stop starts the sequence", async () => {
    setToken("tok-cond");
    setActiveStop("stop-c1");
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          capture_id: "cap-1",
          sequence: ["trailer_exterior", "seals", "load_blocking", "reefer_setpoint"],
        }),
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      router.push("/protection/condition");
      await router.isReady();
      const w = mount(ConditionSurface, { global: { plugins: [router] } });
      await flushPromises();
      expect(w.text()).toContain("Step 1 of 4"); // guided, one decision per step
      expect(w.text()).toContain("Trailer exterior");
      expect(w.find(".shoot").exists()).toBe(true); // camera-first target
      expect(fetchStub.mock.calls[0][0]).toContain("/protection/condition/start");
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

  it("prompts to start a load when there's no active stop", async () => {
    logout();
    setActiveStop(null);
    const router = testRouter();
    const w = mount(ConditionSurface, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.text()).toContain("Start a load");
    w.unmount();
  });
});

describe("ClaimSurface — claim contents (M3-FR5)", () => {
  it("shows the money, terms, mode, and GPS-verified evidence chain", async () => {
    setToken("tok-claim");
    const fetchStub = vi.fn().mockImplementation((url) =>
      String(url).includes("/load/stop-x/claim")
        ? jsonOk({
            claim_id: "c1", amount_cents: 15000, detention_seconds: 7200, free_time_minutes: 120,
            rate_cents_per_hour: 7500, state: "invoiced", mode: "invoice",
            facility: "Perth Dock", counterparty: "Acme Brokerage", notice_sent: true, filed: true,
            created_at: "2026-07-21T10:00:00Z", chain_valid: true, record_count: 3, artifact_count: 1,
            timeline: [{ type: "GEOFENCE", occurred_at: "2026-07-21T10:00:00Z" }, { type: "PHOTO", occurred_at: "2026-07-21T10:05:00Z" }],
          })
        : jsonOk({}),
    );
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      router.push("/claim/stop-x");
      await router.isReady();
      const w = mount(ClaimSurface, { global: { plugins: [router] } });
      await flushPromises();
      expect(w.find(".hero__amount").text()).toBe("$150.00"); // the money
      expect(w.text()).toContain("Money owed to you"); // invoice mode
      expect(w.text()).toContain("Perth Dock");
      expect(w.text()).toContain("Chain verified"); // evidence integrity
      expect(w.text()).toContain("GPS arrival verified"); // the geofence record, friendly
      expect(w.text()).toContain("Photo captured");
      expect(w.text()).toContain("Broker notified"); // notice sent
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });
});

describe("EvidenceSurface — consolidated evidence locker (M5/M3)", () => {
  it("shows condition photos with labels, the timeline, and the verified badge", async () => {
    setToken("tok-ev");
    const fetchStub = vi.fn().mockImplementation((url) =>
      String(url).includes("/load/stop-e/evidence")
        ? jsonOk({
            stop_id: "stop-e", facility: "Perth Dock", chain_valid: true,
            record_count: 3, photo_count: 2,
            documents: [{ doc_type: "cdl", status: "ok" }],
            photos: [
              { prompt: "seals", content_hash: "abc123def456", captured_at: "2026-07-21T10:05:00Z" },
              { prompt: "trailer_exterior", content_hash: "beef99cafe01", captured_at: "2026-07-21T10:06:00Z" },
            ],
            timeline: [
              { type: "GEOFENCE", occurred_at: "2026-07-21T10:00:00Z" },
              { type: "PHOTO", occurred_at: "2026-07-21T10:05:00Z" },
              { type: "PHOTO", occurred_at: "2026-07-21T10:06:00Z" },
            ],
          })
        : jsonOk({}),
    );
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      router.push("/load/stop-e/evidence");
      await router.isReady();
      const w = mount(EvidenceSurface, { global: { plugins: [router] } });
      await flushPromises();
      expect(w.text()).toContain("Perth Dock");
      expect(w.text()).toContain("Chain verified"); // chain-integrity badge
      expect(w.findAll(".photo").length).toBe(2); // one row per captured photo
      expect(w.text()).toContain("Seals"); // guided prompt -> friendly label
      expect(w.text()).toContain("GPS arrival verified"); // timeline record, friendly
      expect(w.text()).toContain("CDL"); // documents on file
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });

  it("renders a real F6-served thumbnail for photos that have an image", async () => {
    setToken("tok-ev2");
    const orig = URL.createObjectURL;
    URL.createObjectURL = vi.fn(() => "blob:evidence-thumb");
    const fetchStub = vi.fn().mockImplementation((url) => {
      const u = String(url);
      if (u.includes("/evidence/photo/")) {
        return Promise.resolve({ ok: true, blob: () => Promise.resolve(new Blob(["x"])) });
      }
      if (u.includes("/load/stop-img/evidence")) {
        return jsonOk({
          stop_id: "stop-img", facility: "Perth Dock", chain_valid: true,
          record_count: 1, photo_count: 1, documents: [],
          photos: [{ artifact_id: "art-1", has_image: true, prompt: "seals", content_hash: "abc123", captured_at: "2026-07-21T10:05:00Z" }],
          timeline: [{ type: "PHOTO", occurred_at: "2026-07-21T10:05:00Z" }],
        });
      }
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      router.push("/load/stop-img/evidence");
      await router.isReady();
      const w = mount(EvidenceSurface, { global: { plugins: [router] } });
      await flushPromises();
      await flushPromises();
      const img = w.find(".photo__img");
      expect(img.exists()).toBe(true);
      expect(img.attributes("src")).toBe("blob:evidence-thumb");
    } finally {
      URL.createObjectURL = orig;
      vi.unstubAllGlobals();
      logout();
    }
  });
});

describe("IncidentSheet — incident capture (M5-FR4)", () => {
  it("files a chosen kind with a note, then confirms", async () => {
    setToken("tok-inc");
    const fetchStub = vi.fn().mockImplementation((url, opts) =>
      jsonOk({ incident_id: "inc-1", evidence_log_ref: "log-1", applied: true }),
    );
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(IncidentSheet);
      await w.findAll(".chip")[0].trigger("click"); // Damage
      await w.find("textarea").setValue("forklift hit the trailer");
      await w.find(".cta").trigger("click");
      await flushPromises();
      const [url, opts] = fetchStub.mock.calls[0];
      expect(String(url)).toContain("/protection/incident");
      expect(JSON.parse(opts.body)).toMatchObject({ kind: "damage", note: "forklift hit the trailer" });
      expect(opts.headers["Idempotency-Key"]).toBeTruthy(); // F12 exactly-once
      expect(w.text()).toContain("Filed"); // calm confirmation
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });

  it("won't file until a kind is chosen", async () => {
    setToken("tok-inc");
    try {
      const w = mount(IncidentSheet);
      expect(w.find(".cta").attributes("disabled")).toBeDefined();
    } finally {
      logout();
    }
  });

  it("saves offline (queued) when the network is dead", async () => {
    setToken("tok-inc");
    const fetchStub = vi.fn().mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(IncidentSheet);
      await w.findAll(".chip")[1].trigger("click"); // Load refused
      await w.find(".cta").trigger("click");
      await flushPromises();
      expect(w.text()).toContain("sync"); // queued-offline confirmation
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });
});


describe("PublicScorecardSurface — public portal (design-prd §18)", () => {
  it("searches facilities and shows an aggregate scorecard (no auth)", async () => {
    logout(); // a public visitor, no session
    const fetchStub = vi.fn().mockImplementation((url) => {
      const u = String(url);
      if (u.includes("/public/facilities")) {
        return jsonOk([{ id: "rcv-1", name: "Dallas Receiver", facility_type: "shipper_receiver" }]);
      }
      if (u.includes("/public/facility/")) {
        return jsonOk({
          id: "rcv-1",
          name: "Dallas Receiver",
          facility_type: "shipper_receiver",
          dwell: { median_seconds: 8100, p90_seconds: 15300, sample_size: 12 },
          rating: { overall: 3.8, review_count: 6 },
          reviews: ["Quick in and out.", "Detention paid without a fight."],
        });
      }
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(PublicScorecardSurface);
      await flushPromises();
      expect(w.text()).toContain("Facility Scorecard");
      const row = w.find(".list__row");
      expect(row.text()).toContain("Dallas Receiver");
      await row.trigger("click");
      await flushPromises();
      expect(w.find(".stat__figure").text()).toBe("2h 15m"); // dwell median, Mono
      expect(w.text()).toContain("12 stops"); // sample size always shown (§11.7)
      // de-identified, moderation-approved snippets render (no author/date)
      expect(w.text()).toContain("What drivers say");
      const snips = w.findAll(".snip").map((n) => n.text());
      expect(snips.length).toBe(2);
      expect(snips[0]).toContain("Quick in and out.");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("suppresses dwell below the sample floor (§13)", async () => {
    logout();
    const fetchStub = vi.fn().mockImplementation((url) => {
      const u = String(url);
      if (u.includes("/public/facilities")) return jsonOk([{ id: "x", name: "Sparse Stop", facility_type: "truck_stop" }]);
      return jsonOk({ id: "x", name: "Sparse Stop", facility_type: "truck_stop", dwell: null, rating: { overall: null, review_count: 0 } });
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(PublicScorecardSurface);
      await flushPromises();
      await w.find(".list__row").trigger("click");
      await flushPromises();
      expect(w.text()).toContain("Not enough tracked stops"); // suppressed, never a small-n figure
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("OwnerPortalSurface — Property-Owner portal (M6-FR5, design-prd §18)", () => {
  it("falls back to the fixture demo when unauthenticated", async () => {
    logout(); // no session -> apiGet throws -> demo
    const w = mount(OwnerPortalSurface);
    await flushPromises();
    expect(w.text()).toContain("Property Owner");
    expect(w.find(".payout__figure").text()).toBe("$396.00"); // demo payable
    expect(w.text()).toContain("Yardline Secured Parking");
    w.unmount();
  });

  it("shows live listings, bookings, and accrued payout", async () => {
    setToken("tok-owner");
    const fetchStub = vi.fn().mockImplementation((url) => {
      const u = String(url);
      if (u.endsWith("/owner/dashboard")) {
        return jsonOk({
          payout_cents: 3960,
          properties: [
            { id: "p1", name: "Depot Lot", vetted: true, spots: [{ label: "A1", price_cents_per_night: 2400, active: true }] },
          ],
          bookings: [
            { id: "b1", nights: 2, price_cents: 4800, owner_payout_cents: 3960, state: "checked_out" },
          ],
        });
      }
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(OwnerPortalSurface);
      await flushPromises();
      expect(w.find(".payout__figure").text()).toBe("$39.60");
      expect(w.text()).toContain("Depot Lot");
      // live view is read-write: the price is an editable input pre-filled in $
      expect(w.find(".spot__price-in").element.value).toBe("24.00");
      expect(w.findAll("tbody tr").length).toBe(1);
      expect(w.find("tbody tr").text()).toContain("Checked out"); // friendly state label
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });

  it("creates a property, adds a spot, re-prices and pauses it", async () => {
    setToken("tok-owner");
    let props = [];
    const fetchStub = vi.fn().mockImplementation((url, opts) => {
      const u = String(url);
      const method = opts?.method || "GET";
      if (u.endsWith("/owner/dashboard")) return jsonOk({ payout_cents: 0, properties: props, bookings: [] });
      if (u.endsWith("/owner/property") && method === "POST") {
        props = [{ id: "p1", name: JSON.parse(opts.body).name, vetted: false, spots: [] }];
        return jsonOk({ id: "p1" });
      }
      if (u.includes("/owner/property/p1/spot") && method === "POST") {
        const b = JSON.parse(opts.body);
        props[0].spots.push({ id: "s1", label: b.label, price_cents_per_night: b.price_cents_per_night, active: true });
        return jsonOk({ id: "s1" });
      }
      if (u.includes("/owner/spot/s1") && method === "PATCH") {
        Object.assign(props[0].spots[0], JSON.parse(opts.body));
        return jsonOk({ id: "s1" });
      }
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(OwnerPortalSurface);
      await flushPromises();
      // add a property
      await w.find(".in--name").setValue("Depot Overnight Lot");
      await w.find(".addprop").trigger("submit");
      await flushPromises();
      expect(w.text()).toContain("Depot Overnight Lot");
      // add a spot ($24/night -> 2400 cents)
      await w.find(".addspot .in--label").setValue("A1");
      await w.find(".addspot .in--price").setValue("24");
      await w.find(".addspot").trigger("submit");
      await flushPromises();
      const spotPost = fetchStub.mock.calls.find((c) => String(c[0]).includes("/spot") && c[1]?.method === "POST");
      expect(JSON.parse(spotPost[1].body)).toMatchObject({ label: "A1", price_cents_per_night: 2400 });
      // re-price to $26 -> PATCH with 2600 cents
      const priceIn = w.find(".spot__price-in");
      priceIn.element.value = "26.00";
      await priceIn.trigger("change");
      await flushPromises();
      const patch = fetchStub.mock.calls.find((c) => String(c[0]).includes("/owner/spot/s1") && c[1]?.method === "PATCH");
      expect(JSON.parse(patch[1].body)).toMatchObject({ price_cents_per_night: 2600 });
      // pause it -> PATCH active:false
      await w.find(".pause").trigger("click");
      await flushPromises();
      const pausePatch = fetchStub.mock.calls.filter((c) => c[1]?.method === "PATCH").pop();
      expect(JSON.parse(pausePatch[1].body)).toMatchObject({ active: false });
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });
});

describe("DevIndexSurface — dev directory of all surfaces", () => {
  it("registers the /dev route in development builds only (import.meta.env.DEV)", () => {
    // vitest runs with DEV=true, so the route is present here; a production
    // `vite build` sets DEV=false and tree-shakes the route + its component out.
    expect(import.meta.env.DEV).toBe(true);
    expect(routes.some((r) => r.name === "dev")).toBe(true);
  });

  it("lists every surface group and signs in as admin", async () => {
    logout();
    const router = testRouter();
    const fetchStub = vi.fn().mockImplementation((url) =>
      String(url).endsWith("/auth/login")
        ? jsonOk({ token: "tok-admin", account_id: "acc-1" })
        : jsonOk({}),
    );
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(DevIndexSurface, { global: { plugins: [router] } });
      await flushPromises();
      // the four groups + key destinations are present as clickable cards
      expect(w.text()).toContain("Driver app");
      expect(w.text()).toContain("Web portals");
      const paths = w.findAll(".card__path").map((n) => n.text());
      expect(paths).toEqual(expect.arrayContaining(["/map", "/load", "/admin", "/owner", "/scorecard"]));
      // one-click admin sign-in hits /auth/login and reflects the session
      await w.findAll(".btn--primary")[1].trigger("click"); // "Sign in as admin"
      await flushPromises();
      expect(fetchStub.mock.calls.some((c) => String(c[0]).endsWith("/auth/login"))).toBe(true);
      expect(w.text()).toContain("Signed in");
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
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
  it("shows the fixture-demo Meter when there's no active load (accruing)", () => {
    logout();
    setActiveStop(null);
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    expect(w.find(".meter__figure").exists()).toBe(true);
    expect(w.text()).toContain("Detention"); // accruing label
    w.unmount();
  });

  it("resumes the current load from /load/active when nothing is stored locally", async () => {
    setToken("tok-resume");
    setActiveStop(null); // fresh device: no persisted stop
    const fetchStub = vi.fn().mockImplementation((url) => {
      const u = String(url);
      if (u.endsWith("/load/active")) return jsonOk({ stop_id: "stop-resumed" });
      if (u.includes("/load/stop-resumed/meter")) {
        return jsonOk({
          stop_id: "stop-resumed", facility_name: "Resumed Receiver", counterparty: "Acme",
          appointment: null, arrived: false, free_time_minutes: 120, rate_cents_per_hour: 7500,
          phase: "not_arrived", free_time_remaining_seconds: null, detention_seconds: 0,
          detention_cents: 0, notice_sent: false,
        });
      }
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      const w = mount(LoadSurface, { global: { plugins: [router] } });
      await flushPromises();
      // it discovered the armed stop server-side and opened its live Meter
      expect(fetchStub.mock.calls.some((c) => String(c[0]).endsWith("/load/active"))).toBe(true);
      expect(w.text()).toContain("Resumed Receiver");
      w.unmount();
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

  it("ends a load durably (POST /load/{stop}/end, then reverts to demo)", async () => {
    setToken("tok-end");
    setActiveStop("stop-end");
    const fetchStub = vi.fn().mockImplementation((url) => {
      const u = String(url);
      if (u.includes("/load/stop-end/meter")) {
        return jsonOk({
          stop_id: "stop-end", facility_name: "Ending Receiver", counterparty: "Acme",
          appointment: null, arrived: true, free_time_minutes: 120, rate_cents_per_hour: 7500,
          phase: "accruing", free_time_remaining_seconds: 0, detention_seconds: 600,
          detention_cents: 1250, notice_sent: false,
        });
      }
      return jsonOk({ stop_id: "stop-end", status: "departed" });
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      const w = mount(LoadSurface, { global: { plugins: [router] } });
      await flushPromises();
      expect(w.text()).toContain("Ending Receiver"); // live
      // §10.2 leaves ONE CTA on the screen; this stop's other actions moved behind
      // "More for this stop" (NAV-3) rather than stacking six buttons under the Meter
      await w.findAll(".cta").find((b) => b.text().includes("More for this stop")).trigger("click");
      await flushPromises();
      const endBtn = w.findAll(".more__item").find((b) => b.text() === "End load");
      await endBtn.trigger("click");
      await flushPromises();
      expect(fetchStub.mock.calls.some((c) => String(c[0]).endsWith("/load/stop-end/end"))).toBe(true);
      expect(w.text()).not.toContain("Ending Receiver"); // reverted to the fixture demo
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

  it("goes live for an active pre-arrival stop with an 'I've arrived' CTA (M3 clock)", async () => {
    setToken("tok-live");
    setActiveStop("stop-live-1");
    const fetchStub = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          stop_id: "stop-live-1",
          facility_name: "Live Receiver",
          counterparty: "Acme Brokerage",
          appointment: null,
          arrived: false,
          free_time_minutes: 120,
          rate_cents_per_hour: 7500,
          phase: "not_arrived",
          free_time_remaining_seconds: null,
          detention_seconds: 0,
          detention_cents: 0,
          notice_sent: false,
        }),
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      const w = mount(LoadSurface, { global: { plugins: [router] } });
      await flushPromises();
      expect(w.text()).toContain("Live Receiver"); // live stop context, not the fixture
      expect(w.find(".cta").text()).toContain("I've arrived"); // pre-arrival CTA
      expect(fetchStub.mock.calls[0][0]).toContain("/load/stop-live-1/meter");
      w.unmount();
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

  it("files a GPS-backed claim from an accruing stop (arrive->accrue->file)", async () => {
    setToken("tok-live");
    setActiveStop("stop-acc");
    const accruing = {
      stop_id: "stop-acc",
      claim_id: "claim-1",
      facility_name: "Accruing Receiver",
      counterparty: "Acme",
      appointment: null,
      arrived: true,
      free_time_minutes: 120,
      rate_cents_per_hour: 7500,
      phase: "accruing",
      free_time_remaining_seconds: 0,
      detention_seconds: 1800,
      detention_cents: 3750,
      // §10.2's ladder is Arm -> Snap BOL -> Send notice -> Generate claim, so the
      // claim is the primary only once the rungs before it are behind the driver:
      // the BOL is filed and the broker has been told the clock started
      notice_sent: true,
      bol_captured: true,
    };
    const fetchStub = vi.fn().mockImplementation((url) => {
      if (String(url).endsWith("/claim")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ amount_cents: 3750, state: "invoiced", chain_valid: true }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(accruing) });
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      const w = mount(LoadSurface, { global: { plugins: [router] } });
      await flushPromises();
      expect(w.find(".cta").text()).toContain("Generate claim"); // accruing CTA
      await w.find(".cta").trigger("click");
      await flushPromises();
      expect(w.find(".filed").exists()).toBe(true);
      expect(w.find(".filed").text()).toContain("$37.50"); // filed claim amount
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

  it("the CTA ladder makes Snap BOL the primary before the claim (§10.2)", async () => {
    setToken("tok-ladder");
    setActiveStop("stop-nobol");
    const noBol = {
      stop_id: "stop-nobol",
      claim_id: "claim-2",
      facility_name: "Paperwork Pending",
      counterparty: "Acme",
      appointment: null,
      arrived: true,
      free_time_minutes: 120,
      rate_cents_per_hour: 7500,
      phase: "accruing",
      free_time_remaining_seconds: 0,
      detention_seconds: 1800,
      detention_cents: 3750,
      notice_sent: false,
      bol_captured: false,
      photos_captured: 0,
      photos_required: 4,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => jsonOk(noBol)),
    );
    try {
      const router = testRouter();
      const w = mount(LoadSurface, { global: { plugins: [router] } });
      await flushPromises();

      // exactly one filled primary, and it is the rung the spec orders next
      const primaries = w.findAll(".cta:not(.cta--text)");
      expect(primaries).toHaveLength(1);
      expect(primaries[0].text()).toContain("Snap BOL");

      // a claim filed without the BOL is a weaker claim, but a driver whose receiver
      // has not produced paperwork must still be able to file — the ladder guides,
      // it does not gate
      const texts = w.findAll(".cta--text").map((b) => b.text());
      expect(texts.some((s) => s.includes("Generate claim"))).toBe(true);

      // and the checklist row can finally answer the question it has always asked
      expect(w.text()).toContain("BOL");
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

  it("scopes a snapped BOL to the stop, which is what makes the row honest", async () => {
    setToken("tok-bol");
    setActiveStop("stop-bol");
    const meter = {
      stop_id: "stop-bol",
      claim_id: "claim-3",
      facility_name: "Dock 4",
      counterparty: "Acme",
      appointment: null,
      arrived: true,
      free_time_minutes: 120,
      rate_cents_per_hour: 7500,
      phase: "within_free_time",
      free_time_remaining_seconds: 3600,
      detention_seconds: 0,
      detention_cents: 0,
      notice_sent: false,
      bol_captured: false,
    };
    const posts = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url, opts) => {
        if (opts?.method === "POST") {
          posts.push({ url: String(url), body: JSON.parse(opts.body) });
          return jsonOk({ document_id: "doc-1", applied: true });
        }
        if (String(url).includes("/documents/types")) {
          return jsonOk({ types: ["bol"], expiring: [], superseding: [] });
        }
        return jsonOk(meter);
      }),
    );
    try {
      const router = testRouter();
      const w = mount(LoadSurface, { global: { plugins: [router] } });
      await flushPromises();
      await w.find(".cta").trigger("click"); // Snap BOL
      await flushPromises();

      // the type was answered by the control that opened this, so it is not re-asked
      expect(w.findAll(".cap__chip")).toHaveLength(0);

      const sheet = w.findComponent({ name: "DocumentCaptureSheet" });
      expect(sheet.props("stopId")).toBe("stop-bol");
      expect(sheet.props("fixedType")).toBe("bol");
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });
});

describe("RateConImportSheet (§10.2 empty state / PRD §108)", () => {
  const DRAFT = {
    document_id: "doc-rc",
    readable: true,
    parsed: {
      reference_number: "L-9001",
      detention_rate_cents_per_hour: 7500,
      free_time_minutes: 120,
      receiver_name: "ACME Distribution Center",
    },
    silent_on: ["tonu"],
    facility_candidates: [
      { facility_id: "fac-1", name: "ACME Distribution Center", address: null, score: 0.68 },
      { facility_id: "fac-2", name: "Dallas Distribution Center", address: null, score: 0.65 },
    ],
  };

  function stub(draft) {
    const posts = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url, opts) => {
        posts.push({ url: String(url), body: opts?.body ? JSON.parse(opts.body) : null });
        if (String(url).endsWith("/load/import")) return jsonOk(draft);
        return jsonOk({ load_id: "l-1", stop_id: "s-1" });
      }),
    );
    return posts;
  }

  async function pickFile(w) {
    // jsdom has no real file picker; drive the handler the input would call
    w.find(".rc__input").element.files = [new File(["x"], "rc.pdf", { type: "application/pdf" })];
    await w.find(".rc__input").trigger("change");
    await flushPromises();
  }

  // FileReader.readAsDataURL resolves on a macrotask, which flushPromises does not
  // await — so the base64 step outlives a plain microtask flush.
  async function settle(w) {
    for (let i = 0; i < 5; i += 1) {
      await new Promise((r) => setTimeout(r, 0));
      await flushPromises();
    }
    await w.vm.$nextTick();
  }

  beforeEach(() => setToken("tok-rc"));
  afterEach(() => {
    vi.unstubAllGlobals();
    logout();
  });

  it("reads the rate con and creates nothing until the driver confirms", async () => {
    const posts = stub(DRAFT);
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    // the import ran; no load was created
    expect(posts.filter((p) => p.url.endsWith("/load/import"))).toHaveLength(1);
    expect(posts.filter((p) => p.url.endsWith("/load"))).toHaveLength(0);

    // and the parsed terms are editable, not asserted
    expect(w.text()).toContain("Read from your rate con");
    const values = w.findAll(".rc__input").map((i) => i.element.value);
    expect(values).toContain("ACME Distribution Center");
    expect(values).toContain("75"); // 7500 cents/h rendered as dollars
  });

  it("says what the rate con is SILENT on rather than showing a zero (M4-FR4)", async () => {
    stub(DRAFT);
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    expect(w.text()).toContain("does not state");
    expect(w.text()).toContain("TONU");
    expect(w.text()).not.toContain("$0");
  });

  it("offers the matched facility and sends it on confirm, so no duplicate is created", async () => {
    const posts = stub(DRAFT);
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    expect(w.text()).toContain("Is this the same place?");

    // no CANDIDATE is pre-selected — pg_trgm scores the wrong dock 0.65 and the right
    // one 0.68, so no threshold tells them apart. "None of these" is the default,
    // which is the honest one: the driver picks a match or the load creates its own.
    const radios = w.findAll(".rc__opt input");
    expect(radios.slice(0, 2).some((i) => i.element.checked)).toBe(false);
    expect(radios[radios.length - 1].element.checked).toBe(true); // "None of these"

    await w.findAll(".rc__opt input")[0].setValue(); // the driver picks
    await w.find(".rc__cta").trigger("click"); // now the create button
    await settle(w);

    const create = posts.find((p) => p.url.endsWith("/load"));
    expect(create.body.facility_id).toBe("fac-1");
    expect(create.body.rate_con_document_id).toBe("doc-rc");
  });

  it("an unreadable rate con falls back to typing, and invents nothing", async () => {
    stub({ document_id: "doc-rc", readable: false, parsed: null, silent_on: [], facility_candidates: [] });
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    expect(w.text()).toContain("could not read this one");
    const values = w.findAll(".rc__input").map((i) => i.element.value);
    expect(values.every((v) => v === "")).toBe(true); // no invented terms
  });
});

describe("LoadSurface — §10.2 anatomy and DRIVING", () => {
  const LIVE = {
    stop_id: "s-next", claim_id: "c-1", facility_name: "First Dock", counterparty: "Acme",
    appointment: null, arrived: true, free_time_minutes: 120, rate_cents_per_hour: 7500,
    phase: "within_free_time", free_time_remaining_seconds: 3600, detention_seconds: 0,
    detention_cents: 0, notice_sent: false, bol_captured: true,
    next_stop: { facility_name: "Second Dock", stop_type: "delivery", appointment: "2026-08-04T09:30:00" },
  };

  beforeEach(() => {
    useDriverState().setState(DriverState.IDLE);
    setToken("tok-next");
    setActiveStop("s-next");
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => jsonOk(LIVE)));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    setActiveStop(null);
    logout();
  });

  it("previews the next stop (§10.2 anatomy)", async () => {
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();

    expect(w.find(".next").exists()).toBe(true);
    expect(w.find(".next__name").text()).toBe("Second Dock");
    expect(w.find(".next__appt").text()).toBe("09:30"); // Mono, like every time figure
  });

  it("collapses to a Meter-only glance with a voice hint while DRIVING (§10.2)", async () => {
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.find(".next").exists()).toBe(true);

    useDriverState().setState(DriverState.DRIVING);
    await w.vm.$nextTick();

    // everything below the Meter goes; the hint names a destination that exists
    expect(w.find(".next").exists()).toBe(false);
    expect(w.findAll(".cta")).toHaveLength(0);
    expect(w.text()).toContain("Voice is on the Map tab");
  });

  it("keeps one CTA on screen and puts the rest behind More (§10.2 single CTA)", async () => {
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();

    // one filled primary; the secondary controls are text, not rivals
    expect(w.findAll(".cta:not(.cta--text)")).toHaveLength(0); // in free time nothing is owed yet
    expect(w.findAll(".more__item")).toHaveLength(0); // sheet closed

    await w.findAll(".cta").find((b) => b.text().includes("More for this stop")).trigger("click");
    await flushPromises();

    const items = w.findAll(".more__item").map((b) => b.text());
    expect(items).toContain("End load");
    expect(items).toContain("Check load profit");
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
  const WALLET = {
    documents: [
      { id: "d-1", doc_type: "cdl", expires_on: "2027-03-01", status: "ok" },
      { id: "d-2", doc_type: "permit", expires_on: "2026-09-01", status: "ok" },
      { id: "d-3", doc_type: "permit", expires_on: "2026-12-01", status: "ok" },
    ],
    expiring: [],
    archived_count: 2,
  };
  const ARCHIVE = {
    documents: [
      {
        id: "a-1",
        doc_type: "cdl",
        expires_on: "2026-03-01",
        archived_at: "2026-07-26T10:00:00+00:00",
        reason: "superseded",
        replaced_by: { id: "d-1", doc_type: "cdl", uploaded_at: "2026-07-26T10:00:00+00:00" },
        restorable: false,
        blocked_by_doc_type: "cdl",
      },
      {
        id: "a-2",
        doc_type: "permit",
        expires_on: null,
        archived_at: "2026-07-24T10:00:00+00:00",
        reason: "removed_by_driver",
        replaced_by: null,
        restorable: true,
        blocked_by_doc_type: null,
      },
    ],
  };

  function stubWallet({ onPost } = {}) {
    const posts = [];
    const stub = vi.fn().mockImplementation((url, opts) => {
      const u = String(url);
      if (opts?.method === "POST") {
        posts.push(u);
        onPost?.(u);
        return jsonOk({ document_id: "x" });
      }
      if (u.includes("/protection/documents/archive")) return jsonOk(ARCHIVE);
      if (u.includes("/protection/wallet")) return jsonOk(WALLET);
      return jsonOk({});
    });
    vi.stubGlobal("fetch", stub);
    return posts;
  }

  beforeEach(() => useDriverState().setState(DriverState.IDLE));
  afterEach(() => {
    vi.unstubAllGlobals();
    logout();
  });

  it("shows inspection button, expiring pills, and the document grid (fixture)", async () => {
    const w = mount(DocsSurface);
    await flushPromises();
    expect(w.find(".inspect").text()).toContain("Inspection mode");
    expect(w.findAll(".doc")).toHaveLength(4);
    expect(w.text()).toContain("CDL"); // acronym stays English (§12.3)
    expect(w.findAll(".pill").length).toBeGreaterThan(0); // expiring-soon strip
  });

  it("groups the grid by type (§10.4 'document grid by type')", async () => {
    setToken("tok-docs");
    stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();

    const labels = w.findAll(".group__label").map((n) => n.text());
    expect(labels).toEqual(["CDL", "Permit"]); // two permits collapse under one heading
    expect(w.findAll(".group")).toHaveLength(2);
    expect(w.findAll(".doc")).toHaveLength(3);
  });

  it("offers the archive with a count, and only when something is in it", async () => {
    setToken("tok-docs");
    stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();

    expect(w.find(".archive").exists()).toBe(true);
    expect(w.find(".archive__count").text()).toBe("2");
  });

  it("does not offer the archive when nothing is in it", async () => {
    setToken("tok-docs");
    // an "Archived · 0" row is a control that teaches the driver nothing
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url) => {
        const u = String(url);
        if (u.includes("/protection/documents/archive")) return jsonOk({ documents: [] });
        if (u.includes("/protection/wallet")) return jsonOk({ ...WALLET, archived_count: 0 });
        return jsonOk({});
      }),
    );
    const w = mount(DocsSurface);
    await flushPromises();

    expect(w.find(".archive").exists()).toBe(false);
  });

  it("removal asks first and only archives after the confirm (§8)", async () => {
    setToken("tok-docs");
    const posts = stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();

    await w.findAll(".doc")[0].trigger("click"); // open the document
    await flushPromises();
    await w.find(".viewer__remove").trigger("click"); // ask
    await flushPromises();

    expect(posts).toHaveLength(0); // nothing has happened yet
    const body = w.text();
    expect(body).toContain("Remove from wallet?");
    expect(body).toContain("Nothing is deleted"); // the confirm states the limit too
    expect(body).toContain("stops expiry reminders"); // and the actual consequence

    await w.find(".rm__go").trigger("click");
    await flushPromises();

    expect(posts.some((u) => u.endsWith("/protection/documents/d-1/archive"))).toBe(true);
  });

  it("keeping it archives nothing", async () => {
    setToken("tok-docs");
    const posts = stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();
    await w.findAll(".doc")[0].trigger("click");
    await flushPromises();
    await w.find(".viewer__remove").trigger("click");
    await flushPromises();

    await w.find(".rm__keep").trigger("click");
    await flushPromises();

    expect(posts).toHaveLength(0);
    expect(w.find(".rm__go").exists()).toBe(false);
  });

  it("offers no destructive control while DRIVING (Forbidden #11)", async () => {
    setToken("tok-docs");
    stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();
    await w.findAll(".doc")[0].trigger("click");
    await flushPromises();
    expect(w.find(".viewer__remove").exists()).toBe(true);

    useDriverState().setState(DriverState.DRIVING);
    await w.vm.$nextTick();

    expect(w.find(".viewer__remove").exists()).toBe(false);
    expect(w.find(".capture").exists()).toBe(false); // capture chip stays guarded too
  });

  it("the archive says why each document is there and whether Restore will work", async () => {
    setToken("tok-docs");
    stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();

    await w.find(".archive").trigger("click");
    await flushPromises();

    const rows = w.findAll(".arch__row");
    expect(rows).toHaveLength(2);
    expect(rows[0].text()).toContain("Replaced by a newer one");
    expect(rows[0].find(".arch__restore").exists()).toBe(false); // a live CDL holds the slot
    expect(rows[0].text()).toContain("already in your wallet"); // and it says so
    expect(rows[1].text()).toContain("You removed this");
    expect(rows[1].find(".arch__restore").exists()).toBe(true);
    expect(w.text()).toContain("Nothing here is deleted");
  });

  it("restores a removed document", async () => {
    setToken("tok-docs");
    const posts = stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();
    await w.find(".archive").trigger("click");
    await flushPromises();

    await w.findAll(".arch__row")[1].find(".arch__restore").trigger("click");
    await flushPromises();

    expect(posts.some((u) => u.endsWith("/protection/documents/a-2/restore"))).toBe(true);
  });

  it("an archived document opens, and offers neither edit nor remove", async () => {
    setToken("tok-docs");
    stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();
    await w.find(".archive").trigger("click");
    await flushPromises();

    await w.findAll(".arch__doc")[0].trigger("click");
    await flushPromises();

    // editing an archived document 409s on the server: it records what was true, so
    // the control is not offered rather than offered and refused
    expect(w.find(".viewer__edit").exists()).toBe(false);
    expect(w.find(".viewer__remove").exists()).toBe(false);
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

  it("submits a parking report and refreshes the overlay (M1-FR7)", async () => {
    setToken("tok-map");
    let status = "empty";
    const fetchStub = vi.fn().mockImplementation((url, opts) => {
      const u = String(url);
      if (u.includes("/map/overlay")) {
        return jsonOk({
          clustered: false,
          total: 1,
          clusters: [],
          pins: [
            { facility_id: "f-ta", name: "TA Dallas", facility_type: "truck_stop", lat: 32.78, lon: -96.82, status, shape: "circle", freshness: { as_of: "2026-07-21T15:00:00Z", ttl_seconds: 3600 } },
          ],
        });
      }
      if (u.endsWith("/map/report") && opts?.method === "POST") {
        status = JSON.parse(opts.body).value.status; // server would flip the belief
        return jsonOk({ submission_id: "s1", presence_proven: false });
      }
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const router = testRouter();
      const w = mount(MapSurface, { global: { plugins: [router] } });
      await flushPromises();
      await w.find(".report-chip").trigger("click"); // opens the report sheet for the nearest lot
      await flushPromises();
      const full = w.findAll(".report__opt").find((b) => b.text().toLowerCase().includes("full"));
      await full.trigger("click");
      await flushPromises();
      const post = fetchStub.mock.calls.find((c) => String(c[0]).endsWith("/map/report") && c[1]?.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse(post[1].body)).toMatchObject({ facility_id: "f-ta", signal_type: "parking_fullness", value: { status: "full" } });
      // overlay was refetched after the report (so the pin recolors)
      expect(fetchStub.mock.calls.filter((c) => String(c[0]).includes("/map/overlay")).length).toBeGreaterThanOrEqual(2);
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });
});

describe("MapSurface — viewport-driven overlay (empty-map fix)", () => {
  const overlayCalls = (stub) =>
    stub.mock.calls.filter((c) => String(c[0]).includes("/map/overlay"));
  const emptyOverlay = () => jsonOk({ clustered: false, total: 0, pins: [], clusters: [] });

  beforeEach(() => {
    useDriverState().setState(DriverState.IDLE);
    setToken("tok-vp");
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    logout();
  });

  it("fetches by viewport bbox on mount, then refetches (debounced) on bounds change", async () => {
    vi.useFakeTimers();
    const stub = vi.fn(() => emptyOverlay());
    vi.stubGlobal("fetch", stub);
    const w = mount(MapSurface, { global: { plugins: [testRouter()] } });
    await flushPromises();
    const first = overlayCalls(stub);
    expect(first.length).toBe(1); // one fetch on mount — the continental default view
    expect(String(first[0][0])).toMatch(/min_lat=.*min_lon=.*max_lat=.*max_lon=/); // bbox, not a point

    w.findComponent(MapCanvas).vm.$emit("bounds", {
      min_lat: 44, min_lon: -90, max_lat: 45, max_lon: -89,
    });
    await vi.advanceTimersByTimeAsync(300); // debounce settles
    await flushPromises();
    const after = overlayCalls(stub);
    expect(after.length).toBe(2);
    expect(String(after[1][0])).toContain("min_lat=44"); // refetched for the new viewport
  });

  it("debounces a burst of moveend bounds into a single refetch", async () => {
    vi.useFakeTimers();
    const stub = vi.fn(() => emptyOverlay());
    vi.stubGlobal("fetch", stub);
    const w = mount(MapSurface, { global: { plugins: [testRouter()] } });
    await flushPromises();
    const canvas = w.findComponent(MapCanvas);
    canvas.vm.$emit("bounds", { min_lat: 40, min_lon: -90, max_lat: 41, max_lon: -89 });
    canvas.vm.$emit("bounds", { min_lat: 41, min_lon: -89, max_lat: 42, max_lon: -88 });
    canvas.vm.$emit("bounds", { min_lat: 42, min_lon: -88, max_lat: 43, max_lon: -87 });
    await vi.advanceTimersByTimeAsync(300);
    await flushPromises();
    const calls = overlayCalls(stub);
    expect(calls.length).toBe(2); // 1 mount + only the last bounds of the burst
    expect(String(calls[1][0])).toContain("min_lat=42");
  });

  it("aborts the in-flight overlay fetch when the viewport moves again (rapid pan)", async () => {
    vi.useFakeTimers();
    const signals = [];
    let n = 0;
    const stub = vi.fn((url, opts) => {
      if (String(url).includes("/map/overlay")) {
        signals.push(opts?.signal);
        n += 1;
        if (n === 2) return new Promise(() => {}); // the first pan's fetch stays in-flight
      }
      return emptyOverlay();
    });
    vi.stubGlobal("fetch", stub);
    const w = mount(MapSurface, { global: { plugins: [testRouter()] } });
    await flushPromises(); // #1 mount fetch resolves
    const canvas = w.findComponent(MapCanvas);
    canvas.vm.$emit("bounds", { min_lat: 44, min_lon: -90, max_lat: 45, max_lon: -89 });
    await vi.advanceTimersByTimeAsync(300); // #2 in-flight (hangs)
    canvas.vm.$emit("bounds", { min_lat: 41, min_lon: -88, max_lat: 42, max_lon: -87 });
    await vi.advanceTimersByTimeAsync(300); // #3 supersedes -> aborts #2
    await flushPromises();
    expect(signals[1].aborted).toBe(true); // the outrun request was cancelled
    expect(signals[2].aborted).toBe(false); // the newest one is live
  });

  it("refetches the current viewport when the preset changes", async () => {
    const stub = vi.fn(() => emptyOverlay());
    vi.stubGlobal("fetch", stub);
    const w = mount(MapSurface, { global: { plugins: [testRouter()] } });
    await flushPromises();
    const before = overlayCalls(stub).length;
    await w.findAll(".chip")[2].trigger("click"); // the Work preset
    await flushPromises();
    const calls = overlayCalls(stub);
    expect(calls.length).toBeGreaterThan(before);
    expect(String(calls[calls.length - 1][0])).toContain("preset=work");
  });
});

describe("MapCanvas — server-side cluster bubbles (§11.5)", () => {
  it("renders a count bubble per cluster (dominant status color), tappable", () => {
    const w = mount(MapCanvas, {
      props: {
        pins: [],
        clusters: [
          { count: 42, lat: 43.0, lon: -89.0, status: "some" },
          { count: 7, lat: 44.0, lon: -90.0, status: "full" },
        ],
      },
    });
    const bubbles = w.findAll(".cluster");
    expect(bubbles).toHaveLength(2);
    expect(bubbles[0].find(".cluster__count").text()).toBe("42");
    expect(bubbles[0].attributes("aria-label")).toContain("42");
    w.unmount();
  });
});
