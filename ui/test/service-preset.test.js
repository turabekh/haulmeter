// AI-CONTEXT: A5 — the Service preset chip and the call/hours/services rows on the
// facility card. Drivers asked for repair shops, tire shops and "other entities that
// may help" on the map, and for a way to reach them.
//
// The card rows are guarded harder than they look. A call button that renders when
// there is no number is worse than no button: a driver taps it while broken down and
// nothing happens. 28 of the 45 repair facilities in the registry have no phone, so
// the absent case is the COMMON one, not the edge.
import { describe, it, expect, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import PresetChips from "../src/core/components/PresetChips.vue";
import FacilityCard from "../src/core/components/FacilityCard.vue";
import MapSurface from "../src/surfaces/MapSurface.vue";
import { routes } from "../src/router.js";
import en from "../src/core/i18n/en.json";
import es from "../src/core/i18n/es.json";
import ru from "../src/core/i18n/ru.json";
import uz from "../src/core/i18n/uz.json";
import pa from "../src/core/i18n/pa.json";
import so from "../src/core/i18n/so.json";

const LOCALES = { en, es, ru, uz, pa, so };
import { setToken, logout } from "../src/core/api.js";
import { observeMotion, __resetStateForTests, DRIVING_SUSTAIN_MS } from "../src/core/state.js";

function jsonOk(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function router() {
  return createRouter({ history: createMemoryHistory(), routes });
}

const SHOP = {
  facility_id: "f-1",
  name: "Portage Diesel Repair",
  facility_type: "repair",
  services: ["truck_repair", "tire"],
  phone: "+1-608-555-0199",
  opening_hours: "Mo-Fr 07:00-18:00",
  badges: [],
};

function card(pin = {}, extra = {}) {
  return mount(FacilityCard, {
    props: { pin: { ...SHOP, ...pin }, ...extra },
    global: { plugins: [router()] },
  });
}

// the REAL state machine, not a prop — a card that took `driving` from its parent
// would prove only that the parent passes it, and §22.3 asks what the SCREEN does.
function drive() {
  const t = 1_800_000_000_000;
  observeMotion({ speedMps: 25, now: t });
  observeMotion({ speedMps: 25, now: t + DRIVING_SUSTAIN_MS });
}

afterEach(() => __resetStateForTests());

describe("Service preset chip (A5, §11.3)", () => {
  it("joins the row as a sixth filter chip, not a sixth tab", () => {
    // NAV-1 fixes FIVE TABS and is untouched here — §23's Food-chip precedent
    // established that a preset chip is a filter row. The row already scrolls.
    const w = mount(PresetChips, { props: { modelValue: "drive", available: ["drive", "tonight", "work", "fuel", "food", "service"] } });
    const chips = w.findAll(".chip");
    expect(chips).toHaveLength(6);
  });

  it("keeps its translated name reachable for a screen reader", () => {
    // §23 entry 89: the glyphs are anonymous to assistive tech unless the name moves
    // to aria-label. Six locales keep working because the icon needs no translation.
    const w = mount(PresetChips, { props: { modelValue: "service", available: ["drive", "tonight", "work", "fuel", "food", "service"] } });
    const chip = w.findAll(".chip")[5];
    expect(chip.attributes("aria-label")).toBe(en["map.preset.service"]);
    expect(chip.attributes("aria-selected")).toBe("true");
  });

  it("emits the preset key when tapped", async () => {
    const w = mount(PresetChips, { props: { modelValue: "drive", available: ["drive", "tonight", "work", "fuel", "food", "service"] } });
    await w.findAll(".chip")[5].trigger("click");
    expect(w.emitted()["update:modelValue"][0]).toEqual(["service"]);
  });
});

describe("Facility card — reaching the shop (A5 req 3)", () => {
  it("offers a call that dials the number the pin carries", () => {
    const link = card({}).find(".fac__call");
    expect(link.exists()).toBe(true);
    expect(link.attributes("href")).toBe("tel:+1-608-555-0199");
  });

  it("does not render a call action when there is no number", () => {
    // the common case: 28 of the 45 repair facilities have no phone. A dead button
    // is worse than an absent one for someone standing beside a broken truck.
    expect(card({ phone: null }).find(".fac__call").exists()).toBe(false);
  });

  it("lists what the shop actually does, in the driver's language", () => {
    const text = card({}).find(".fac__services").text();
    expect(text).toContain(en["facility.service.truck_repair"]);
    expect(text).toContain(en["facility.service.tire"]);
  });

  it("says nothing about services when the site has none", () => {
    // §15.3 / Q-7: an empty section is filler on a card read in ten seconds
    expect(card({ services: [] }).find(".fac__services").exists()).toBe(false);
  });

  it("shows hours verbatim and only when they exist", () => {
    expect(card({}).find(".fac__hours").text()).toContain("Mo-Fr 07:00-18:00");
    expect(card({ opening_hours: null }).find(".fac__hours").exists()).toBe(false);
  });

  it("records the tap, so the requirement can be validated at all", async () => {
    // v2.0 §2: done is an observation in the database. A bare tel: link leaves none,
    // and A5 would have shipped complete and unvalidatable.
    const w = card();
    await w.find(".fac__call").trigger("click");
    expect(w.emitted()["call-tapped"][0][0].facility_id).toBe("f-1");
  });

  it("never offers to dial while the truck is moving", () => {
    // §21.11 forbids interactive prompts while DRIVING and §11.4 makes corridor taps
    // deferred-safe. Placing a call at 65 mph is the most interactive thing on this
    // card, so it becomes save-for-stop rather than a dial.
    drive();
    const w = card();
    expect(w.find(".fac__call").exists()).toBe(false);
    expect(w.find(".fac__call-later").exists()).toBe(true);
  });
});

// AI-CONTEXT: the surface-level wiring, and it exists because the unit tests above
// were ALL GREEN while `recordServiceCall` was used in MapSurface and never imported.
// A missing import in a .vue file is a runtime ReferenceError that fires the first
// time a driver taps Call — and nothing in this project would have caught it: there
// is no ESLint on the UI at all, so `make lint` is Python-only.
//
// A component test proves the card EMITS. Only a surface test proves anything listens.
describe("MapSurface — the tap reaches the server (A5 validation)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    logout();
  });

  it("posts the call tap for the facility whose card is open", async () => {
    setToken("tok-a05");
    const stub = vi.fn((url) => {
      const u = String(url);
      if (u.includes("/map/overlay")) {
        return jsonOk({
          clustered: false,
          total: 1,
          clusters: [],
          pins: [
            {
              facility_id: "f-shop",
              name: "Portage Diesel Repair",
              facility_type: "repair",
              shape: "circle",
              lat: 43.5,
              lon: -89.4,
              status: null,
              services: ["truck_repair"],
              phone: "+1-608-742-3039",
              opening_hours: null,
              badges: [],
              freshness: null,
            },
          ],
        });
      }
      return jsonOk({});
    });
    vi.stubGlobal("fetch", stub);

    const w = mount(MapSurface, { global: { plugins: [router()] } });
    await flushPromises();
    await w.find(".pin").trigger("click");
    await flushPromises();
    await w.find(".fac__call").trigger("click");
    await flushPromises();

    const post = stub.mock.calls.find(
      (c) => String(c[0]).includes("/map/facility/f-shop/called") && c[1]?.method === "POST",
    );
    expect(post).toBeTruthy();
  });
});

