// AI-CONTEXT: the vendor portal's own laws as tests (design-prd §18, §22.3 DoD).
//
// What these defend, in order of how much it would cost to get wrong:
// · The Q-4 floor renders as NAMED fields. A refused publish that says "something
//   went wrong" defeats the entire point of having a floor.
// · The menu says out loud that editing a price changes what is advertised NEXT.
//   Without that sentence a cook assumes one of the two wrong things.
// · Verification never oversells. `documents_on_file` is paperwork received, and an
//   upload reads "pending" — this screen's reader is the person who would most like
//   those to mean more.
// · Reputation carries the driver's figures, not a flattering variant.
// · PHASE A: no order, no checkout, no payment anywhere in the portal.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import VendorWeek from "../src/surfaces/vendor/VendorWeek.vue";
import VendorMenu from "../src/surfaces/vendor/VendorMenu.vue";
import VendorPromotions from "../src/surfaces/vendor/VendorPromotions.vue";
import VendorVerification from "../src/surfaces/vendor/VendorVerification.vue";
import VendorReputation from "../src/surfaces/vendor/VendorReputation.vue";
import VendorJoinSurface from "../src/surfaces/vendor/VendorJoinSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const router = () => createRouter({ history: createMemoryHistory(), routes });
const withRouter = (Comp, props) =>
  mount(Comp, { props, global: { plugins: [router()] } });

let calls;

function stub(routeMap) {
  calls = [];
  global.fetch = vi.fn((url, opts) => {
    const path = String(url).replace("http://localhost:8008", "").split("?")[0];
    const key = opts?.method ? `${opts.method} ${path}` : path;
    calls.push({ path, key, body: opts?.body ? JSON.parse(opts.body) : null });
    const hit = key in routeMap ? routeMap[key] : routeMap[path];
    if (hit && hit.__status) {
      return Promise.resolve({
        ok: false,
        status: hit.__status,
        json: () => Promise.resolve({ detail: hit.detail }),
      });
    }
    return Promise.resolve({
      ok: hit !== undefined,
      status: hit !== undefined ? 200 : 404,
      json: () => Promise.resolve(hit ?? {}),
    });
  });
}

beforeEach(() => setToken("portal-token"));
afterEach(() => {
  logout();
  vi.restoreAllMocks();
});

// --- the publish form that did not exist ---
describe("Publishing an appearance (M13-FR8)", () => {
  const MENU = [
    { item_id: "m-1", name: "Tamales", price_cents: 1200, portions: 40, is_active: true },
  ];

  it("offers the button at all — the portal could only cancel before", async () => {
    stub({ "/vendor/appearances": [], "/vendor/menu": MENU });
    const w = withRouter(VendorWeek);
    await flushPromises();
    expect(w.text()).toContain(en["vendor.add_appearance"]);
  });

  it("pre-selects the whole standing menu, because that is the usual case", async () => {
    stub({ "/vendor/appearances": [], "/vendor/menu": MENU });
    const w = withRouter(VendorWeek);
    await flushPromises();
    await w.find(".cta").trigger("click");
    expect(w.findAll(".item--on")).toHaveLength(1);
  });

  it("renders a refused publish as NAMED fields, not as a generic failure", async () => {
    // the whole point of the Q-4 floor is that a cook can fix it in one pass
    stub({
      "/vendor/appearances": [],
      "/vendor/menu": MENU,
      "POST /vendor/appearances": {
        __status: 422,
        detail: { error: "listing_incomplete", missing: ["languages", "halal_disclosure"] },
      },
    });
    const w = withRouter(VendorWeek);
    await flushPromises();
    await w.find(".cta").trigger("click");
    w.vm.form.facility_id = "f-1";
    w.vm.form.date = "2026-08-01";
    await w.vm.publish();
    await flushPromises();

    const missing = w.find(".missing");
    expect(missing.exists()).toBe(true);
    expect(missing.text()).toContain(en["vendor.gap.languages"]);
    expect(missing.text()).toContain(en["vendor.gap.halal_disclosure"]);
    expect(missing.text()).not.toContain("422");
  });

  it("states the property attestation's consequence where it is made", async () => {
    stub({ "/vendor/appearances": [], "/vendor/menu": MENU });
    const w = withRouter(VendorWeek);
    await flushPromises();
    await w.find(".cta").trigger("click");
    expect(w.text()).toContain(en["vendor.property_approved_hint"]);
  });

  it("shows a stop's NAME, not its uuid", async () => {
    stub({
      "/vendor/appearances": [
        {
          appearance_id: "a-1",
          facility_id: "0f3b8c2e-1111-2222-3333-444444444444",
          facility_name: "Pilot 442",
          starts_at: "2026-08-01T11:00:00Z",
          ends_at: "2026-08-01T14:00:00Z",
          status: "scheduled",
          offerings: [],
          series_id: null,
        },
      ],
      "/vendor/menu": MENU,
    });
    const w = withRouter(VendorWeek);
    await flushPromises();
    expect(w.text()).toContain("Pilot 442");
    expect(w.text()).not.toContain("0f3b8c2e");
  });
});

