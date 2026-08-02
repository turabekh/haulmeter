// AI-CONTEXT: M13 driver-UI laws as tests (design-prd §22.3 DoD).
//
// What these defend, in order of how much it would cost to get wrong:
// · §11.7 — a vendor's own claim can never render as a driver count.
// · Q-7 — nothing to show renders NOTHING (no filler on a 360 dp card).
// · Q-6 — two vendors on a card, three on a corridor.
// · Forbidden #11 / §13.4 — no interactive prompt while DRIVING.
// · §6 — tokens only; no hardcoded colour or size reaches the screen.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import FacilityCard from "../src/core/components/FacilityCard.vue";
import VendorSheet from "../src/core/components/VendorSheet.vue";
import CorridorStack from "../src/core/components/CorridorStack.vue";
import PresetChips from "../src/core/components/PresetChips.vue";
import MapCanvas from "../src/core/components/MapCanvas.vue";
import { routes, installAuthGuard } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import { useDriverState, DriverState } from "../src/core/state.js";
import {
  cardVendors,
  corridorVendors,
  presenceLabel,
  priceLabel,
  verificationPresentation,
  withFoodBadges,
  MAX_VENDORS_PER_CARD,
  MAX_CORRIDOR_VENDORS,
} from "../src/core/vendors.js";

const NOW = Date.parse("2026-07-25T18:00:00Z");

function entry(overrides = {}) {
  return {
    vendor_id: overrides.vendor_id ?? "v-1",
    name: overrides.name ?? "Osh Express",
    verify_status: overrides.verify_status ?? "unverified",
    facility_id: overrides.facility_id ?? "f-1",
    starts_at: "2026-07-25T17:00:00Z",
    ends_at: "2026-07-25T21:00:00Z",
    bucket: overrides.bucket ?? 1,
    distance_m: overrides.distance_m ?? 12000,
    sold_out: overrides.sold_out ?? false,
    offerings: overrides.offerings ?? [{ name: "Osh", price_cents: 1200, portions: 40 }],
    presence: overrides.presence ?? null,
    languages: ["uz", "ru"],
    ...overrides,
  };
}

const PIN = {
  facility_id: "f-1",
  name: "Love's #212",
  facility_type: "truck_stop",
  lat: 32.7,
  lon: -96.8,
  status: "some",
  badges: [],
  freshness: null,
};

function testRouter() {
  return createRouter({ history: createMemoryHistory(), routes });
}

// --- §11.7: the honesty split ---
describe("presence honesty (design-prd §11.7)", () => {
  it("renders a crowd confirmation as a driver count", () => {
    const label = presenceLabel(
      { present: true, source: "crowd", sample_size: 3, reported_at: "2026-07-25T17:40:00Z" },
      NOW,
    );
    expect(label).toBe("20m · 3 drivers");
  });

  it("NEVER renders a vendor's own claim as a driver count", () => {
    const label = presenceLabel(
      // note the sample_size: even with rows behind it, this is not a driver count
      { present: true, source: "vendor", sample_size: 1, reported_at: "2026-07-25T17:40:00Z" },
      NOW,
      { vendorSays: "vendor says here" },
    );
    expect(label).toBe("20m · vendor says here");
    expect(label).not.toMatch(/driver/);
  });

  it("says nothing at all when nobody has confirmed", () => {
    expect(presenceLabel(null, NOW)).toBeNull();
    expect(presenceLabel({ present: false, source: "crowd" }, NOW)).toBeNull();
  });
});

describe("verification tiers (§16 C-1)", () => {
  it("gives every tier a label, never colour alone", () => {
    for (const status of ["verified", "documents_on_file", "unverified"]) {
      expect(verificationPresentation(status).labelKey).toBeTruthy();
    }
  });

  it("keeps 'license on file' visually neutral — paperwork is not an endorsement", () => {
    expect(verificationPresentation("documents_on_file").token).toBe("--text-2");
    expect(verificationPresentation("verified").token).toBe("--ledger-500");
  });

  it("falls back to unverified for an unknown status rather than overclaiming", () => {
    expect(verificationPresentation("something_new").labelKey).toBe("vendor.unverified");
  });
});

// --- Q-6: the noise budget ---
describe("driver-side noise budget (Q-6)", () => {
  it("caps the card at two vendors and the corridor at three", () => {
    const many = Array.from({ length: 6 }, (_, i) => entry({ vendor_id: `v-${i}` }));
    expect(cardVendors(many)).toHaveLength(MAX_VENDORS_PER_CARD);
    expect(corridorVendors(many)).toHaveLength(MAX_CORRIDOR_VENDORS);
  });

  it("degrades to empty rather than breaking on a malformed response", () => {
    // the map outranks the food layer: bad data means no food, never a broken map
    expect(cardVendors(undefined)).toEqual([]);
    expect(withFoodBadges(undefined, undefined)).toEqual([]);
  });
});

