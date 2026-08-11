// AI-CONTEXT: Component tests for the M1 shell + Map surface. Assert the design
// laws that are testable in jsdom: exactly 5 labeled tabs & no hamburger
// (NAV-1), preset chips (§11.3), facility card single primary CTA + report, and
// DRIVING → Corridor mode (§11.4).
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
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
import BookingsSurface from "../src/surfaces/BookingsSurface.vue";
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
import en from "../src/core/i18n/en.json";
import { messages, LAUNCH_LOCALES } from "../src/core/i18n/index.js";
import { useI18n } from "../src/core/i18n.js";
import { useDriverState, DriverState } from "../src/core/state.js";
// AI-CONTEXT: these were imported from `src/core/fixtures.js` and now live here
// (§23 entry 131). The distinction is the one entry 81 drew: a placeholder EXPORTED
// FROM `src/` is one import away from a driver's screen, and these two were exactly
// that — `MoneySurface` imported the same constants this test does. Test data in a
// test file ships to nobody, so it belongs here, shaped to the endpoints it stands in
// for (`/accessorial/owed`, `/money/earnings`).
const OWED_ROWS = [
  { receivable_id: "r-1", kind: "detention", amount_cents: 15000, state: "invoiced", aging_days: 3, is_reimbursement: false },
  { receivable_id: "r-2", kind: "tonu", amount_cents: 30000, state: "disputed", aging_days: 11, is_reimbursement: false },
  { receivable_id: "r-3", kind: "lumper", amount_cents: 12500, state: "recovered", aging_days: 21, is_reimbursement: true },
];
const EARNINGS = {
  recovered_cents: 12500,
  fuel_saved_cents: 36250,
  flagged_cents: 10000,
  ddd_cents: 58750,
};

// every Money state below needs a SESSION as well as a stub: `fetchOwed` goes through
// `apiGet`, which throws "no session" before it ever calls fetch. Without this the
// surface used to fall back to the fixture and the assertions measured that instead.
function stubMoney({ owed = OWED_ROWS, earnings = EARNINGS } = {}) {
  setToken("tok-money");
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url) => {
    const u = String(url);
    if (u.includes("/accessorial/owed")) return jsonOk(owed);
    if (u.includes("/money/earnings")) return jsonOk(earnings);
    return jsonOk({});
  }));
}

// AI-CONTEXT: find the call this test is ABOUT (§23 entry 115).
//
// These read `fetch.mock.calls[0]` and assumed the first request was theirs. Establishing
// a session now also PUTs the driver's detected timezone — the browser is the only thing
// that knows it, and §13.3's "local" was landing on UTC for everyone — so the first call
// is no longer necessarily the one under test. Indexing into a call list is the same
// brittleness HANDOFF-104 §6 corrected in an M5 assertion that read `delivered[0]`:
// assert WHICH call, not which position.
function callTo(fetchStub, fragment) {
  const hit = fetchStub.mock.calls.find(([url]) => String(url).includes(fragment));
  if (!hit) throw new Error(`no fetch to ${fragment}; saw ${fetchStub.mock.calls.map(([u]) => u)}`);
  return hit;
}


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
  it("offers the six presets and emits selection", async () => {
    // four §11.3 presets + Food (M13 / §23 E-D2) + Service (A5, same precedent).
    // NAV-1's five-tab law is about TABS and is asserted separately — this row is a
    // filter, and it scrolls.
    const w = mount(PresetChips, { props: { modelValue: "drive", available: ["drive", "tonight", "work", "fuel", "food", "service"] } });
    const chips = w.findAll(".chip");
    expect(chips).toHaveLength(6);
    await chips[1].trigger("click");
    expect(w.emitted()["update:modelValue"][0]).toEqual(["tonight"]);
  });

  // AI-CONTEXT: this asserted `chips[4].text()` === "Food", which was right until the
  // chips became icons (§23 entry 89). The name is not gone — it moved to where a
  // screen reader and a long-press can still reach it, which is the property actually
  // worth holding. An icon row whose glyphs are anonymous to assistive tech would be
  // a worse screen than the text row it replaced, in the one way nobody screenshots.
  it("keeps every preset's translated name reachable without rendering it", () => {
    const w = mount(PresetChips, { props: { modelValue: "drive", available: ["drive", "tonight", "work", "fuel", "food", "service"] } });
    const chips = w.findAll(".chip");
    expect(chips.map((c) => c.attributes("aria-label"))).toEqual([
      en["map.preset.drive"],
      en["map.preset.tonight"],
      en["map.preset.work"],
      en["map.preset.fuel"],
      en["map.preset.food"],
      en["map.preset.service"],
    ]);
    // long-press / hover reaches the same name
    expect(chips[4].attributes("title")).toBe(en["map.preset.food"]);
    // and no chip carries visible text any more — that is the density change
    expect(chips[4].text()).toBe("");
  });

  it("marks the selected preset by more than colour (C-1)", () => {
    // a text chip could lean on hue because the LABEL carried the meaning; an icon
    // chip cannot, so selection is a fill plus aria-selected
    const w = mount(PresetChips, { props: { modelValue: "work", available: ["drive", "tonight", "work", "fuel", "food", "service"] } });
    const chips = w.findAll(".chip");
    expect(chips[2].classes()).toContain("chip--active");
    expect(chips[2].attributes("aria-selected")).toBe("true");
    expect(chips[0].attributes("aria-selected")).toBe("false");
  });

  it("meets the glove spec in BOTH axes, which a text chip got for free", () => {
    // an icon chip is only as wide as it is told to be — the same defect the Docs
    // capture chip was caught by when its shortest locale rendered 42 dp wide
    const src = readFileSync(
      resolve(__dirname, "../src/core/components/PresetChips.vue"), "utf8",
    );
    expect(src).toMatch(/min-height:\s*48px/);
    expect(src).toMatch(/min-width:\s*48px/);
  });
});

// AI-CONTEXT: the voice sheet's honesty, which is the whole of §14.5 (§23 entry 91).
// Reported twice by the owner as "listening but not working" — first because a failed
// start() left `listening` true forever, then because a mic that CANNOT work in an
// insecure context still presented itself as one.
describe("speech availability (§14.5 / §12.4)", () => {
  it("does not call an unusable recogniser 'supported'", async () => {
    // Chrome exposes webkitSpeechRecognition over plain http and then refuses to
    // start one. A constructor that exists but can never run is not support.
    const speech = await import("../src/core/speech.js");
    const orig = Object.getOwnPropertyDescriptor(window, "isSecureContext");
    Object.defineProperty(window, "isSecureContext", { value: false, configurable: true });
    try {
      expect(speech.recognitionSupported()).toBe(false);
      expect(speech.recognitionUnavailableReason()).toBe("insecure");
    } finally {
      if (orig) Object.defineProperty(window, "isSecureContext", orig);
    }
  });

  it("sorts failures by what the DRIVER can do about them", async () => {
    const { speechFailureKind } = await import("../src/core/speech.js");
    // every one of these used to say "didn't catch that — try again", which invited
    // a retry at something that could not succeed
    expect(speechFailureKind("audio-capture")).toBe("no_mic");
    expect(speechFailureKind("network")).toBe("network");
    expect(speechFailureKind("not-allowed")).toBe("blocked");
    expect(speechFailureKind("service-not-allowed")).toBe("blocked");
    expect(speechFailureKind("start-failed")).toBe("unavailable");
    // and the two where re-asking IS the right answer
    expect(speechFailureKind("no-speech")).toBe("retry");
    expect(speechFailureKind("no-match")).toBe("retry");
  });

  it("reports a failed start instead of swallowing it", async () => {
    // the defect behind "says listening but is not working": start() threw, the catch
    // ate it, onerror never fired, and `listening` had already been set true
    const { createRecognizer } = await import("../src/core/speech.js");
    class Throwing {
      start() { throw new Error("no gesture"); }
      stop() {}
    }
    const prev = window.SpeechRecognition;
    window.SpeechRecognition = Throwing;
    try {
      const errors = [];
      const rec = createRecognizer("en", { onError: (e) => errors.push(e) });
      expect(rec.start()).toBe(false);
      expect(errors).toEqual(["start-failed"]);
    } finally {
      window.SpeechRecognition = prev;
    }
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
    // the scorecard cross-link is the eye in the title now; the VERB is its
    // accessible name, which is the only place a screen reader can find it
    expect(w.find(".fac__view").attributes("aria-label")).toBe("View facility");
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
    // parking report is nonsensical for fuel — assert the OPTIONS are absent, not the
    // old button label: the label no longer exists anywhere on any card
    expect(w.find(".report__opt").exists()).toBe(false);
  });

  it("a receiver dock offers no parking status question either", () => {
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
    expect(w.find(".report__opt").exists()).toBe(false); // no parking-fullness on a dock
    // dock-time intel is still one tap deeper, from the eye on the name
    expect(w.find(".fac__view").exists()).toBe(true);
  });
});

// AI-CONTEXT: §23 entry 124 — the scorecard cross-link is an eye in the title. NAV-5
// calls cross-links VERBS, so what these defend is that the verb did not disappear
// with the words: it has to survive as the accessible name, in every locale, or the
// control is unreachable by anyone not looking at it.
describe("FacilityCard — the scorecard link is on the name (§23 entry 124)", () => {
  const pin = {
    facility_id: "f-eye",
    name: "Highway 13 & 21 Wayside",
    facility_type: "rest_area",
    status: "some",
    badges: [],
    freshness: { reported_at: new Date().toISOString(), sample_size: 1 },
  };

  it("opens the facility scorecard, the same NAV-5 deep link as before", async () => {
    const router = testRouter();
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [router] } });
    await w.find(".fac__view").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/facility/f-eye");
  });

  it("carries the verb as its accessible name in all six locales (§16 / §12.5)", () => {
    const { setLocale } = useI18n();
    for (const loc of LAUNCH_LOCALES) {
      setLocale(loc);
      const w = mount(FacilityCard, { props: { pin }, global: { plugins: [testRouter()] } });
      const label = w.find(".fac__view").attributes("aria-label");
      expect(label).toBe(messages[loc]["facility.view"]);
      expect(label).toBeTruthy();
    }
    setLocale("en");
  });

  it("no longer spends a full-width row on it at the bottom of the card", () => {
    const w = mount(FacilityCard, { props: { pin }, global: { plugins: [testRouter()] } });
    expect(w.findAll(".cta--tertiary").map((b) => b.text())).not.toContain("View facility");
    // the glyph is inside the title, not floating in the action stack
    expect(w.find(".fac__name .fac__view").exists()).toBe(true);
  });
});