// --- the menu, and the sentence that makes it safe ---
describe("Menu & prices", () => {
  const MENU = [
    { item_id: "m-1", name: "Tamales", price_cents: 1200, portions: 40, is_active: true },
    { item_id: "m-2", name: "Pozole", price_cents: 1400, portions: null, is_active: false },
  ];

  it("says out loud that a price change applies to the NEXT listing", async () => {
    // without this a cook assumes either that old listings silently update, or that
    // they must re-publish to fix a price going forward. Both are wrong.
    stub({ "/vendor/menu": MENU });
    const w = withRouter(VendorMenu);
    await flushPromises();
    expect(w.find(".menu__note").text()).toBe(en["vendor.menu_snapshot_note"]);
  });

  it("separates what is on the menu from what was taken off", async () => {
    stub({ "/vendor/menu": MENU });
    const w = withRouter(VendorMenu);
    await flushPromises();
    expect(w.findAll("tbody tr")).toHaveLength(1); // only the active one
    expect(w.find(".retired").text()).toContain("Pozole");
  });

  it("sends dollars typed by a cook as cents", async () => {
    stub({ "/vendor/menu": MENU, "PATCH /vendor/menu/m-1": { item_id: "m-1" } });
    const w = withRouter(VendorMenu);
    await flushPromises();
    const cell = w.find(".cell");
    expect(cell.element.value).toBe("12.00");
    cell.element.value = "13.50";
    await cell.trigger("change");
    await flushPromises();
    expect(calls.find((c) => c.key === "PATCH /vendor/menu/m-1").body.price_cents).toBe(1350);
  });

  it("takes an item off rather than deleting it", async () => {
    stub({ "/vendor/menu": MENU, "DELETE /vendor/menu/m-1": { item_id: "m-1" } });
    const w = withRouter(VendorMenu);
    await flushPromises();
    await w.findAll("tbody .link")[0].trigger("click");
    await flushPromises();
    // DELETE on the API retires; the label a cook reads says "take off", not "delete"
    expect(w.html()).not.toContain("Delete");
    expect(calls.some((c) => c.key === "DELETE /vendor/menu/m-1")).toBe(true);
  });
});

// --- verification never oversells ---
describe("Verification", () => {
  const STATE = {
    verify_status: "documents_on_file",
    kinds: ["license", "insurance", "halal_cert"],
    documents: [
      { document_id: "d-1", kind: "license", review_status: "pending", at: "2026-07-26T09:00:00Z" },
    ],
  };

  it("says what the middle rung actually means", async () => {
    stub({ "/vendor/documents": STATE });
    const w = withRouter(VendorVerification);
    await flushPromises();
    expect(w.text()).toContain(en["vendor.rung_means.documents_on_file"]);
    expect(w.text()).toContain("Nobody has inspected your kitchen");
  });

  it("reports a fresh upload as pending, not as approved", async () => {
    stub({ "/vendor/documents": STATE });
    const w = withRouter(VendorVerification);
    await flushPromises();
    expect(w.text()).toContain(en["vendor.doc_status.pending"]);
    expect(w.text()).toContain(en["vendor.upload_note"]);
  });

  it("never paints the middle rung with the success token", async () => {
    // §23: only `verified` earns --ledger-500; paperwork on file is not an endorsement
    stub({ "/vendor/documents": STATE });
    const w = withRouter(VendorVerification);
    await flushPromises();
    expect(w.html()).not.toContain("ledger-500");
  });
});

// --- reputation is the driver's numbers ---
describe("Reputation", () => {
  const REP = {
    shows_up: { confirmed: 19, published: 20 },
    rating: { average: 4.6, reviewers: 12 },
    reviews: [{ review_id: "r-1", rating: 5, text: "Best tamales on I-90", at: "2026-07-20" }],
    upheld_reports: 0,
    consecutive_no_shows: 0,
    publish_suspended: false,
  };

  it("shows the raw pair and never a percentage", async () => {
    stub({ "/vendor/reputation": REP });
    const w = withRouter(VendorReputation);
    await flushPromises();
    expect(w.text()).toMatch(/19\s*\/\s*20/);
    expect(w.text()).not.toMatch(/95\s*%/);
  });

  it("never shows a rating without its reviewer count", async () => {
    stub({ "/vendor/reputation": REP });
    const w = withRouter(VendorReputation);
    await flushPromises();
    expect(w.text()).toContain("4.6");
    expect(w.text()).toContain("12");
  });

  it("reads 'no reviews yet' rather than 0.0", async () => {
    // a zero average reads as "rated badly" when it means "nobody has said"
    stub({ "/vendor/reputation": { ...REP, rating: { average: null, reviewers: 0 }, reviews: [] } });
    const w = withRouter(VendorReputation);
    await flushPromises();
    expect(w.text()).toContain(en["vendor.no_reviews"]);
    expect(w.text()).not.toContain("0.0");
  });

  it("offers no way to edit, reply to, or take down a review", async () => {
    // the author's words survive the verdict either way (§23 settability)
    stub({ "/vendor/reputation": REP });
    const w = withRouter(VendorReputation);
    await flushPromises();
    expect(w.find(".review").findAll("button")).toHaveLength(0);
    expect(w.find(".review").findAll("input")).toHaveLength(0);
    expect(w.text()).toContain("Best tamales on I-90");
  });

  it("warns about no-shows before the suspension arrives", async () => {
    stub({ "/vendor/reputation": { ...REP, consecutive_no_shows: 2 } });
    const w = withRouter(VendorReputation);
    await flushPromises();
    expect(w.find(".warn").exists()).toBe(true);
  });
});