describe("food badge (§11.1 / §11.2)", () => {
  it("rides an existing pin instead of adding one", () => {
    const pins = withFoodBadges([PIN, { ...PIN, facility_id: "f-2" }], [entry()]);
    expect(pins).toHaveLength(2); // no new pin
    expect(pins[0].has_food).toBe(true);
    expect(pins[1].has_food).toBeUndefined();
  });

  it("renders the badge on the pin's puck", () => {
    const w = mount(MapCanvas, { props: { pins: [{ ...PIN, has_food: true }], clusters: [] } });
    expect(w.find(".pin__badge").exists()).toBe(true);
  });

  it("shows no badge on a facility with no vendors", () => {
    const w = mount(MapCanvas, { props: { pins: [PIN], clusters: [] } });
    expect(w.find(".pin__badge").exists()).toBe(false);
  });
});

// --- Q-7: clean empty states ---
describe("facility card vendor section (Q-6 / Q-7)", () => {
  it("does not render the section at all when there is no food", async () => {
    const w = mount(FacilityCard, {
      props: { pin: PIN, vendors: [] },
      global: { plugins: [testRouter()] },
    });
    expect(w.find(".fac__vendors").exists()).toBe(false);
    expect(w.text()).not.toMatch(/food/i); // no filler, no "nothing here yet"
  });

  it("shows at most two vendors and offers the rest behind 'all vendors'", async () => {
    const many = Array.from({ length: 4 }, (_, i) =>
      entry({ vendor_id: `v-${i}`, name: `Cook ${i}` }),
    );
    const w = mount(FacilityCard, {
      props: { pin: PIN, vendors: many },
      global: { plugins: [testRouter()] },
    });
    expect(w.findAll(".vendor")).toHaveLength(2);
    expect(w.text()).toContain("All vendors (4)");
  });

  it("emits the tapped vendor so the sheet can open", async () => {
    const w = mount(FacilityCard, {
      props: { pin: PIN, vendors: [entry()] },
      global: { plugins: [testRouter()] },
    });
    await w.find(".vendor").trigger("click");
    expect(w.emitted().vendor[0][0].vendor_id).toBe("v-1");
  });

  it("marks a sold-out vendor without hiding it", async () => {
    const w = mount(FacilityCard, {
      props: { pin: PIN, vendors: [entry({ sold_out: true })] },
      global: { plugins: [testRouter()] },
    });
    expect(w.find(".vendor__soldout").exists()).toBe(true);
  });

  it("keeps the facility's own primary action unchanged", async () => {
    // food must never displace the reason the card exists (§Principle 4)
    const w = mount(FacilityCard, {
      props: { pin: PIN, vendors: [entry()] },
      global: { plugins: [testRouter()] },
    });
    expect(w.find(".cta").text()).toContain("Navigate");
  });
});

// --- the sheet ---
describe("VendorSheet", () => {
  const sheet = {
    vendor_id: "v-1",
    name: "Osh Express",
    verify_status: "documents_on_file",
    languages: ["uz", "ru"],
    halal_disclosure: "Halal butcher in Orlando",
    shows_up: { confirmed: 19, published: 20 },
    appearances: [entry()],
  };

  beforeEach(() => {
    useDriverState().setState(DriverState.IDLE);
  });
  afterEach(() => {
    useDriverState().setState(DriverState.IDLE);
  });

  it("shows reliability as a raw pair, never a percentage", () => {
    const w = mount(VendorSheet, { props: { sheet } });
    expect(w.text()).toContain("19");
    expect(w.text()).toContain("20");
    expect(w.text()).not.toMatch(/%/);
  });

  it("prints the vendor's halal disclosure verbatim", () => {
    const w = mount(VendorSheet, { props: { sheet } });
    expect(w.text()).toContain("Halal butcher in Orlando");
  });

  it("says plainly when no halal claim was made", () => {
    const w = mount(VendorSheet, { props: { sheet: { ...sheet, halal_disclosure: null } } });
    expect(w.text()).toContain("No halal claim made");
  });

  it("offers confirm / not-here / sold-out while stopped", async () => {
    const w = mount(VendorSheet, { props: { sheet } });
    await w.findAll(".cta")[0].trigger("click");
    expect(w.emitted().confirm).toBeTruthy();
    expect(w.findAll(".cta").length).toBeGreaterThanOrEqual(4);
  });

  it("renders NO interactive prompt while DRIVING (Forbidden #11)", () => {
    useDriverState().setState(DriverState.DRIVING);
    const w = mount(VendorSheet, { props: { sheet } });
    expect(w.findAll(".cta")).toHaveLength(0);
    // the information is still readable at a glance — only the taps are gone
    expect(w.text()).toContain("Osh Express");
  });

  it("shows prices as Mono money figures", () => {
    expect(priceLabel(1200)).toBe("$12.00");
    const w = mount(VendorSheet, { props: { sheet } });
    expect(w.find(".vs__price").text()).toBe("$12.00");
  });
});

