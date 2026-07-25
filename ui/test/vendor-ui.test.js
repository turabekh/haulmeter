// AI-CONTEXT: M13 driver-UI laws as tests (design-prd §22.3 DoD).
//
// What these defend, in order of how much it would cost to get wrong:
// · §11.7 — a vendor's own claim can never render as a driver count.
// · Q-7 — nothing to show renders NOTHING (no filler on a 360 dp card).
// · Q-6 — two vendors on a card, three on a corridor.
// · Forbidden #11 / §13.4 — no interactive prompt while DRIVING.
// · §6 — tokens only; no hardcoded colour or size reaches the screen.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import FacilityCard from "../src/core/components/FacilityCard.vue";
import VendorSheet from "../src/core/components/VendorSheet.vue";
import CorridorStack from "../src/core/components/CorridorStack.vue";
import PresetChips from "../src/core/components/PresetChips.vue";
import MapCanvas from "../src/core/components/MapCanvas.vue";
import { routes } from "../src/router.js";
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
    const w = mount(PresetChips, { props: { modelValue: "drive" } });
    const chips = w.findAll(".chip");
    await chips[4].trigger("click");
    expect(w.emitted()["update:modelValue"][0]).toEqual(["food"]);
  });

  it("reuses the existing chip class — no new visual pattern", () => {
    const w = mount(PresetChips, { props: { modelValue: "food" } });
    const food = w.findAll(".chip")[4];
    expect(food.classes()).toContain("chip");
    expect(food.classes()).toContain("chip--active");
  });
});