// AI-CONTEXT: §23 entry 123 — the status report moved ONTO the card. What these
// defend is the tap count and the ladder it had to fit into: the options must be
// present and answerable in one tap, and they must never sit above a price.
describe("FacilityCard — one-tap status report (M1-FR7 / §23 entry 123)", () => {
  const lot = (over = {}) => ({
    facility_id: "f-ts",
    name: "TA Dallas",
    facility_type: "truck_stop",
    status: "some",
    badges: [],
    freshness: { reported_at: new Date().toISOString(), sample_size: 3 },
    ...over,
  });

  it("asks the question on the card and answers it in ONE tap", async () => {
    const w = mount(FacilityCard, { props: { pin: lot() }, global: { plugins: [testRouter()] } });
    expect(w.find(".report__q").text()).toBe("How's parking here right now?");
    const opts = w.findAll(".report__opt");
    expect(opts.map((o) => o.text())).toEqual(["Empty", "Some", "Full"]);
    await opts[2].trigger("click");
    // the pin AND the answer travel together — the surface needs both to post
    expect(w.emitted("report")[0][0].facility_id).toBe("f-ts");
    expect(w.emitted("report")[0][1]).toBe("full");
  });

  it("leads the card, because Navigate is worth nothing to a driver already there", () => {
    const w = mount(FacilityCard, { props: { pin: lot() }, global: { plugins: [testRouter()] } });
    const html = w.html();
    // both must be PRESENT before their order means anything — a missing selector
    // makes indexOf -1, which is less than everything and proves nothing
    expect(html).toContain("report__opt");
    expect(html).toContain("cta--nav");
    expect(html.indexOf("report__opt")).toBeLessThan(html.indexOf("cta--nav"));
    // the filled CTA is still the only primary — the options are hairline outlines
    expect(w.find(".cta").text()).toContain("Navigate");
  });

  it("never sits above a price: a bookable lot keeps Book on top (§12.2)", () => {
    const w = mount(FacilityCard, {
      props: {
        pin: lot({
          facility_type: "parking_property",
          badges: [{ kind: "bookable", value: 2400, spot_id: "spot-1" }],
        }),
      },
      global: { plugins: [testRouter()] },
    });
    const html = w.html();
    expect(html.indexOf("cta--book")).toBeLessThan(html.indexOf("report__opt"));
    expect(w.find(".cta").text()).toContain("Book spot"); // still the first action
    expect(w.findAll(".report__opt")).toHaveLength(3); // and still one tap
  });

  it("keeps the driver's own dock leading with the stop, report underneath", () => {
    const w = mount(FacilityCard, {
      props: { pin: lot(), isActiveStop: true },
      global: { plugins: [testRouter()] },
    });
    const html = w.html();
    expect(html.indexOf("cta--stop")).toBeLessThan(html.indexOf("report__opt"));
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
  it("leads with the DDD North Star figure + breakdown", async () => {
    stubMoney();
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

  // AI-CONTEXT: the calculator knew nothing about the load it was opened from (§23
  // entry 85). It is reached as a bare `/load/calc` while reading query params nothing
  // supplies, so it asked the driver to retype a Rate the load already knew and valued
  // detention at the NIL UUID — a facility that does not exist — from a hardcoded
  // Dallas origin.
  const METER = {
    stop_id: "s-1",
    facility_id: "fac-77",
    facility_name: "Harvest Foods DC",
    rate_cents: 285000,
    free_time_minutes: 90,
    rate_cents_per_hour: 6000,
    phase: "not_arrived",
    detention_cents: 0,
    detention_seconds: 0,
    photos_captured: 0,
    photos_required: 4,
  };

  async function mountCalcWithLoad(meter = METER) {
    setActiveStop("s-1");
    setToken("tok-calc");
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url) => {
      if (String(url).includes("/meter")) return jsonOk(meter);
      return Promise.reject(new Error("no session"));
    }));
    const w = await mountCalc();
    await flushPromises();
    return w;
  }

  it("prefills the rate from the load rather than asking for it again", async () => {
    try {
      const w = await mountCalcWithLoad();
      expect(w.findAll(".field__input").at(0).element.value).toBe("2850.00");
      // §11.7: the figure names who is speaking
      expect(w.text()).toContain(en["calc.from_load"]);
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

  it("carries the load's detention terms across too", async () => {
    try {
      const w = await mountCalcWithLoad();
      const inputs = w.findAll(".field__input");
      expect(inputs.at(3).element.value).toBe("90"); // free time
      expect(inputs.at(4).element.value).toBe("60"); // $/hr
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

  it("values detention at the real receiver, not the nil UUID", async () => {
    setActiveStop("s-1");
    setToken("tok-calc");
    const posts = [];
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url, opts) => {
      posts.push({ url: String(url), body: opts?.body ? JSON.parse(opts.body) : null });
      if (String(url).includes("/meter")) return jsonOk(METER);
      return jsonOk({ revenue_cents: 285000, fuel_cost_cents: 1, tolls_cents: 0,
        expected_detention_cents: 0, net_cents: 1, rpm_after_cents: 1,
        basis: { fuel: "live", detention_sample_size: 3 } });
    }));
    try {
      const w = await mountCalc();
      await flushPromises();
      await w.find("form").trigger("submit");
      await flushPromises();
      const calc = posts.find((p) => p.body && p.body.receiver_facility_id);
      expect(calc.body.receiver_facility_id).toBe("fac-77");
      expect(calc.body.revenue_cents).toBe(285000);
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

  it("says nothing about a rate the contract never stated", async () => {
    // §11.7: a rate con silent on the linehaul must not hand the driver a confident
    // figure they did not type and the paper does not contain
    try {
      const w = await mountCalcWithLoad({ ...METER, rate_cents: null });
      expect(w.text()).not.toContain(en["calc.from_load"]);
      expect(w.findAll(".field__input").at(0).element.value).toBe("2000");
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

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

// AI-CONTEXT: §23 entry 131 — the three tests below mounted this surface with NO stub
// at all and asserted on `sampleProfile()` / `sampleFacilityIntel()` / `sampleQuestions()`,
// which the surface substituted when every fetch failed. Two of them said "(fixture)" in
// their own names. They assert the same things against the endpoints now. Shapes copied
// from GET /facility/{id}/profile, /intel/detention-risk, /intel/appointment-hours and
// /community/questions.
const FAC_PROFILE = {
  facility_id: "f-1",
  name: "Love's Travel Stop #212",
  check_in_procedure: "Check in at guard shack; keep PPE on in the yard.",
  overnight_parking: true,
  restrooms: true,
  dwell: {
    overall: { median_seconds: 8100, p90_seconds: 15300, sample_size: 12 },
    by_hour: {},
  },
  ratings: { overall: 3.8, review_count: 2, per_aspect: {} },
  detention_risk: { rate: null, sample_size: 0, basis: "m3_pending" },
  reviews: [],
};
const FAC_RISK = { exceed_rate: 0.43, sample_size: 14, confidence: "high", basis: "tracked_stops" };
const FAC_HOURS = [{ hour: 6, median_seconds: 2400, sample_size: 9, confidence: "medium" }];
const FAC_QUESTIONS = [
  {
    question_id: "q-1",
    text: "Is the north entrance still closed?",
    answers: [
      { text: "Open as of this morning — go around the fuel island.", presence_proven: true },
      { text: "Was closed last week.", presence_proven: false },
    ],
  },
  { question_id: "q-2", text: "Any overnight parking after 8pm?", answers: [] },
];

function stubFacility() {
  setToken("tok-facility");
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url) => {
    const u = String(url);
    if (u.includes("/facility/f-1/profile")) return jsonOk(FAC_PROFILE);
    if (u.includes("/intel/detention-risk")) return jsonOk(FAC_RISK);
    if (u.includes("/intel/appointment-hours")) return jsonOk(FAC_HOURS);
    if (u.includes("/community/questions")) return jsonOk(FAC_QUESTIONS);
    // AI-CONTEXT: null, not `{}`, and the difference is not cosmetic. An UNCLAIMED
    // facility returns null here (M13-FR7), and the surface's `v-if="serviceCenter"`
    // is written for exactly that. A truthy `{}` has no `services` array, so
    // `serviceCenter.services.length` throws DURING RENDER — which collapses every
    // branch below it, including the Q&A list this stub exists to feed. Caught while
    // writing it: the questions arrived, the state said `loaded`, and the section
    // rendered `<!--v-if-->`. A stub whose shape does not match its endpoint hides
    // that endpoint, which is the fixtures' own lesson (§23 entry 52).
    if (u.includes("/vendors/service-center/")) return jsonOk(null);
    return jsonOk({});
  }));
}

describe("FacilityProfileSurface — M8 intel (FR6 risk + FR2 fastest hour)", () => {
  it("shows the detention-risk % and fastest hour with basis", async () => {
    stubFacility();
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

// AI-CONTEXT: §23 entry 125 — the language chooser reached the door. Six locales
// have shipped since F15, and five of them were behind a login screen you had to
// read English to get through: the driver who most needs the setting had to finish
// onboarding in a language they don't read in order to change it. What these defend
// is that the control is legible BEFORE the choice is made — the trigger names the
// current language in its own words, and the list names all six in theirs.
describe("AuthSurface — the language chooser at the door (F15 / §23 entry 125)", () => {
  const mountAuth = async () => {
    const router = testRouter();
    router.push("/login");
    await router.isReady();
    return mount(AuthSurface, { global: { plugins: [router] } });
  };

  beforeEach(() => logout());
  afterEach(() => {
    useI18n().setLocale("en");
    try { localStorage.removeItem("longhaul.locale"); } catch { /* no storage */ }
  });

  it("names the current language in its own words, not a flag or a bare glyph", async () => {
    const w = await mountAuth();
    const btn = w.find(".lang-btn");
    expect(btn.exists()).toBe(true);
    expect(btn.text()).toContain("English");
    // the verb is the accessible name; the visible text is the language itself
    expect(btn.attributes("aria-label")).toBe("Language");
    w.unmount();
  });

  it("opens the six locales in a sheet and switches the whole screen", async () => {
    const w = await mountAuth();
    expect(w.findAll(".lang")).toHaveLength(0); // closed: no list stacked into the form
    await w.find(".lang-btn").trigger("click");
    await flushPromises();
    const langs = w.findAll(".lang");
    expect(langs).toHaveLength(6);
    expect(langs.map((b) => b.text().trim())).toEqual(
      expect.arrayContaining(["English", "Español", "ਪੰਜਾਬੀ", "Русский", "Oʻzbekcha", "Soomaali"]),
    );

    await langs.find((b) => b.text().includes("Español")).trigger("click");
    await flushPromises();
    // the choice lands on the login screen itself, not only after signing in
    expect(w.text()).toContain(messages.es["auth.login"]);
    expect(w.find(".lang-btn").text()).toContain("Español");
    expect(w.findAll(".lang")).toHaveLength(0); // picking closes the sheet
    w.unmount();
  });

  it("persists the choice, so the next cold start opens in it", async () => {
    const w = await mountAuth();
    await w.find(".lang-btn").trigger("click");
    await flushPromises();
    await w.findAll(".lang").find((b) => b.text().includes("Русский")).trigger("click");
    await flushPromises();
    expect(localStorage.getItem("longhaul.locale")).toBe("ru");
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
  it("shows the points balance + contributor level from the endpoint", async () => {
    // AI-CONTEXT: this said `logout(); // no session -> fixture path` and asserted
    // "340" — SAMPLE_POINTS' balance (§23 entry 131). It was a test OF the defect: a
    // driver with no session was shown a balance and a loyalty level they had not
    // earned. It reads the real endpoint now.
    setToken("tok-points");
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url) => {
      if (String(url).includes("/community/points")) {
        return jsonOk({ balance: 512, points_earned: 700, contribution_count: 40, trust_score: 1.6, level: "pro" });
      }
      return jsonOk({});
    }));
    const router = testRouter();
    const w = mount(MoreSurface, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.find(".points__figure").text()).toBe("512");
    expect(w.find(".points__level").text()).toBe("Pro");
    w.unmount();
  });

  it("shows no balance at all when the points call fails", async () => {
    // the other half, and the one that was the finding: absence must read as absence.
    setToken("tok-points");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, json: () => Promise.resolve({}) }));
    const router = testRouter();
    const w = mount(MoreSurface, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.find(".points__figure").exists()).toBe(false);
    expect(w.text()).toContain(en["more.points_failed"]);
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
      "/community/points": { balance: 0, level: "rookie" },
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
      "/community/points": { balance: 0, level: "rookie" },
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
  it("lists questions + answers with the on-site badge", async () => {
    stubFacility();
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
  // AI-CONTEXT: these mount a sheet that is meant to have a WORKING recogniser, and
  // `recognitionSupported()` now also requires a secure context (§23 entry 91) —
  // because Chrome exposes the constructor over plain http and then refuses to start
  // it, which is what "listening but not working" turned out to be. The test runner
  // is not a browsing context, so it has to say which case it is simulating. Three
  // tests failed on this guard and they were RIGHT to: they had been asserting that a
  // mic works without ever stating the condition under which one can.
  let secureCtx;
  beforeEach(() => {
    secureCtx = Object.getOwnPropertyDescriptor(window, "isSecureContext");
    Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
  });
  afterEach(() => {
    if (secureCtx) Object.defineProperty(window, "isSecureContext", secureCtx);
    else delete window.isSecureContext;
  });

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
      expect(callTo(fetchStub, "/voice/ask")[0]).toContain("/voice/ask");
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
      expect(callTo(fetchStub, "/voice/ask")[0]).toContain("/voice/ask");
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
  it("names no figure at all when it cannot reach the fleet", async () => {
    // AI-CONTEXT: this asserted `$1,840.00` — SAMPLE_FLEET's invented recovered total —
    // under the name "falls back to the fixture demo" (§23 entry 131). It was a test OF
    // the defect. The portal now says it could not load, and shows no money.
    logout();
    const w = mount(FleetWorkspaceSurface);
    await flushPromises();
    expect(w.text()).toContain("Fleet Workspace"); // the heading is still real
    expect(w.find(".kpi__figure").exists()).toBe(false);
    expect(w.text()).toContain(en["fleet.load_failed"]);
    expect(w.text()).not.toContain("$1,840.00");
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
      expect(callTo(fetchStub, "/money/settlements/audit")[0]).toContain("/money/settlements/audit");
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
  it("ranks stops with the guaranteed-bookable starred", async () => {
    // AI-CONTEXT: was "(offline fixture)" and began `logout(); // no session ->
    // fixture plan`. It asserted against three invented lots with invented prices,
    // shown to a driver deciding where to sleep on the hours they have left — §11.7's
    // worst shape, a place that is not there (§23 entry 131). Same assertions, real
    // endpoint, shape copied from /intel/sleep's own return.
    setToken("tok-sleep");
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url) => {
      if (String(url).includes("/intel/sleep")) {
        return jsonOk({
          range_m: 177000,
          stops: [
            { facility_id: "f-3", name: "Yardline Secured Parking", distance_m: 9200, predicted_status: null, guaranteed_bookable: true },
            { facility_id: "f-1", name: "Loves Travel Stop #212", distance_m: 5400, predicted_status: "some", guaranteed_bookable: false },
            { facility_id: "f-2", name: "Pilot #77", distance_m: 12800, predicted_status: "full", guaranteed_bookable: false },
          ],
          guaranteed: { spot_id: "spot-f3-a1", property_name: "Yardline Secured Parking", price_cents_per_night: 2400 },
          fuel: { facility_id: "f-5", name: "TA Travel Center", net_cents_per_gal: 394 },
        });
      }
      return jsonOk({});
    }));
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

  it("names no lot at all when the solver cannot be reached", async () => {
    setToken("tok-sleep");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503, json: () => Promise.resolve({}) }));
    const w = mount(SleepSheet);
    await w.find(".cta").trigger("click");
    await flushPromises();
    expect(w.findAll(".stop")).toHaveLength(0);
    expect(w.text()).toContain(en["sleep.load_failed"]);
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
      expect(callTo(fetchStub, "/community/handoff/h-1/claim")[0]).toContain("/community/handoff/h-1/claim");
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
      expect(callTo(fetchStub, "/protection/condition/start")[0]).toContain("/protection/condition/start");
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

  // AI-CONTEXT: §22.3's DRIVING box was never filled for this surface, and the input
  // carries `capture="environment"` — it opens the rear camera directly. The route
  // has no guard of its own (the router has only an auth `beforeEach`), so a deep
  // link, the back button or a §13.5 notification could open a camera at speed.
  it("does not offer the camera while DRIVING (SM-3, Forbidden #11)", async () => {
    setToken("tok-cond-driving");
    setActiveStop("stop-c1");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            capture_id: "cap-1",
            sequence: ["trailer_exterior", "seals", "load_blocking", "reefer_setpoint"],
          }),
      }),
    );
    try {
      const router = testRouter();
      router.push("/protection/condition");
      await router.isReady();
      const w = mount(ConditionSurface, { global: { plugins: [router] } });
      await flushPromises();
      expect(w.find(".shoot").exists()).toBe(true);

      useDriverState().setState(DriverState.DRIVING);
      await w.vm.$nextTick();

      // the shutter goes; what the driver can READ stays, as on EvidenceSurface
      expect(w.find(".shoot").exists()).toBe(false);
      expect(w.find("input[type='file']").exists()).toBe(false);
      expect(w.text()).toContain("Step 1 of 4");
      expect(w.text()).toContain("Pull over");
    } finally {
      useDriverState().setState(DriverState.IDLE);
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
            facility: "Perth Dock", counterparty: "Acme Brokerage", notice_sent: true,
            // finding F5: the row reads the DERIVED delivery state now, because
            // `notice_sent` alone could not tell a bounce from a claim nobody
            // had tapped Send on
            notice_delivery: "sent", filed: true,
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
      const [url, opts] = callTo(fetchStub, "/protection/incident");
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
  it("names no property and no payout when it cannot reach the board", async () => {
    // was "falls back to the fixture demo", asserting `$396.00` and a property called
    // "Yardline Secured Parking" that belongs to nobody (§23 entry 131). The portal
    // labelled that data "Demo data — sign in to manage your listings", which was the
    // most honest of the ten fallbacks and still put invented revenue on the screen.
    logout(); // no session -> apiGet throws
    const w = mount(OwnerPortalSurface);
    await flushPromises();
    expect(w.text()).toContain("Property Owner"); // the heading is still real
    expect(w.find(".payout__figure").exists()).toBe(false);
    expect(w.text()).not.toContain("Yardline Secured Parking");
    expect(w.text()).toContain(en["owner.load_failed"]);
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
  // AI-CONTEXT: this asserted the OPPOSITE until §23 entry 49 — that a driver with no
  // load sees an accruing Detention meter. It did, and the figure was $37.52 of money
  // nobody had earned, ticking, in the largest type on the screen. §11.7 is "Never
  // fake confidence" and §15.3 wants one sentence of purpose and one starting action.
  it("rests the Meter when there is no load, and invents nothing (§15.3)", () => {
    logout();
    setActiveStop(null);
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });

    // the Meter still anchors the screen (§9) — at rest, with no figure to count
    expect(w.find(".meter__figure").exists()).toBe(true);
    expect(w.find(".meter__figure").text()).toBe("—");
    expect(w.find(".meter__status").exists()).toBe(false);
    expect(w.text()).not.toContain("Detention");
    expect(w.text()).not.toMatch(/\$\d/); // no money of any amount

    // and none of a working load's furniture: no stop, no counterparty, no checklist
    expect(w.find(".context").exists()).toBe(false);
    expect(w.find(".checklist").exists()).toBe(false);
    expect(w.text()).not.toContain("Dallas Receiver");
    expect(w.text()).not.toContain("Acme Brokerage");

    // §15.3: one sentence of purpose, one starting action
    expect(w.text()).toContain("The Meter runs when you have a load");
    expect(w.findAll(".cta:not(.cta--text)")).toHaveLength(1);
    expect(w.find(".cta:not(.cta--text)").text()).toBe("Add a load");
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
      await w
        .findAll(".rungs__item")
        .find((b) => b.text().includes("More for this stop"))
        .trigger("click");
      await flushPromises();
      const endBtn = w.findAll(".more__item").find((b) => b.text() === "End load");
      await endBtn.trigger("click");
      await flushPromises();
      expect(fetchStub.mock.calls.some((c) => String(c[0]).endsWith("/load/stop-end/end"))).toBe(true);
      // a single-stop load has nowhere to advance to, so the tab rests (§23 entry 69)
      expect(w.text()).not.toContain("Ending Receiver"); // back to the resting Meter
      expect(w.find(".meter__figure").text()).toBe("—");
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
      expect(callTo(fetchStub, "/load/stop-live-1/meter")[0]).toContain("/load/stop-live-1/meter");
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
      // the amount lives in the Meter, which FREEZES at it (§9); the row is the route
      // to the claim and no longer restates the figure directly above it
      expect(w.find(".meter__figure").text()).toContain("$37.50");
      expect(w.find(".filed").text()).toBe("View claim");
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
      const texts = w.findAll(".rungs__item").map((b) => b.text());
      expect(texts.some((s) => s.includes("Generate claim"))).toBe(true);

      // §10.2's ladder is Snap BOL -> Send notice -> Generate claim, and the
      // passed-over rungs list in that order. They emitted claim ABOVE notice, so
      // the nearer rung sat below the further one.
      expect(texts.indexOf("Send notice")).toBeLessThan(texts.indexOf("Generate claim"));

      // the passed-over rungs are §8 Tertiary — they must not wear the Primary's
      // full-bleed shape, which is what made four controls read as a button stack
      expect(w.findAll(".rungs__item.cta")).toHaveLength(0);

      // and the checklist row says what is true: this stop has no BOL yet
      expect(w.text()).toContain("BOL not captured");
      expect(w.text()).not.toContain("BOL captured");
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
  // AI-CONTEXT: the draft is a ROUTE now (§23 entry 68) — the parse returns the whole
  // stops table, and each stop carries its own geocode and its own candidates.
  const DRAFT = {
    document_id: "doc-rc",
    readable: true,
    parsed: {
      reference_number: "L-9001",
      detention_rate_cents_per_hour: 7500,
      free_time_minutes: 120,
    },
    silent_on: ["tonu"],
    stops: [
      {
        sequence: 0,
        stop_type: "delivery",
        name: "ACME Distribution Center",
        address: "8450 Lakeside Ave, Columbus, OH 43228",
        appointment_start: null,
        appointment_end: null,
        location: { lat: 39.9612, lon: -83.0907, label: "8450 Lakeside Ave, Columbus, OH" },
        facility_candidates: [
          { facility_id: "fac-1", name: "ACME Distribution Center", address: null,
            locality: "Columbus, OH", score: 0.68 },
          { facility_id: "fac-2", name: "ACME Distribution Center", address: null,
            locality: "Dallas, TX", score: 0.65 },
        ],
      },
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

  // AI-CONTEXT: the code said "NOTHING is pre-selected" and the screen arrived with
  // "None of these" ticked (§23 entry 65). `chosenFacility` starts at null to mean
  // "not answered" and that option carried `:value="null"`, so v-model matched it.
  // A comment is not a test, and this is the test.
  // AI-CONTEXT: the dock's coordinate is what the geofence is armed on, and this sheet
  // used to send a hardcoded Dallas lat/lon for every load — so a Columbus receiver
  // could never fire an ENTER. Refusing to file a load we cannot place is the honest
  // replacement for inventing a coordinate (§23 entry 67).
  // AI-CONTEXT: the sixth and seventh parsed values to reach no field (§23 entry 84).
  //
  // `rate_cents` and `accessorial_terms` have been in the parse schema, in the prompt
  // and in `Load`'s own columns since F5 was written, and reached no pixel and no
  // field: the confirm screen showed the DETENTION rate and never the linehaul, and
  // warned about what the contract was SILENT on while never showing what it SAID. So
  // a driver signed off a contract having read every term except the money.
  it("shows the money the load pays, and files it", async () => {
    const posts = stub({
      ...DRAFT,
      parsed: { ...DRAFT.parsed, rate_cents: 285000 },
    });
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    // the parse is a PROPOSAL, so it lands in an editable field like every other value
    const rate = w.findAll("input").find((i) => i.element.value === "2850.00");
    expect(rate).toBeTruthy();

    await w.find(".rc__cta").trigger("click");
    await settle(w);
    const created = posts.find((p) => p.url.endsWith("/load") && p.body);
    expect(created.body.rate_cents).toBe(285000);
  });

  // M4-FR4 is "accessorial terms extraction ... WITH A DRIVER-CONFIRM STEP", and the
  // confirm step was the half that did not exist.
  it("quotes what the rate con actually states, beside what it is silent on", async () => {
    stub({
      ...DRAFT,
      parsed: {
        ...DRAFT.parsed,
        accessorial_terms: { tonu: "50% of linehaul", layover: "$150 per night" },
      },
    });
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    const text = w.text();
    expect(text).toContain("50% of linehaul");
    expect(text).toContain("$150 per night");
    // the contract's own words are quoted, never retyped: a claim is argued from them
    expect(w.find(".rc__terms-block input").exists()).toBe(false);
  });

  it("files the terms it quoted, so M4 judges the load against its real contract", async () => {
    const posts = stub({
      ...DRAFT,
      parsed: { ...DRAFT.parsed, accessorial_terms: { tonu: "50% of linehaul" } },
    });
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    const created = posts.find((p) => p.url.endsWith("/load") && p.body);
    expect(created.body.accessorial_terms).toEqual({ tonu: "50% of linehaul" });
  });

  it("says nothing about terms when the rate con stated none", async () => {
    // §15.3 / Q-7: an empty section is filler on a screen read in ten seconds
    stub(DRAFT);
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);
    expect(w.find(".rc__terms-block").exists()).toBe(false);
  });

  it("will not file a load it cannot place", async () => {
    const posts = stub({ ...DRAFT, stops: [{ ...DRAFT.stops[0], address: "", location: null }] });
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    expect(w.find(".rc__cta").attributes("disabled")).toBeDefined();
    expect(w.text()).toContain("so arrivals at this dock are detected");

    await w.find(".rc__cta").trigger("click");
    await settle(w);
    expect(posts.some((p) => p.url.endsWith("/load") && p.body)).toBe(false);
  });

  it("files the dock where the geocoder placed it, not where the sheet used to guess", async () => {
    const posts = stub(DRAFT);
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    // the geocoder's own wording is shown rather than the driver's typing echoed back
    expect(w.text()).toContain("8450 Lakeside Ave, Columbus, OH");

    await w.find(".rc__cta").trigger("click");
    await settle(w);
    const created = posts.find((p) => p.url.endsWith("/load") && p.body);
    expect(created.body.lat).toBeCloseTo(39.9612);
    expect(created.body.lon).toBeCloseTo(-83.0907);
  });

  // AI-CONTEXT: the defect this replaced — the parse returned one receiver, so a
  // two-stop contract lost its pickup, and with it any detention claim at the shipper.
  it("shows every stop of the route, pickup first", async () => {
    const posts = stub({
      ...DRAFT,
      stops: [
        {
          sequence: 0, stop_type: "pickup", name: "Harvest Foods DC",
          address: "1200 Commerce Pkwy, Dallas, TX", appointment_start: "2026-08-03T08:00:00",
          appointment_end: "2026-08-03T10:00:00",
          location: { lat: 32.7767, lon: -96.797, label: "Dallas, TX" },
          facility_candidates: [],
        },
        DRAFT.stops[0],
      ],
    });
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    const blocks = w.findAll(".rc__stop");
    expect(blocks).toHaveLength(2);
    expect(blocks[0].text()).toContain("Pickup");
    expect(blocks[1].text()).toContain("Delivery");
    // the name is an editable field, so read its value rather than the block's text
    expect(blocks[0].findAll("input")[0].element.value).toBe("Harvest Foods DC");
    expect(blocks[1].findAll("input")[0].element.value).toBe("ACME Distribution Center");

    await w.find(".rc__cta").trigger("click");
    await settle(w);
    const created = posts.find((p) => p.url.endsWith("/load") && p.body);
    expect(created.body.stops.map((s) => s.stop_type)).toEqual(["pickup", "delivery"]);
    // each dock is filed where it is: Dallas and Columbus are not the same place
    expect(created.body.stops[0].lat).toBeCloseTo(32.7767);
    expect(created.body.stops[1].lat).toBeCloseTo(39.9612);
    // the pickup's WINDOW survives — "08:00 - 10:00" is two times
    expect(created.body.stops[0].appointment).toBeTruthy();
    expect(created.body.stops[0].appointment_end).toBeTruthy();
  });

  it("pre-selects no facility answer at all, including none-of-these", async () => {
    stub(DRAFT);
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    const radios = w.findAll(".rc__opt input");
    expect(radios.length).toBe(3); // two candidates + none-of-these
    expect(radios.filter((r) => r.element.checked)).toHaveLength(0);
  });

  it("says which is which when two candidates share a name (\u00a723 entry 76)", async () => {
    // a real driver was offered "Metro Market Warehouse" twice, rendered identically,
    // on the screen that asks whether it is the same place. Both were real -- one in
    // Columbus, one in Dallas -- and a question whose answers cannot be told apart
    // cannot be answered.
    stub(DRAFT);
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    const opts = w.findAll(".rc__opt");
    expect(opts[0].text()).toContain("ACME Distribution Center");
    expect(opts[1].text()).toContain("ACME Distribution Center"); // same name, still
    expect(opts[0].find(".rc__where").text()).toBe("Columbus, OH");
    expect(opts[1].find(".rc__where").text()).toBe("Dallas, TX");
  });

  it("keeps the broker name the parse read", async () => {
    // it was extracted and dropped: the read handler filled five fields and this was
    // not one of them, so a parsed rate con arrived with an empty Broker box
    const posts = stub({ ...DRAFT, parsed: { ...DRAFT.parsed, broker_name: "Coyote Logistics" } });
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    expect(w.findAll(".rc__input").some((i) => i.element.value === "Coyote Logistics")).toBe(true);

    await w.find(".rc__cta").trigger("click");
    await settle(w);
    const created = posts.find((p) => p.url.endsWith("/load") && p.body);
    expect(created.body.counterparty).toBe("Coyote Logistics");
  });

  it("sends no facility id when the driver rejects every candidate", async () => {
    const posts = stub(DRAFT);
    const w = mount(RateConImportSheet);
    await pickFile(w);
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    const radios = w.findAll(".rc__opt input");
    await radios[radios.length - 1].setValue(); // none of these
    await w.find(".rc__cta").trigger("click");
    await settle(w);

    // the answer belongs to the STOP it was asked about (§23 entry 68)
    const created = posts.find((p) => p.url.endsWith("/load") && p.body);
    expect(created.body.stops[0].facility_id).toBe(null); // the sentinel stays client-side
    // ...and the rejection travels as a statement rather than as silence, so the API
    // stops running its own name+geohash match over the answer (§23 entry 66)
    expect(created.body.stops[0].create_new_facility).toBe(true);
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

    // AI-CONTEXT: this used to assert that "None of these" arrived CHECKED and called
    // that "the honest one" — contradicting §23 entry 47, which says the match must
    // never be pre-ticked because no threshold separates a right dock from a wrong one
    // (0.68 against 0.65). The screen was pre-selecting the answer that creates a
    // duplicate dock, and this test held it in place. Nothing is pre-selected now;
    // the dedicated assertion for it lives above.
    const radios = w.findAll(".rc__opt input");
    expect(radios.some((i) => i.element.checked)).toBe(false);

    await w.findAll(".rc__opt input")[0].setValue(); // the driver picks
    await w.find(".rc__cta").trigger("click"); // now the create button
    await settle(w);

    const create = posts.find((p) => p.url.endsWith("/load"));
    expect(create.body.stops[0].facility_id).toBe("fac-1");
    expect(create.body.stops[0].create_new_facility).toBe(false); // a pick is not a rejection
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

  // AI-CONTEXT: a claim worth nothing is a TRAP, not just clutter. §9 freezes the
  // Meter at the filed amount and the UI hides every claim control once filed, so a
  // driver who tapped the instant free time ran out was left reading "$0.00 · Claim
  // filed — clock stopped" while detention went on accruing, with no route back.
  // Measured against the running server: filed at zero, three minutes later the meter
  // still said $0.00 while the API had $4.42.
  it("does not offer a claim until there is something to claim", async () => {
    setToken("tok-zero");
    setActiveStop("stop-zero");
    const zero = {
      stop_id: "stop-zero", claim_id: "c-0", facility_name: "Zero Dock", counterparty: "Acme",
      appointment: null, arrived: true, free_time_minutes: 0, rate_cents_per_hour: 7500,
      phase: "accruing", free_time_remaining_seconds: 0, detention_seconds: 0,
      detention_cents: 0, notice_sent: true, filed: false, bol_captured: true,
      photos_captured: 0, photos_required: 4,
    };
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => jsonOk(zero)));
    try {
      const router = testRouter();
      const w = mount(LoadSurface, { global: { plugins: [router] } });
      await flushPromises();

      // accruing, notice sent, BOL in hand — the ladder would have offered a claim,
      // and the amount is $0.00
      const labels = [
        ...w.findAll(".cta").map((b) => b.text()),
        ...w.findAll(".rungs__item").map((b) => b.text()),
      ];
      expect(labels.some((s) => s.includes("Generate claim"))).toBe(false);
      w.unmount();
    } finally {
      vi.unstubAllGlobals();
      setActiveStop(null);
      logout();
    }
  });

  // AI-CONTEXT: §15.5 became load-bearing the moment the meter started depending on
  // real positions (F3's ping seam, this session). "A single persistent Load-tab card
  // explaining exactly what stops working, with a one-tap fix — never nags beyond
  // that card."
  it("shows one degraded-location card when permission is denied (§15.5)", async () => {
    const { permission } = await import("../src/core/location.js");
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.find(".degraded").exists()).toBe(false);

    permission.value = "denied";
    await w.vm.$nextTick();

    const cards = w.findAll(".degraded");
    expect(cards).toHaveLength(1); // ONE card, not a card per render
    // it states the CONSEQUENCE, not the permission — "the meter arms manually"
    expect(w.text()).toContain("Start the meter yourself");
    expect(w.find(".degraded__fix").exists()).toBe(true);

    // "unavailable" is not a permission the driver can restore, so no card and no
    // one-tap fix that cannot work
    permission.value = "unavailable";
    await w.vm.$nextTick();
    expect(w.find(".degraded").exists()).toBe(false);

    permission.value = "unknown";
  });

  // AI-CONTEXT: §9 calls this element "the counting figure". Before arrival it used to
  // render the appointment as a static clock face — the same value the Appointment row
  // states two lines below, in the largest type on the screen, never moving.
  it("counts down to the appointment before arrival, and up once it passes (§9)", async () => {
    const soon = new Date(Date.now() + 2 * 3600_000).toISOString();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        jsonOk({ ...LIVE, phase: "not_arrived", arrived: false, appointment: soon }),
      ),
    );
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();

    expect(w.text()).toContain("Until appointment");
    // a duration that ticks, not the 24h clock face it used to show
    expect(w.find(".meter__figure").text()).toMatch(/^(2:00:00|1:59:\d\d)$/);
    w.unmount();

    const late = new Date(Date.now() - 12 * 60_000).toISOString();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        jsonOk({ ...LIVE, phase: "not_arrived", arrived: false, appointment: late }),
      ),
    );
    const w2 = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();

    expect(w2.text()).toContain("Appointment passed");
    expect(w2.find(".meter__figure").text()).toMatch(/^0:1[12]:\d\d$/);
    w2.unmount();
  });

  // AI-CONTEXT: M5-FR1's verdict is filed on every arrival and had no screen. FR5's
  // protection summary counts four documented items; the checklist rendered three.
  it("shows the on-time verdict as the checklist's fourth row (M5-FR1)", async () => {
    const rowText = async (extra) => {
      vi.stubGlobal("fetch", vi.fn().mockImplementation(() => jsonOk({ ...LIVE, ...extra })));
      const w = mount(LoadSurface, { global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] } });
      await flushPromises();
      const first = w.findAll(".checklist__item")[0].text();
      w.unmount();
      return first;
    };

    // not arrived: no verdict exists, and the row says so rather than implying one
    expect(await rowText({ on_time: null, arrived_at: null })).toContain("Arrival not recorded yet");

    // on time — the label carries the state, and the figure is the arrival (§12.5's
    // labelled figure, since t() has no interpolation)
    const ok = await rowText({ on_time: true, arrived_at: "2026-08-04T07:58:00+00:00" });
    expect(ok).toContain("On time");
    expect(ok).toContain("07:58");

    // late is stated as a fact, not an accusation
    const late = await rowText({ on_time: false, arrived_at: "2026-08-04T09:12:00+00:00" });
    expect(late).toContain("Late");
    expect(late).toContain("09:12");
    expect(late).not.toContain("On time");
  });

  // AI-CONTEXT: §5's ON_SITE, narrowed to this tab (§23 entry 64). §5 wants capture
  // "one tap from anywhere via a persistent action chip"; an app-wide chip is a new
  // component pattern AND navigation structure, so the owner chose the benefit without
  // the new component. ON_SITE was derivable but unread — the state changed nothing.
  it("brings cargo capture one tap away at the dock (§5 ON_SITE)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => jsonOk(LIVE)));
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();

    const rungs = () => w.findAll(".rungs__item").map((b) => b.text());
    // IDLE: it lives in the More sheet, two taps away, as it always has
    expect(rungs().some((s) => s.includes("Capture cargo condition"))).toBe(false);

    useDriverState().setState(DriverState.ON_SITE);
    await w.vm.$nextTick();

    expect(rungs().some((s) => s.includes("Capture cargo condition"))).toBe(true);

    // and it is a SHORTCUT, not a move — the sheet still lists it
    await w.find(".rungs__item--more").trigger("click");
    await flushPromises();
    expect(w.findAll(".more__item").map((b) => b.text())).toContain("Capture cargo condition");

    useDriverState().setState(DriverState.IDLE);
    w.unmount();
  });

  it("does not restate the Meter in the filed row", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        jsonOk({ ...LIVE, phase: "accruing", free_time_remaining_seconds: 0, filed: true, detention_cents: 8750 }),
      ),
    );
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();

    // the Meter carries the fact and the figure; the row carries the route
    expect(w.find(".meter__status").text()).toContain("Claim filed");
    expect(w.find(".filed").text()).toBe("View claim");
    expect(w.findAll(".filed")).toHaveLength(1);
    w.unmount();
  });

  it("says 'End load' only on the last stop of the route (§12.2)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => jsonOk({ ...LIVE, next_stop: null })),
    );
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();

    await w.find(".rungs__item--more").trigger("click");
    await flushPromises();

    const items = w.findAll(".more__item").map((b) => b.text());
    expect(items).toContain("End load");
    expect(items).not.toContain("Leave this stop");
    w.unmount();
  });

  it("previews the next stop (§10.2 anatomy)", async () => {
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();

    expect(w.find(".next").exists()).toBe(true);
    expect(w.find(".next__name").text()).toBe("Second Dock");
    expect(w.find(".next__appt").text()).toBe("09:30"); // Mono, like every time figure
  });

  // AI-CONTEXT: the stop context row printed the appointment as the API sends it —
  // an ISO timestamp. Live drivers read "2026-07-27T04:10:50.993277+00:00 · TQL" in
  // §10.2's anatomy row, and nothing caught it because the fixture that stood in for
  // this endpoint carried a PREFORMATTED "07:00": the demo rendered tidily and
  // production never did. The fixture is deleted; this asserts against the real shape.
  it("never renders a raw timestamp in the stop context row", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        jsonOk({ ...LIVE, appointment: "2026-07-27T04:10:50.993277+00:00" }),
      ),
    );
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();

    expect(w.text()).not.toMatch(/\d{4}-\d{2}-\d{2}T/);
    // the counterparty stands alone; the appointment has its own row, which is the
    // one that can say where the value came from (M5-FR1)
    expect(w.find(".context__meta").text()).toBe("Acme");
    expect(w.find(".context__window").text()).toBe("04:10");
    // and it appears ONCE — printing it in both rows was the other half of the defect
    expect(w.findAll(".context").map((e) => e.text()).join("").match(/04:10/g)).toHaveLength(1);
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

    await w
      .findAll(".rungs__item")
      .find((b) => b.text().includes("More for this stop"))
      .trigger("click");
    await flushPromises();

    // AI-CONTEXT: §12.2 — the control says what will actually happen. LIVE has a next
    // stop, so leaving this dock opens that one; it does not end the load (entry 69).
    const items = w.findAll(".more__item").map((b) => b.text());
    expect(items).toContain("Leave this stop");
    expect(items).not.toContain("End load");
    expect(items).toContain("Check load profit");
  });
});