// --- corridor ---
describe("CorridorStack food lines (§11.4 / Q-6)", () => {
  it("lists at most three vendors ahead", () => {
    const many = Array.from({ length: 5 }, (_, i) =>
      entry({ vendor_id: `v-${i}`, name: `Cook ${i}` }),
    );
    const w = mount(CorridorStack, { props: { entries: [], vendors: many } });
    expect(w.findAll(".corridor__card--food")).toHaveLength(3);
  });

  it("renders food lines as read-only text, with no tap target", () => {
    const w = mount(CorridorStack, { props: { entries: [], vendors: [entry()] } });
    const line = w.find(".corridor__card--food");
    expect(line.find("button").exists()).toBe(false);
  });

  it("renders nothing when no vendor is ahead", () => {
    const w = mount(CorridorStack, { props: { entries: [], vendors: [] } });
    expect(w.findAll(".corridor__card--food")).toHaveLength(0);
  });
});

// --- the preset chip ---
describe("Food preset chip (§23 E-D2)", () => {
  it("joins the preset row and emits its key", async () => {
    const w = mount(PresetChips, { props: { modelValue: "drive", available: ["drive", "tonight", "work", "fuel", "food", "service"] } });
    const chips = w.findAll(".chip");
    await chips[4].trigger("click");
    expect(w.emitted()["update:modelValue"][0]).toEqual(["food"]);
  });

  it("reuses the existing chip class — no new visual pattern", () => {
    const w = mount(PresetChips, { props: { modelValue: "food", available: ["drive", "tonight", "work", "fuel", "food", "service"] } });
    const food = w.findAll(".chip")[4];
    expect(food.classes()).toContain("chip");
    expect(food.classes()).toContain("chip--active");
  });
});

// --- Session B: promoted slots, reviews, reporting, the portal ---
import VendorPortalShell from "../src/surfaces/vendor/VendorPortalShell.vue";
import VendorOverview from "../src/surfaces/vendor/VendorOverview.vue";
import { splitPromoted, reviewSummary, reasonLabelKey, REPORT_REASONS } from "../src/core/vendors.js";

const PROMO = {
  promotion_id: "p-1",
  vendor_id: "v-1",
  vendor_name: "Osh Express",
  text: "Free chai with any plate",
  promoted: true,
};

describe("promoted slots (FR6 / Q-3)", () => {
  it("keeps organic and promoted apart — there is no combined array to render", () => {
    const split = splitPromoted([entry()], [PROMO]);
    expect(split.organic).toHaveLength(1);
    expect(split.promoted).toHaveLength(1);
    // the helper deliberately returns two keys; a caller that wants one list has
    // to concatenate deliberately rather than by habit
    expect(Array.isArray(split)).toBe(false);
  });

  it("renders a promotion in a labelled container on the facility card", () => {
    const w = mount(FacilityCard, {
      props: { pin: PIN, vendors: [entry()], promotions: [PROMO] },
      global: { plugins: [testRouter()] },
    });
    const slot = w.find(".promo");
    expect(slot.exists()).toBe(true);
    expect(slot.find(".promo__label").text()).toBe("Promoted");
    expect(slot.text()).toContain("Free chai with any plate");
  });

  it("never renders a promotion inside the ranked vendor rows", () => {
    const w = mount(FacilityCard, {
      props: { pin: PIN, vendors: [entry()], promotions: [PROMO] },
      global: { plugins: [testRouter()] },
    });
    for (const row of w.findAll(".vendor")) {
      expect(row.text()).not.toContain("Free chai");
    }
  });

  it("renders no slot at all when nothing is promoted", () => {
    const w = mount(FacilityCard, {
      props: { pin: PIN, vendors: [entry()], promotions: [] },
      global: { plugins: [testRouter()] },
    });
    expect(w.find(".promo").exists()).toBe(false);
  });

  it("labels the promotion on the vendor sheet too", () => {
    const w = mount(VendorSheet, {
      props: {
        sheet: {
          name: "Osh Express",
          verify_status: "unverified",
          appearances: [entry()],
          promotions: [{ promotion_id: "p-1", text: "Two somsa for $6", promoted: true }],
        },
      },
    });
    expect(w.find(".vs__promo-label").text()).toBe("Promoted");
  });
});