// --- promotions ---
describe("Promotions", () => {
  const PROMOS = [
    { promotion_id: "p-1", text: "Fresh tamales at 11", ends_at: "2026-08-02", status: "active" },
  ];

  it("reports delivery as what actually went out, with the reason it is fewer", async () => {
    stub({
      "/vendor/promotions": PROMOS,
      "POST /vendor/promotions": { promotion_id: "p-2", alerts_delivered: 3 },
    });
    const w = withRouter(VendorPromotions);
    await flushPromises();
    w.vm.draft.text = "Pozole today";
    await w.vm.add();
    await flushPromises();
    expect(w.find(".delivered").text()).toContain("3");
    expect(w.text()).toContain(en["vendor.delivery_caps"]);
  });

  it("says plainly that an edit does not push another alert", async () => {
    stub({ "/vendor/promotions": PROMOS });
    const w = withRouter(VendorPromotions);
    await flushPromises();
    expect(w.text()).toContain(en["vendor.edit_no_resend"]);
  });

  it("counts down the character limit as a cook types", async () => {
    stub({ "/vendor/promotions": PROMOS });
    const w = withRouter(VendorPromotions);
    await flushPromises();
    w.vm.draft.text = "x".repeat(130);
    await flushPromises();
    expect(w.text()).toContain("10 left");
  });
});

// --- the way in ---
describe("Signing up (§18 door, owner decision: open)", () => {
  it("never asks a cook for an authority number", async () => {
    const w = withRouter(VendorJoinSurface);
    await flushPromises();
    expect(w.text().toLowerCase()).not.toContain("authority");
    expect(w.text().toLowerCase()).not.toContain("mc number");
  });

  it("says up front that it is free and sells nothing", async () => {
    const w = withRouter(VendorJoinSurface);
    expect(w.find(".join__free").text()).toBe(en["vendor.join.free"]);
  });

  it("asks for exactly what the publish floor will require", async () => {
    const w = withRouter(VendorJoinSurface);
    w.vm.step = "business";
    await flushPromises();
    expect(w.text()).toContain(en["vendor.languages"]);
    expect(w.text()).toContain(en["vendor.halal"]);
  });

  it("tells a cook they start Unverified before they get there", async () => {
    // "Unverified" on their own pin must never be a surprise (§11.7)
    const w = withRouter(VendorJoinSurface);
    w.vm.step = "business";
    await flushPromises();
    expect(w.find(".join__ladder").text()).toBe(en["vendor.join.starts_unverified"]);
  });

  it("will not submit a business without the floor's fields", async () => {
    const w = withRouter(VendorJoinSurface);
    w.vm.step = "business";
    await flushPromises();
    expect(w.find(".cta").attributes("disabled")).toBeDefined();
    w.vm.business.name = "Ana's Tamales";
    w.vm.business.languages = "es, en";
    await flushPromises();
    expect(w.find(".cta").attributes("disabled")).toBeUndefined();
  });

  it("explains a duplicate rather than showing a status code", async () => {
    stub({ "POST /vendors/register": { __status: 409, detail: { error: "duplicate_vendor" } } });
    const w = withRouter(VendorJoinSurface);
    w.vm.step = "business";
    w.vm.business.name = "Ana's Tamales";
    w.vm.business.languages = "es";
    await w.vm.createBusiness();
    await flushPromises();
    expect(w.find(".join__error").text()).toBe(en["vendor.join.duplicate"]);
  });
});

// --- Phase A ---
describe("Phase A holds across the portal", () => {
  it("ships no order, checkout or payment control", async () => {
    const screens = [
      [VendorWeek, { "/vendor/appearances": [], "/vendor/menu": [] }],
      [VendorMenu, { "/vendor/menu": [] }],
      [VendorPromotions, { "/vendor/promotions": [] }],
      [VendorReputation, { "/vendor/reputation": { shows_up: { confirmed: 0, published: 0 }, rating: { average: null, reviewers: 0 }, reviews: [], upheld_reports: 0, consecutive_no_shows: 0, publish_suspended: false } }],
    ];
    for (const [Comp, routeMap] of screens) {
      stub(routeMap);
      const w = withRouter(Comp);
      await flushPromises();
      const html = w.html().toLowerCase();
      for (const forbidden of ["checkout", "add to cart", "pay now", "invoice", "payout"]) {
        expect(html, `${Comp.__name} mentions ${forbidden}`).not.toContain(forbidden);
      }
    }
  });
});