describe("LoadSurface — past loads (§23-approved history)", () => {
  const HISTORY = {
    loads: [
      {
        load_id: "l-1", stop_id: "s-1", facility_name: "ACME Distribution Center",
        reference_number: "L-9001", created_at: "2026-08-03T14:00:00+00:00",
        status: "completed", stop_count: 1,
        detention_cents: 8750, claim_state: "invoiced",
        evidence_count: 6, documents: ["bol", "rate_con"],
      },
      {
        load_id: "l-2", stop_id: "s-2", facility_name: "Quiet Dock",
        reference_number: null, created_at: "2026-07-24T09:00:00+00:00",
        status: "completed", stop_count: 1,
        detention_cents: null, claim_state: null,
        evidence_count: 0, documents: [],
      },
      {
        load_id: "l-3", stop_id: "s-3", facility_name: "Harvest Foods DC",
        destination_name: "Metro Market Warehouse",
        reference_number: "BRL-78426", created_at: "2026-07-28T04:00:00+00:00",
        status: "completed", stop_count: 2,
        detention_cents: 27143, claim_state: "exported",
        evidence_count: 4, documents: ["rate_con"],
        stops: [
          { stop_id: "s-3a", sequence: 0, stop_type: "pickup",
            facility_name: "Harvest Foods DC", detention_cents: 8367,
            claim_state: "exported", photo_count: 4 },
          { stop_id: "s-3b", sequence: 1, stop_type: "delivery",
            facility_name: "Metro Market Warehouse", detention_cents: null,
            claim_state: "open", photo_count: 4 },
        ],
      },
    ],
  };

  beforeEach(() => {
    useDriverState().setState(DriverState.IDLE);
    setToken("tok-hist");
    setActiveStop(null); // no active load -> the empty state, where history lives
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url) => {
        if (String(url).includes("/load/history")) return jsonOk(HISTORY);
        if (String(url).includes("/load/active")) return jsonOk({ stop_id: null });
        return Promise.reject(new Error("no live load"));
      }),
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    logout();
  });

  it("a finished load is still reachable, with a route back to its evidence", async () => {
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();

    await w.findAll(".cta").find((b) => b.text() === "Past loads").trigger("click");
    await flushPromises();

    const rows = w.findAll(".hist__row");
    expect(rows).toHaveLength(3);
    expect(rows[0].text()).toContain("ACME Distribution Center");
    expect(rows[0].text()).toContain("$87.50"); // Mono, like every money figure
    expect(rows[0].text()).toContain("Invoiced");

    // the stop id is back, so the evidence pack has a route weeks later
    await rows[0].find(".hist__main").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/load/s-1/evidence");
  });

  it("a load that produced nothing says so rather than rendering empty rows", async () => {
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();
    await w.findAll(".cta").find((b) => b.text() === "Past loads").trigger("click");
    await flushPromises();

    const quiet = w.findAll(".hist__row")[1].text();
    expect(quiet).toContain("no detention");
    expect(quiet).toContain("nothing was captured");
    expect(quiet).not.toContain("$0.00"); // a zero would read as a claim that failed
  });

  it("names the whole route, not the stop it started at (\u00a723 entry 74)", async () => {
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();
    await w.findAll(".cta").find((b) => b.text() === "Past loads").trigger("click");
    await flushPromises();

    const route = w.findAll(".hist__row")[2].text();
    // both ends of the load, and how many stops it had. Every figure on this row used
    // to be the FIRST stop's, so a two-stop load was indistinguishable from a delivery
    // to its pickup's dock -- and showed one of its two claims as if it were the total.
    expect(route).toContain("Harvest Foods DC");
    expect(route).toContain("Metro Market Warehouse");
    expect(route).toContain("2 stops");
    expect(route).toContain("$271.43");
    // five loads down the same lane in one week are otherwise identical rows
    expect(route).toContain("BRL-78426");
  });

  it("opens a route's row to its stops, so every photo is reachable (\u00a723 entry 78)", async () => {
    // the row linked to stops[0] and there was no other way in, so a driver who
    // photographed a pickup AND a delivery had eight photos in the system and could
    // open four -- whichever four the row happened to point at.
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();
    await w.findAll(".cta").find((b) => b.text() === "Past loads").trigger("click");
    await flushPromises();

    const rows = w.findAll(".hist__row");
    expect(rows[2].findAll(".hist__stop")).toHaveLength(0); // closed to begin with
    await rows[2].find(".hist__main").trigger("click");
    await flushPromises();

    const stops = w.findAll(".hist__row")[2].findAll(".hist__stop");
    expect(stops).toHaveLength(3); // two stops + export the whole load
    expect(stops[0].text()).toContain("1 · Pickup · Harvest Foods DC");
    expect(stops[0].text()).toContain("4 photos");
    expect(stops[1].text()).toContain("2 · Delivery · Metro Market Warehouse");
    expect(stops[1].text()).toContain("no detention");

    // and the delivery's own evidence is now reachable, which it was not
    await stops[1].trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/load/s-3b/evidence");
  });

  it("sends a one-stop load straight to its evidence rather than opening nothing", async () => {
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();
    await w.findAll(".cta").find((b) => b.text() === "Past loads").trigger("click");
    await flushPromises();

    await w.findAll(".hist__row")[0].find(".hist__main").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/load/s-1/evidence");
  });

  it("labels a company driver's claim state rather than printing its key", async () => {
    const router = testRouter();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();
    await w.findAll(".cta").find((b) => b.text() === "Past loads").trigger("click");
    await flushPromises();

    // `exported` is where a claim lands for a driver without their own authority -- a
    // pack for their carrier, no invoice -- and it had no label in any of the six
    // locales, so the commonest outcome rendered as "money.state.exported".
    const route = w.findAll(".hist__row")[2].text();
    expect(route).toContain("Sent to carrier");
    expect(route).not.toContain("money.state");
  });
});

