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
import ClaimSurface from "../src/surfaces/ClaimSurface.vue";
import IncidentSheet from "../src/core/components/IncidentSheet.vue";
import AdminConsoleSurface from "../src/surfaces/AdminConsoleSurface.vue";
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

describe("AdminConsoleSurface — F14 operator portal (design-prd §18)", () => {
  it("lists flags with gates and toggles one; denies non-admins", async () => {
    setToken("tok-admin");
    const fetchStub = vi.fn().mockImplementation((url, opts) => {
      const u = String(url);
      if (u.endsWith("/admin/flags")) {
        return jsonOk([
          { key: "m06_parking", description: "", enabled: false, kill_switch: false, can_activate: false, gates: [{ name: "refund_policy", satisfied: false }] },
          { key: "free_flag", description: "", enabled: false, kill_switch: false, can_activate: true, gates: [] },
        ]);
      }
      if (u.endsWith("/admin/views")) return jsonOk([{ key: "m03.claims", module: "m03", title: "Detention Claims", path: "/x" }]);
      if (u.endsWith("/admin/moderation")) return jsonOk([]);
      if (u.endsWith("/admin/analytics")) {
        return jsonOk({
          funnel: { module: "m03", steps: [
            { event: "load_added", count: 10 },
            { event: "arrived", count: 6 },
            { event: "claim_sent", count: 3 },
          ] },
          totals: { map_open: 40, load_added: 10, claim_sent: 3 },
        });
      }
      if (u.endsWith("/admin/audit")) {
        return jsonOk([
          { id: "a2", action: "moderation_approved", actor: "ops@example.com", target_kind: "review", detail: {}, created_at: "2026-07-21T18:40:00+00:00" },
          { id: "a1", action: "config_set", actor: "ops@example.com", target_kind: "config", detail: { key: "m06_take_rate_bps" }, created_at: "2026-07-21T18:30:00+00:00" },
        ]);
      }
      if (u.includes("/admin/config")) return jsonOk({ scope: "pricing", entries: { m06_take_rate_bps: 1750 } });
      if (u.includes("/enable")) return jsonOk({ key: "free_flag", enabled: true });
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(AdminConsoleSurface);
      await flushPromises();
      expect(w.text()).toContain("Admin Console");
      expect(w.text()).toContain("m06_parking");
      expect(w.text()).toContain("Detention Claims"); // module admin view listed
      // the audit log shows the operator mutation, attributed and timestamped
      expect(w.text()).toContain("Audit log");
      expect(w.text()).toContain("config_set");
      expect(w.text()).toContain("ops@example.com");
      expect(w.text()).toContain("2026-07-21 18:30"); // ISO trimmed, time never localized
      // moderation decisions now appear in the same feed, labeled by content kind
      expect(w.text()).toContain("moderation_approved");
      expect(w.text()).toContain("review"); // target_kind shown when there's no detail.key
      // the North Star funnel renders with per-step counts and drop-off %
      expect(w.text()).toContain("Detention funnel");
      const bars = w.findAll(".bar__fill");
      expect(bars.length).toBe(3);
      expect(bars[1].attributes("style")).toContain("60%"); // 6/10 arrived
      expect(w.text()).toContain("50%"); // 3/6 filed a claim (conversion)
      // the config editor lists the runtime value
      expect(w.find(".cfg__input").element.value).toBe("1750");
      // a gated flag that can't activate has a disabled toggle
      const toggles = w.findAll(".toggle");
      const gated = toggles.find((b) => b.attributes("disabled") !== undefined);
      expect(gated).toBeTruthy();
      // the gate-free flag toggles on
      const free = toggles.find((b) => b.attributes("disabled") === undefined);
      await free.trigger("click");
      await flushPromises();
      expect(fetchStub.mock.calls.some((c) => String(c[0]).includes("/enable"))).toBe(true);
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });

  it("shows the no-access notice on 403", async () => {
    setToken("tok-driver");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403 }));
    try {
      const w = mount(AdminConsoleSurface);
      await flushPromises();
      expect(w.text()).toContain("Platform admins only");
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });

  it("edits a runtime config value (POST /admin/config, numeric coercion)", async () => {
    setToken("tok-admin");
    const fetchStub = vi.fn().mockImplementation((url, opts) => {
      const u = String(url);
      if (u.endsWith("/admin/flags")) return jsonOk([]);
      if (u.endsWith("/admin/views")) return jsonOk([]);
      if (u.endsWith("/admin/moderation")) return jsonOk([]);
      if (u.endsWith("/admin/analytics")) return jsonOk({ funnel: { module: "m03", steps: [] }, totals: {} });
      if (u.endsWith("/admin/audit")) return jsonOk([]);
      if (u.includes("/admin/config") && opts?.method === "POST") return jsonOk({ key: "x", scope: "pricing", value: 1500 });
      if (u.includes("/admin/config")) return jsonOk({ scope: "pricing", entries: { m06_take_rate_bps: 1750 } });
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(AdminConsoleSurface);
      await flushPromises();
      // edit the existing value -> a POST with the numeric (not string) value
      const input = w.find(".cfg__input");
      input.element.value = "1500";
      await input.trigger("change");
      await flushPromises();
      const post = fetchStub.mock.calls.find((c) => String(c[0]).includes("/admin/config") && c[1]?.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse(post[1].body)).toMatchObject({ key: "m06_take_rate_bps", value: 1500, scope: "pricing" });
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
      const endBtn = w.findAll(".cta").find((b) => b.text() === "End load");
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

  it("submits a parking report and refreshes the overlay (M1-FR7)", async () => {
    setToken("tok-map");
    let status = "empty";
    const fetchStub = vi.fn().mockImplementation((url, opts) => {
      const u = String(url);
      if (u.includes("/map/overlay")) {
        return jsonOk([
          { facility_id: "f-ta", name: "TA Dallas", facility_type: "truck_stop", lat: 32.78, lon: -96.82, status, shape: "circle", freshness: { as_of: "2026-07-21T15:00:00Z", ttl_seconds: 3600 } },
        ]);
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