describe("reviews on the sheet (FR5 / §11.7)", () => {
  const reviewed = {
    name: "Osh Express",
    verify_status: "verified",
    appearances: [entry()],
    reviews: {
      average: 4.5,
      reviewers: 12,
      items: [{ rating: 5, text: "Best osh on I-35", created_at: "2026-07-26T12:00:00Z" }],
    },
    can_review: true,
  };

  beforeEach(() => useDriverState().setState(DriverState.IDLE));

  it("always shows the reviewer count beside the average", () => {
    // an average with no denominator invites overreading a handful of opinions
    const w = mount(VendorSheet, { props: { sheet: reviewed } });
    expect(w.text()).toContain("4.5");
    expect(w.text()).toContain("12 drivers");
  });

  it("says plainly when there are no reviews rather than showing a zero", () => {
    const w = mount(VendorSheet, {
      props: { sheet: { ...reviewed, reviews: { average: null, reviewers: 0, items: [] } } },
    });
    expect(w.text()).toContain("No reviews yet");
    expect(w.text()).not.toContain("0.0");
  });

  it("emits a rating the driver picked", async () => {
    const w = mount(VendorSheet, { props: { sheet: reviewed } });
    await w.findAll(".vs__star")[4].trigger("click");
    await w.find(".vs__rate .cta").trigger("click");
    expect(w.emitted().review[0][0].rating).toBe(5);
  });

  it("will not send a review with no rating", async () => {
    const w = mount(VendorSheet, { props: { sheet: reviewed } });
    expect(w.find(".vs__rate .cta").attributes("disabled")).toBeDefined();
  });

  it("explains the wait instead of offering a form the server would reject", () => {
    const w = mount(VendorSheet, { props: { sheet: { ...reviewed, can_review: false } } });
    expect(w.find(".vs__rate").exists()).toBe(false);
    expect(w.text()).toContain("review again in a week");
  });

  it("hides the review form while DRIVING", () => {
    useDriverState().setState(DriverState.DRIVING);
    const w = mount(VendorSheet, { props: { sheet: reviewed } });
    expect(w.find(".vs__rate").exists()).toBe(false);
    // the reviews themselves stay readable at a glance
    expect(w.text()).toContain("12 drivers");
    useDriverState().setState(DriverState.IDLE);
  });

  it("summarises nothing when there are no reviewers", () => {
    expect(reviewSummary({ average: null, reviewers: 0 })).toBeNull();
    expect(reviewSummary(undefined)).toBeNull();
  });
});

describe("report affordance (Q-8)", () => {
  const sheet = { name: "Osh Express", verify_status: "unverified", appearances: [entry()] };

  beforeEach(() => useDriverState().setState(DriverState.IDLE));

  it("offers every reason a driver may pick", async () => {
    const w = mount(VendorSheet, { props: { sheet } });
    const reportButton = w.findAll(".cta--tertiary").at(-1);
    await reportButton.trigger("click");
    expect(w.findAll(".vs__reason")).toHaveLength(REPORT_REASONS.length);
  });

  it("includes the false-attestation reason Q11 depends on", () => {
    // the ranking boost a self-attestation earns is only defensible because a
    // driver can say "he isn't allowed to be here"
    expect(REPORT_REASONS).toContain("false_property_attestation");
    expect(reasonLabelKey("false_property_attestation")).toBe(
      "vendor.reason.false_property_attestation",
    );
  });

  it("emits the chosen reason and closes the list", async () => {
    const w = mount(VendorSheet, { props: { sheet } });
    await w.findAll(".cta--tertiary").at(-1).trigger("click");
    await w.findAll(".vs__reason")[1].trigger("click");
    expect(w.emitted().report[0][0]).toBe("offensive");
    expect(w.findAll(".vs__reason")).toHaveLength(0);
  });

  it("is not reachable while DRIVING", () => {
    useDriverState().setState(DriverState.DRIVING);
    const w = mount(VendorSheet, { props: { sheet } });
    expect(w.findAll(".cta--tertiary")).toHaveLength(0);
    useDriverState().setState(DriverState.IDLE);
  });

  it("falls back to 'other' for an unknown reason rather than showing a raw token", () => {
    expect(reasonLabelKey("nonsense")).toBe("vendor.reason.other");
  });
});