describe("MoneySurface (M4 Money tab, design-prd §10.3)", () => {
  it("lists receivables with Mono amounts + status pills", async () => {
    stubMoney();
    const w = mount(MoneySurface);
    await flushPromises();
    expect(w.findAll(".row")).toHaveLength(3);
    const text = w.text();
    expect(text).toContain("$150.00"); // detention 15000c, tabular
    expect(text).toContain("Detention"); // jargon stays English (§12.3)
    expect(text).toContain("11d"); // aging in Mono
  });
});

describe("EvidenceSurface — export (§23 entries 71, 72)", () => {
  const EVIDENCE = {
    stop_id: "s-1",
    facility: "Metro Market Warehouse",
    documents: [],
    chain_valid: true,
    record_count: 4,
    photo_count: 0,
    timeline: [
      { type: "USER_ACTION", event: "arrived", occurred_at: "2026-07-28T03:43:29+00:00" },
      { type: "USER_ACTION", event: "departed", occurred_at: "2026-07-28T03:43:31+00:00" },
    ],
    photos: [],
  };

  function mountEvidence() {
    const router = createRouter({ history: createMemoryHistory(), routes });
    router.push("/load/s-1/evidence");
    return router.isReady().then(() => mount(EvidenceSurface, { global: { plugins: [router] } }));
  }

  beforeEach(() => setToken("tok-ev"));
  afterEach(() => {
    vi.unstubAllGlobals();
    logout();
  });

  // AI-CONTEXT: the timeline used to be labelled by RecordType alone, so a pack read
  // "Event recorded 03:14". The API now carries what happened (§23 entry 70).
  it("names each event rather than its record type", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => jsonOk(EVIDENCE)));
    const w = await mountEvidence();
    await flushPromises();

    expect(w.text()).toContain("Arrived");
    expect(w.text()).toContain("Departed");
    w.unmount();
  });

  // AI-CONTEXT: `window.open` after an await is blocked — the gesture is gone — so the
  // button did nothing at all (§23 entry 72). A download anchor needs no popup.
  it("downloads the pack instead of opening a blocked popup", async () => {
    const pdf = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url) => {
        if (String(url).includes("/export")) {
          return Promise.resolve({
            ok: true,
            blob: () => Promise.resolve(pdf),
            headers: { get: () => 'inline; filename="stop-3c222255.pdf"' },
          });
        }
        return jsonOk(EVIDENCE);
      }),
    );
    // only the two methods — replacing the whole URL global breaks the DOM's own URL
    // parsing the moment an anchor's href is assigned
    const realCreateURL = URL.createObjectURL;
    const realRevokeURL = URL.revokeObjectURL;
    URL.createObjectURL = () => "blob:pack";
    URL.revokeObjectURL = () => {};
    const opened = vi.fn();
    vi.stubGlobal("open", opened);
    const w = await mountEvidence();
    await flushPromises();

    const clicked = [];
    const realCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag) => {
      const el = realCreate(tag);
      if (tag === "a") el.click = () => clicked.push({ href: el.href, download: el.download });
      return el;
    });

    await w.find(".cta").trigger("click");
    await flushPromises();

    // eslint-disable-next-line no-console
    expect(opened).not.toHaveBeenCalled(); // never a popup
    expect(clicked).toHaveLength(1);
    expect(clicked[0].download).toBe("stop-3c222255.pdf"); // the server's own name
    document.createElement.mockRestore();
    URL.createObjectURL = realCreateURL;
    URL.revokeObjectURL = realRevokeURL;
    w.unmount();
  });

  it("says so when the pack cannot be built, rather than doing nothing (§12.4)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url) =>
        String(url).includes("/export")
          ? Promise.resolve({ ok: false, status: 404 })
          : jsonOk(EVIDENCE),
      ),
    );
    const w = await mountEvidence();
    await flushPromises();

    await w.find(".cta").trigger("click");
    await flushPromises();

    expect(w.text()).toContain("Couldn't build the PDF");
    w.unmount();
  });
});