// AI-CONTEXT: A6 — a CLAIMED shop's own details, and saying so.
//
// The server prefers the claimed phone/hours/services over the ingested ones, so the
// rows themselves need no new logic. What the card owes the driver is attribution:
// §11.7 forbids rendering a business's own claim as the platform's finding, which is
// the same rule that stops a vendor's word being counted as "N drivers".
describe("A6 — a claimed service centre on the card", () => {
  it("names the business whose details these are", () => {
    const w = card({ claimed_by: { name: "Portage Diesel Repair", verify_status: "verified" } });
    const line = w.find(".fac__claimed");
    expect(line.exists()).toBe(true);
    expect(line.text()).toContain("Portage Diesel Repair");
  });

  it("says nothing at all for an unclaimed facility", () => {
    // absent, not empty (§15.3): most facilities are unclaimed and a dangling
    // "claimed by —" would be noise on every card a driver opens
    expect(card().find(".fac__claimed").exists()).toBe(false);
  });

  it("still renders the call action for a claimed shop", () => {
    // the attribution line must not displace the one action the card exists for
    const w = card({
      phone: "+1-417-555-1212",
      claimed_by: { name: "Gateway Truck Service", verify_status: "documents_on_file" },
    });
    expect(w.find(".fac__call").attributes("href")).toBe("tel:+1-417-555-1212");
  });

  it("carries no untranslated key in any launch locale", () => {
    // §12: six locales, no English fallback reaching a driver
    for (const loc of ["en", "es", "ru", "uz", "pa", "so"]) {
      const catalog = LOCALES[loc];
      expect(catalog["facility.claimed_by"], `${loc} missing facility.claimed_by`).toBeTruthy();
      expect(catalog["facility.claimed_by"]).toContain("{name}");
    }
  });
});

// AI-CONTEXT: a chip is only on the row when its feature is LIVE.
//
// The row was a hardcoded array, so it offered Food after v2.0 §4 deferred it — and
// `preset=food` answered 500, which MapSurface's own catch absorbed into the offline
// path. It looked empty rather than broken, for weeks, on the owner's own screen.
//
// §21.3: a control that leads nowhere is decoration. §23 entry 415 made a vendor-portal
// rail item conditional on the same reasoning.
describe("preset chips follow their feature (v2.0 §4 / §21.3)", () => {
  const keyOf = (w) => w.findAll(".chip").map((c) => c.attributes("aria-label"));

  it("drops the Food chip when the food half is switched off", () => {
    const w = mount(PresetChips, {
      props: { modelValue: "drive", available: ["drive", "tonight", "work", "fuel", "service"] },
    });
    expect(keyOf(w)).not.toContain(en["map.preset.food"]);
    expect(keyOf(w)).toContain(en["map.preset.service"]);
    expect(w.findAll(".chip")).toHaveLength(5);
  });

  it("drops the Service chip when A5's flag is off, by the same rule", () => {
    // the mechanism is not a special case for food — it is per capability
    const w = mount(PresetChips, {
      props: { modelValue: "drive", available: ["drive", "tonight", "work", "fuel"] },
    });
    expect(keyOf(w)).not.toContain(en["map.preset.service"]);
    expect(w.findAll(".chip")).toHaveLength(4);
  });

  it("shows only the four that cannot be wrong while the answer is unknown", () => {
    // offline, or the first paint before /map/presets lands. Absent beats a chip that
    // answers nothing — the failure mode that produced this whole defect.
    const w = mount(PresetChips, { props: { modelValue: "drive" } });
    expect(w.findAll(".chip")).toHaveLength(4);
    expect(keyOf(w)).not.toContain(en["map.preset.food"]);
  });

  it("never drops a chip the four §11.3 originals depend on", () => {
    // no map, no chip row — so these are never in question and must never be filtered
    const w = mount(PresetChips, { props: { modelValue: "drive", available: [] } });
    expect(keyOf(w)).toEqual([
      en["map.preset.drive"], en["map.preset.tonight"],
      en["map.preset.work"], en["map.preset.fuel"],
    ]);
  });
});