describe("Vendor portal shell (§18 fourth portal)", () => {
  const PROFILE = {
    vendor_id: "v-1",
    name: "Osh Express",
    verify_status: "documents_on_file",
    languages: ["uz", "ru"],
    halal_disclosure: "Halal butcher",
    publish_suspended: false,
    consecutive_no_shows: 0,
    profile_gaps: [],
    documents: [],
    assisted: [],
  };
  const ANALYTICS = {
    sheet_views: 42,
    confirmations: 7,
    shows_up: { confirmed: 19, published: 20 },
    reviews: { average: 4.5, reviewers: 12 },
    publish_suspended: false,
  };

  function mockPortal(overrides = {}) {
    const data = {
      "/vendor/profile": PROFILE,
      "/vendor/appearances": [],
      "/vendor/promotions": [],
      "/vendor/analytics": ANALYTICS,
      "/vendor/menu": [],
      ...overrides,
    };
    global.fetch = vi.fn((url) => {
      const path = String(url).replace("http://localhost:8008", "").split("?")[0];
      return Promise.resolve({
        ok: path in data,
        status: path in data ? 200 : 404,
        json: () => Promise.resolve(data[path] ?? {}),
      });
    });
  }

  function mountShell() {
    return mount(VendorPortalShell, {
      global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] },
    });
  }

  beforeEach(() => setToken("portal-token"));
  afterEach(() => {
    logout();
    vi.restoreAllMocks();
  });

  // the shell carries what a cook must not have to go looking for
  it("states a suspension plainly, wherever they are standing", async () => {
    mockPortal({ "/vendor/profile": { ...PROFILE, publish_suspended: true } });
    const w = mountShell();
    await flushPromises();
    expect(w.find(".portal__alert").exists()).toBe(true);
    expect(w.text()).toContain("Publishing is paused");
  });

  it("names exactly what still blocks publishing", async () => {
    mockPortal({
      "/vendor/profile": { ...PROFILE, profile_gaps: ["languages", "halal_disclosure"] },
    });
    const w = mountShell();
    await flushPromises();
    expect(w.find(".portal__gaps").exists()).toBe(true);
  });

  it("explains itself to someone who is not a vendor", async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 404, json: () => ({}) }));
    const w = mountShell();
    await flushPromises();
    expect(w.text()).toContain("vendor portal");
  });

  it("offers every section on the rail", async () => {
    mockPortal();
    const w = mountShell();
    await flushPromises();
    const labels = w.findAll(".rail__item").map((a) => a.text());
    expect(labels).toHaveLength(6);
    expect(labels).toContain("My week");
    expect(labels).toContain("Menu & prices");
  });

  // the overview carries the figures, and they are the DRIVER's figures
  it("shows the same show-up pair a driver sees — no vanity variant", async () => {
    mockPortal();
    const w = mount(VendorOverview, {
      global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] },
    });
    await flushPromises();
    // 19 / 20 is exactly what VendorSheet renders for the same vendor
    expect(w.text()).toMatch(/19\s*\/\s*20/);
    expect(w.text()).not.toMatch(/95%/);
  });

  it("shows a quiet empty state rather than a blank panel", async () => {
    mockPortal();
    const w = mount(VendorOverview, {
      global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] },
    });
    await flushPromises();
    expect(w.text()).toContain("Nothing scheduled yet.");
  });

  it("is a portal route, not a driver-app tab", () => {
    // the sections are children now, so the portal meta lives on the parent
    const route = routes.find((r) => r.path === "/vendor-portal");
    expect(route.meta.portal).toBe(true);
    expect(route.meta.chrome).toBe(false);
    expect(route.children.map((c) => c.name)).toContain("vendor-portal");
  });

  it("has a PUBLIC way in, because a cook without an account cannot be behind the gate", () => {
    const join = routes.find((r) => r.name === "vendor-join");
    expect(join.meta.public).toBe(true);
    expect(join.meta.portal).toBe(true);
  });

  it("sends an unauthenticated visitor to the portal's own door, not the driver login", () => {
    // the driver login is mobile-first, asks for an authority number, and lands on
    // the trucking map afterwards — all three are wrong for a cook
    const router = { beforeEach: (fn) => (router._guard = fn) };
    installAuthGuard(router);
    logout();
    expect(router._guard({ path: "/vendor-portal/menu", meta: {}, query: {} })).toEqual({
      name: "vendor-join",
    });
  });

  it("brings everyone else back where they were going after the driver login", () => {
    const router = { beforeEach: (fn) => (router._guard = fn) };
    installAuthGuard(router);
    logout();
    expect(
      router._guard({ path: "/money", fullPath: "/money", meta: {}, query: {} }),
    ).toEqual({ name: "login", query: { next: "/money" } });
  });
});