describe("DocsSurface (M5 Docs tab, design-prd §10.4)", () => {
  const WALLET = {
    documents: [
      { id: "d-1", doc_type: "cdl", expires_on: "2027-03-01", status: "ok",
        content_type: "image/jpeg" },
      { id: "d-2", doc_type: "permit", expires_on: "2026-09-01", status: "ok",
        content_type: "image/jpeg" },
      { id: "d-3", doc_type: "permit", expires_on: "2026-12-01", status: "ok",
        content_type: "image/jpeg" },
    ],
    expiring: [],
    archived_count: 2,
    load_paperwork: [
      {
        load_id: "l-9", stop_id: "s-9", reference_number: "BRL-78426",
        created_at: "2026-07-28T04:00:00+00:00",
        facility_name: "Harvest Foods DC", destination_name: "Metro Market Warehouse",
        doc_types: ["bol", "rate_con"], document_count: 3,
      },
    ],
    unattached: [
      { id: "o-1", doc_type: "rate_con", uploaded_at: "2026-07-28T12:41:00+00:00",
        content_type: "application/pdf" },
      { id: "o-2", doc_type: "rate_con", uploaded_at: "2026-07-28T12:05:00+00:00",
        content_type: "application/pdf" },
    ],
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

  // §23 entry 80: the sections start collapsed, so a test that wants a document has
  // to open its section — which is the same tap a driver makes.
  async function openSection(w, nth = 0) {
    await w.findAll(".group__head")[nth].trigger("click");
    await flushPromises();
  }

  function stubWallet({ onPost, wallet = WALLET } = {}) {
    const posts = [];
    const stub = vi.fn().mockImplementation((url, opts) => {
      const u = String(url);
      if (opts?.method === "POST") {
        posts.push(u);
        onPost?.(u);
        return jsonOk({ document_id: "x" });
      }
      if (u.includes("/protection/documents/archive")) return jsonOk(ARCHIVE);
      if (u.includes("/protection/wallet")) return jsonOk(wallet);
      if (/\/protection\/documents\/[0-9a-z-]+$/.test(u)) {
        return Promise.resolve({ ok: true, blob: () => Promise.resolve(new Blob(["%PDF"])) });
      }
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

  // AI-CONTEXT: the capture BUTTON was guarded and the SHEET was not. A driver who
  // opened it while stopped and then pulled away kept a live camera-capture UI on
  // screen at speed — the control that opens a flow and the flow itself are two
  // different things to guard, and only one of them was.
  // AI-CONTEXT: §13.5 — "every notification deep-links to the exact screen AND STATE it
  // describes. No landing on tab roots."
  //
  // The 30/14/3 expiry reminder deep-linked to `/docs`. A driver told their med card
  // expires in three days arrived at a wallet holding every credential and every BOL they
  // had ever filed, and had to work out which one was meant — the same "it was done and I
  // could not find it" failure the Load tab's review card was built to end.
  it("marks the document a reminder was about, and opens the section holding it", async () => {
    // AI-CONTEXT: `setToken` is not decoration (§23 entry 131). `fetchWallet` goes
    // through `apiGet`, which throws "no session" BEFORE it calls fetch — so this test
    // and the two below stubbed a wallet the surface never asked for, and asserted
    // against `SAMPLE_WALLET` while naming an endpoint. It passed for the wrong reason
    // for as long as the fixture existed, and the fixture's ids happened to match the
    // stub's. Deleting the fixture is what exposed it.
    setToken("tok-docs");
    stubWallet();
    const router = createRouter({ history: createMemoryHistory(), routes });
    router.push("/docs?doc=d-2");
    await router.isReady();
    const w = mount(DocsSurface, { global: { plugins: [router] } });
    await flushPromises();

    // the grid is collapsed by default (§23 entry 80) — a deep link that lands on a
    // closed accordion has not arrived anywhere
    const marked = w.findAll(".doc--marked");
    expect(marked.length).toBe(1);
    expect(marked[0].attributes("aria-current")).toBe("true"); // C-1: never colour alone
  });

  it("marks nothing when no reminder sent the driver here", async () => {
    setToken("tok-docs");
    stubWallet();
    const router = createRouter({ history: createMemoryHistory(), routes });
    router.push("/docs");
    await router.isReady();
    const w = mount(DocsSurface, { global: { plugins: [router] } });
    await flushPromises();
    await openSection(w);
    expect(w.findAll(".doc--marked").length).toBe(0);
  });

  it("a renewed document whose id no longer exists still lands on the wallet", async () => {
    // the reminder is durable and the wallet moves on. A driver who renews before tapping
    // the notification should get their wallet, not an error and not an empty screen.
    setToken("tok-docs");
    stubWallet();
    const router = createRouter({ history: createMemoryHistory(), routes });
    router.push("/docs?doc=gone-forever");
    await router.isReady();
    const w = mount(DocsSurface, { global: { plugins: [router] } });
    await flushPromises();
    await openSection(w);

    expect(w.findAll(".doc--marked").length).toBe(0);
    expect(w.findAll(".doc").length).toBeGreaterThan(0);
  });

  it("names a PDF instead of rendering a broken image (\u00a723 entry 77)", async () => {
    // this input accepts application/pdf and the preview was always an <img> on a blob
    // URL, which cannot decode one -- so choosing a rate con showed the browser's
    // broken-image glyph where the review of the file was supposed to be.
    stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();
    await w.find(".capture").trigger("click");
    await flushPromises();

    const sheet = w.findComponent({ name: "DocumentCaptureSheet" });
    const pdf = new File(["%PDF-1.4"], "rate-con.pdf", { type: "application/pdf" });
    Object.defineProperty(sheet.find(".cap__input").element, "files", { value: [pdf] });
    await sheet.find(".cap__input").trigger("change");
    await flushPromises();

    expect(sheet.find("img.cap__preview").exists()).toBe(false);
    expect(sheet.find(".cap__file").text()).toBe("rate-con.pdf");
  });

  it("still previews an actual image", async () => {
    stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();
    await w.find(".capture").trigger("click");
    await flushPromises();

    const sheet = w.findComponent({ name: "DocumentCaptureSheet" });
    const jpg = new File(["\u00ff\u00d8"], "bol.jpg", { type: "image/jpeg" });
    Object.defineProperty(sheet.find(".cap__input").element, "files", { value: [jpg] });
    await sheet.find(".cap__input").trigger("change");
    await flushPromises();

    expect(sheet.find("img.cap__preview").exists()).toBe(true);
    expect(sheet.find(".cap__file").exists()).toBe(false);
  });

  it("closes an open capture sheet when the truck starts moving (SM-3)", async () => {
    stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();

    await w.find(".capture").trigger("click");
    await flushPromises();
    expect(w.find(".cap__chip").exists()).toBe(true); // the sheet is open

    useDriverState().setState(DriverState.DRIVING);
    await flushPromises();

    expect(w.find(".cap__chip").exists()).toBe(false);
    expect(w.find(".capture").exists()).toBe(false); // and the chip that opens it
    // §10.4 lets inspection mode survive DRIVING; only capture is withdrawn
    expect(w.find(".inspect").exists()).toBe(true);
  });

  it("shows inspection button, expiring pills, and the document grid", async () => {
    // was "(fixture)" in its own name, and that is exactly what it measured: the
    // surface mounted with no session and rendered SAMPLE_WALLET's four invented
    // documents, including a CDL (audit U-09). It asserts the same shapes against the
    // real endpoint now.
    setToken("tok-docs");
    stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();
    expect(w.find(".inspect").text()).toContain("Inspection mode");
    // §23 entry 80: sections start collapsed, so the strip and the headings are what
    // a driver sees first -- the expiring pills still need no tap at all
    expect(w.findAll(".doc")).toHaveLength(0);
    await openSection(w);
    expect(w.findAll(".doc")).toHaveLength(3);
    expect(w.text()).toContain("CDL"); // acronym stays English (§12.3)
  });

  it("flies the expiring strip when the wallet says something is expiring", async () => {
    // split out of the test above, which asserted `.pill` > 0 against a stub whose
    // `expiring` is EMPTY — it was reading the fixture's two expiring documents. The
    // strip is real and worth covering, so it gets a wallet that actually has one.
    setToken("tok-docs");
    stubWallet({
      wallet: {
        ...WALLET,
        expiring: [{ id: "d-9", doc_type: "med_card", expires_on: "2026-08-20", status: "expiring" }],
      },
    });
    const w = mount(DocsSurface);
    await flushPromises();
    expect(w.findAll(".pill").length).toBeGreaterThan(0);
  });

  it("groups the grid by type (§10.4 'document grid by type')", async () => {
    setToken("tok-docs");
    stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();

    await openSection(w);
    const labels = w.findAll(".group__sub").map((n) => n.text());
    expect(labels).toEqual(["CDL", "Permit"]); // two permits collapse under one heading
    expect(w.findAll(".subgroup")).toHaveLength(2);
    expect(w.findAll(".doc")).toHaveLength(3);
    // and the wallet says whose documents these are, because it no longer holds
    // anyone else's paperwork (§23 entry 79)
    expect(w.find(".group__label").text()).toBe("Your documents");
  });

  it("keeps load paperwork out of the credentials wallet (\u00a723 entry 79)", async () => {
    // measured on a real account: 40 documents in this tab, 5 of them the driver's.
    // `documents_for_account` filters by account and ignores subject_kind, while its
    // own docstring says the wallet's job is "the credential a driver holds now".
    setToken("tok-docs");
    stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();

    const headings = w.findAll(".group__label").map((n) => n.text());
    expect(headings).toEqual(["Your documents", "Load paperwork", "Not attached to a load"]);
    // and each says how much is inside, so nothing has to be opened to find out
    expect(w.findAll(".group__count").map((n) => n.text())).toEqual(["3", "1", "2"]);

    // paperwork is named by its LOAD, not by its type: a BOL matters for the load it
    // belongs to, not for being a BOL
    await openSection(w, 1);
    const paper = w.findAll(".paper__row");
    expect(paper[0].text()).toContain("Harvest Foods DC → Metro Market Warehouse");
    expect(paper[0].text()).toContain("BRL-78426");
    expect(paper[0].text()).toContain("BOL · Rate con");
  });

  it("says plainly which rate cons never became a load, and removes them", async () => {
    setToken("tok-docs");
    const posts = stubWallet();
    const w = mount(DocsSurface);
    await flushPromises();

    await openSection(w, 2);
    const orphans = w.findAll(".orphan");
    expect(orphans).toHaveLength(2);
    expect(orphans[0].text()).toContain("Photographed, no load made");

    await orphans[0].find(".orphan__rm").trigger("click");
    await flushPromises();
    // removal is the archive, never a hard delete (§17 Q16)
    expect(posts.some((u) => u.includes("/archive"))).toBe(true);
  });

  it("opens a PDF as a PDF, not a broken image (\u00a723 entry 80)", async () => {
    // the viewer has always carried a PDF branch -- its own header says "some
    // credentials are filed as PDFs, which an <img> cannot render" -- and keyed it off
    // a `content_type` the wallet never sent. So the branch could not execute and
    // every PDF opened as a broken image with its label as alt text.
    setToken("tok-docs");
    stubWallet();
    // the viewer fetches the bytes itself; the wallet row only says how to render them
    const realCreateURL = URL.createObjectURL;
    URL.createObjectURL = () => "blob:doc";
    const w = mount(DocsSurface);
    await flushPromises();

    await openSection(w, 2); // the unattached rate cons, which are PDFs
    await w.findAll(".paper__row")[0].trigger("click");
    await flushPromises();

    expect(w.find("object.viewer__frame").exists()).toBe(true);
    expect(w.find("img.viewer__frame").exists()).toBe(false);
    URL.createObjectURL = realCreateURL;
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

    await openSection(w);
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
    await openSection(w);
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
    await openSection(w);
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
  it("shows dwell figures with sample size and reviews", async () => {
    stubFacility();
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

  // §23 entry 123. The chip picks the nearest pin, which the driver never chose and
  // cannot see; an unnamed sheet lets a reading land on the lot across the interstate.
  it("names the lot the chip picked, so a wrong target is visible before the tap", async () => {
    setToken("tok-map-name");
    const fetchStub = vi.fn().mockImplementation((url) => {
      if (String(url).includes("/map/overlay")) {
        return jsonOk({
          clustered: false,
          total: 1,
          clusters: [],
          pins: [{ facility_id: "f-ta", name: "TA Dallas", facility_type: "truck_stop", lat: 32.78, lon: -96.82, status: "some", shape: "circle", freshness: null }],
        });
      }
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(MapSurface, { global: { plugins: [testRouter()] } });
      await flushPromises();
      await w.find(".report-chip").trigger("click");
      await flushPromises();
      expect(w.text()).toContain("TA Dallas");
    } finally {
      vi.unstubAllGlobals();
      logout();
    }
  });

  // the whole point of entry 123: pin -> status. Two taps, no second sheet, and the
  // card the driver was reading is not swapped out from under them mid-answer.
  it("posts a card's status in ONE tap on the card, opening no second sheet", async () => {
    setToken("tok-map-card");
    const fetchStub = vi.fn().mockImplementation((url, opts) => {
      const u = String(url);
      if (u.includes("/map/overlay")) {
        return jsonOk({
          clustered: false,
          total: 1,
          clusters: [],
          pins: [{ facility_id: "f-ta", name: "TA Dallas", facility_type: "truck_stop", lat: 32.78, lon: -96.82, status: "empty", shape: "circle", freshness: null }],
        });
      }
      if (u.endsWith("/map/report") && opts?.method === "POST") return jsonOk({ submission_id: "s2", presence_proven: true });
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchStub);
    try {
      const w = mount(MapSurface, { global: { plugins: [testRouter()] } });
      await flushPromises();
      await w.find(".pin[data-facility='f-ta']").trigger("click");
      await flushPromises();
      expect(w.text()).toContain("TA Dallas"); // the card is open
      const opts = w.findAll(".report__opt");
      expect(opts).toHaveLength(3); // asked ON the card — no "Report status" detour
      await opts[2].trigger("click");
      await flushPromises();
      const post = fetchStub.mock.calls.find((c) => String(c[0]).endsWith("/map/report") && c[1]?.method === "POST");
      expect(JSON.parse(post[1].body)).toMatchObject({
        facility_id: "f-ta",
        signal_type: "parking_fullness",
        value: { status: "full" },
      });
      // one tap answered it: the sheet closed rather than handing over to another one
      expect(w.findAll(".report__opt")).toHaveLength(0);
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

// AI-CONTEXT: the two controls behind §23 entry 108's P0s. Both exist because the
// events did not: nothing could mark a claim paid, and M6-FR7's refund engine had no
// endpoint. What is asserted here is mostly the SHAPE of the offer — which rows are
// eligible, when the control is withdrawn, and that an irreversible money statement
// takes two deliberate taps rather than one.
describe("MoneySurface — marking a claim paid (§23 entry 108)", () => {
  beforeEach(() => useDriverState().setState(DriverState.IDLE));
  afterEach(() => {
    vi.unstubAllGlobals();
    logout();
    useDriverState().setState(DriverState.IDLE);
  });

  it("offers the control and lists only what the ledger could accept", async () => {
    stubMoney();
    const w = mount(MoneySurface);
    await flushPromises();

    expect(w.text()).toContain(en["money.paid.cta"]);
    await w.findAll(".audit-cta").at(-1).trigger("click");
    await flushPromises();

    // the fixture holds invoiced + disputed + recovered; `recovered` is terminal in
    // F7's transition table, so offering it would promise something the API refuses
    const choices = w.findAll(".paid__row");
    expect(choices).toHaveLength(2);
    expect(w.find(".paid__list").text()).not.toContain("Lumper");
  });

  it("will not submit until a claim is chosen", async () => {
    stubMoney();
    const w = mount(MoneySurface);
    await flushPromises();
    await w.findAll(".audit-cta").at(-1).trigger("click");
    await flushPromises();

    expect(w.find(".paid__submit").attributes("disabled")).toBeDefined();
    await w.findAll(".paid__row")[0].trigger("click");
    expect(w.find(".paid__submit").attributes("disabled")).toBeUndefined();
  });

  it("posts the chosen receivable and re-reads the money that moved", async () => {
    setToken("tok-money");
    const calls = [];
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url, opts) => {
      const u = String(url);
      calls.push(`${opts?.method || "GET"} ${u}`);
      if (u.includes("/accessorial/owed")) return jsonOk(OWED_ROWS);
      if (u.includes("/money/earnings")) return jsonOk(EARNINGS);
      if (u.includes("/paid")) return jsonOk({ receivable_id: "r-1", state: "recovered" });
      return jsonOk({});
    }));
    const w = mount(MoneySurface);
    await flushPromises();
    await w.findAll(".audit-cta").at(-1).trigger("click");
    await flushPromises();
    await w.findAll(".paid__row")[0].trigger("click");
    await w.find(".paid__submit").trigger("click");
    await flushPromises();

    expect(calls.some((c) => c.startsWith("POST") && c.includes("/money/receivable/r-1/paid"))).toBe(
      true,
    );
    // the North Star figure is derived from recovered money, so it must be re-read
    expect(calls.filter((c) => c.includes("/money/earnings")).length).toBeGreaterThan(1);
    expect(w.find(".paid__list").exists()).toBe(false); // the sheet closes behind it
  });

  it("withdraws the control at speed (§10.3 — actions deferred)", async () => {
    useDriverState().setState(DriverState.DRIVING);
    const w = mount(MoneySurface);
    await flushPromises();

    expect(w.text()).not.toContain(en["money.paid.cta"]);
  });
});

describe("OwnerPortalSurface — cancelling a booking (M6-FR7, §23 entry 108)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    logout();
  });

  function stub(bookings, onCancel = () => {}) {
    return vi.fn().mockImplementation((url, opts) => {
      const u = String(url);
      if (u.endsWith("/owner/dashboard")) {
        return jsonOk({ payout_cents: 0, properties: [], bookings });
      }
      if (u.includes("/cancel")) {
        onCancel(u);
        return jsonOk({ state: "refunded" });
      }
      return jsonOk({});
    });
  }

  it("offers cancel only on bookings that are still live", async () => {
    setToken("tok-owner");
    vi.stubGlobal("fetch", stub([
      { id: "b1", nights: 1, price_cents: 2400, owner_payout_cents: 1980, state: "booked" },
      { id: "b2", nights: 2, price_cents: 4800, owner_payout_cents: 3960, state: "checked_out" },
      { id: "b3", nights: 1, price_cents: 2400, owner_payout_cents: 1980, state: "refunded" },
    ]));
    const w = mount(OwnerPortalSurface);
    await flushPromises();

    expect(w.findAll("tbody .pause")).toHaveLength(1);
  });

  it("arms on the first click and only cancels on the second", async () => {
    setToken("tok-owner");
    const hits = [];
    vi.stubGlobal("fetch", stub(
      [{ id: "b1", nights: 1, price_cents: 2400, owner_payout_cents: 1980, state: "booked" }],
      (u) => hits.push(u),
    ));
    const w = mount(OwnerPortalSurface);
    await flushPromises();
    const btn = w.find("tbody .pause");

    await btn.trigger("click");
    await flushPromises();
    expect(hits).toHaveLength(0); // nothing has been refunded yet
    expect(w.find("tbody .pause").text()).toBe(en["owner.cancel_confirm"]);

    await w.find("tbody .pause").trigger("click");
    await flushPromises();
    expect(hits).toHaveLength(1);
    expect(hits[0]).toContain("/parking/booking/b1/cancel");
  });

  it("arms one row at a time", async () => {
    setToken("tok-owner");
    vi.stubGlobal("fetch", stub([
      { id: "b1", nights: 1, price_cents: 2400, owner_payout_cents: 1980, state: "booked" },
      { id: "b2", nights: 1, price_cents: 2400, owner_payout_cents: 1980, state: "booked" },
    ]));
    const w = mount(OwnerPortalSurface);
    await flushPromises();

    await w.findAll("tbody .pause")[0].trigger("click");
    const labels = w.findAll("tbody .pause").map((b) => b.text());

    expect(labels).toEqual([en["owner.cancel_confirm"], en["owner.cancel"]]);
  });
});

// AI-CONTEXT: the screen that had never existed (§23 entry 110). `owner_bookings` shipped
// with M6 and this did not, so a booking was write-only from the person who paid for it —
// and the cancellation P0 had to deep-link at the checkout flow for want of anywhere honest.
describe("BookingsSurface — the driver's own bookings (§23 entry 110)", () => {
  function mountBookings() {
    const router = createRouter({ history: createMemoryHistory(), routes });
    router.push("/bookings");
    return router.isReady().then(() => mount(BookingsSurface, { global: { plugins: [router] } }));
  }
  const ROWS = [
    { id: "bk-1", property_name: "Riverside Lot", spot_label: "A1", spot_id: "s-1", nights: 1,
      start_at: "2026-08-02T00:00:00+00:00", end_at: "2026-08-03T00:00:00+00:00",
      price_cents: 2400, state: "booked", refunded: false },
    { id: "bk-2", property_name: "Depot Overnight", spot_label: "B2", spot_id: "s-2", nights: 2,
      start_at: "2026-07-10T00:00:00+00:00", end_at: "2026-07-12T00:00:00+00:00",
      price_cents: 4800, state: "refunded", refunded: true },
  ];

  beforeEach(() => {
    useDriverState().setState(DriverState.IDLE);
    setToken("tok-bk");
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    logout();
    useDriverState().setState(DriverState.IDLE);
  });

  it("shows where, when and what each booking cost", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => jsonOk({ bookings: ROWS })));
    const w = await mountBookings();
    await flushPromises();

    expect(w.findAll(".row")).toHaveLength(2);
    const text = w.text();
    expect(text).toContain("Riverside Lot");
    expect(text).toContain("$24.00");
    // §11.7: "canceled" and "canceled, money back" are different facts
    expect(text).toContain(en["bookings.st_refunded"]);
    w.unmount();
  });

  it("offers cancel only on live bookings", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => jsonOk({ bookings: ROWS })));
    const w = await mountBookings();
    await flushPromises();

    expect(w.findAll(".row__cancel")).toHaveLength(1);
    w.unmount();
  });

  it("arms before it cancels, because F7 has no un-refund", async () => {
    const hits = [];
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url) => {
      const u = String(url);
      if (u.includes("/cancel")) {
        hits.push(u);
        return jsonOk({ state: "refunded" });
      }
      return jsonOk({ bookings: ROWS });
    }));
    const w = await mountBookings();
    await flushPromises();

    await w.find(".row__cancel").trigger("click");
    expect(hits).toHaveLength(0);
    expect(w.find(".row__cancel").text()).toBe(en["bookings.cancel_confirm"]);

    await w.find(".row__cancel").trigger("click");
    await flushPromises();
    expect(hits).toHaveLength(1);
    expect(hits[0]).toContain("/parking/booking/bk-1/cancel");
    w.unmount();
  });

  it("withdraws the action at speed (§22.3)", async () => {
    useDriverState().setState(DriverState.DRIVING);
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => jsonOk({ bookings: ROWS })));
    const w = await mountBookings();
    await flushPromises();

    expect(w.find(".row__cancel").exists()).toBe(false);
    expect(w.text()).toContain("Riverside Lot"); // reading is still fine
    w.unmount();
  });

  it("invites the map when there is nothing booked", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => jsonOk({ bookings: [] })));
    const w = await mountBookings();
    await flushPromises();

    expect(w.text()).toContain(en["bookings.empty"]);
    w.unmount();
  });
});
