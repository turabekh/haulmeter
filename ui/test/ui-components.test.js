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
import AuthSurface from "../src/surfaces/AuthSurface.vue";
import MoreSurface from "../src/surfaces/MoreSurface.vue";
import VoiceSheet from "../src/core/components/VoiceSheet.vue";
import FleetWorkspaceSurface from "../src/surfaces/FleetWorkspaceSurface.vue";
import AuditSurface from "../src/surfaces/AuditSurface.vue";
import ConditionSurface from "../src/surfaces/ConditionSurface.vue";
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
      notice_sent: false,
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
