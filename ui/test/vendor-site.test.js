// AI-CONTEXT: M13-FR7 — the claim flow's own laws as tests (design-prd §18, §22.3).
//
// What these defend, in order of how much it would cost to get wrong:
// · **Never a UUID.** A claimant recognises their site by name and address. The
//   moment a facility id reaches the screen this flow is unusable by the person it
//   is for, and nothing else in the test suite would notice.
// · **A dispute is disclosed before the form, and never reads as a rejection.** The
//   domain deliberately makes a rival claim a dispute an operator settles; a screen
//   that said "taken" or failed silently would undo that decision in the UI.
// · **The mismatch names the site, not a score.** "0.42" tells a business owner
//   nothing about what to type next.
// · **Curation adds.** What ingestion knows renders locked (E3.2) — a screen that
//   let someone untick it would imply a power the server does not grant.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import VendorSite from "../src/surfaces/vendor/VendorSite.vue";
import VendorPortalShell from "../src/surfaces/vendor/VendorPortalShell.vue";
import FacilityProfileSurface from "../src/surfaces/FacilityProfileSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const FACILITY_ID = "3f9d1a52-77c2-4a1e-9f0b-2b4d6e8a1c33";
const CLAIM_ID = "8c1e0b44-1d33-4a77-b0aa-9e5f2c7d4411";

const router = () => createRouter({ history: createMemoryHistory(), routes });
const withRouter = (Comp) => mount(Comp, { global: { plugins: [router()] } });

let calls;

function stub(routeMap) {
  calls = [];
  global.fetch = vi.fn((url, opts) => {
    const path = String(url).replace("http://localhost:8008", "").split("?")[0];
    const key = opts?.method ? `${opts.method} ${path}` : path;
    calls.push({ path, key, url: String(url), body: opts?.body ? JSON.parse(opts.body) : null });
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

// shape-matched to the endpoint (api/vendor_portal.py::profile), which ALWAYS returns
// `verify_status` — the shell renders it in its header, so a mock without it measured a
// portal saying "vendor.undefined" out loud. §23 entries 84/85, again.
const SERVICE_VENDOR = {
  name: "Gateway Truck Service",
  vendor_type: "service_center",
  verify_status: "unverified",
};
const KINDS = ["tire", "wash", "truck_repair", "mobile_repair", "towing", "parts"];

function claim(overrides = {}) {
  return {
    claim_id: CLAIM_ID,
    facility_id: FACILITY_ID,
    facility_name: "Gateway Truck Service",
    facility_address: "1400 Range Line Rd, Joplin MO",
    claimed_name: "Gateway Truck Service",
    status: "pending",
    services_ingested: ["tire"],
    services_added: [],
    services: ["tire"],
    has_document: true,
    hours: null,
    phone: null,
    ...overrides,
  };
}

beforeEach(() => setToken("portal-token"));
afterEach(() => {
  logout();
  vi.restoreAllMocks();
});

describe("claiming a site (M13-FR7)", () => {
  it("shows a claim by its name and address, never by its id", async () => {
    stub({
      "/vendor/profile": SERVICE_VENDOR,
      "/vendor/claims": { claims: [claim()], service_kinds: KINDS },
    });
    const w = withRouter(VendorSite);
    await flushPromises();

    expect(w.text()).toContain("Gateway Truck Service");
    expect(w.text()).toContain("1400 Range Line Rd, Joplin MO");
    expect(w.text()).not.toContain(FACILITY_ID);
    expect(w.text()).not.toContain(CLAIM_ID);
  });

  it("states what pending means rather than showing only a status word", async () => {
    stub({
      "/vendor/profile": SERVICE_VENDOR,
      "/vendor/claims": { claims: [claim()], service_kinds: KINDS },
    });
    const w = withRouter(VendorSite);
    await flushPromises();

    expect(w.text()).toContain(en["vendor.site.status.pending"]);
    expect(w.text()).toContain(en["vendor.site.means.pending"]);
  });

  it("says a dispute is an operator's decision, not a loss", async () => {
    stub({
      "/vendor/profile": SERVICE_VENDOR,
      "/vendor/claims": { claims: [claim({ status: "disputed" })], service_kinds: KINDS },
    });
    const w = withRouter(VendorSite);
    await flushPromises();

    const said = en["vendor.site.means.disputed"];
    expect(w.text()).toContain(said);
    // the copy must carry the operator's decision, never imply the claim failed
    expect(said.toLowerCase()).toContain("operator");
    expect(w.text()).not.toContain(en["vendor.site.means.rejected"]);
  });

  it("discloses an existing claim in the search row, before the form", async () => {
    stub({
      "/vendor/profile": SERVICE_VENDOR,
      "/vendor/claims": { claims: [], service_kinds: KINDS },
      "/vendor/claimable": [
        {
          facility_id: FACILITY_ID,
          name: "Gateway Truck Service",
          address: "1400 Range Line Rd",
          services: ["tire"],
          already_claimed: true,
          claimed_by_me: false,
        },
      ],
    });
    const w = withRouter(VendorSite);
    await flushPromises();

    await w.find('input[type="search"]').setValue("gateway");
    await w.findAll("button").find((b) => b.text().includes(en["vendor.site.search"])).trigger("click");
    await flushPromises();

    expect(w.text()).toContain(en["vendor.site.taken"]);
    // and it is stated on the row itself — no form has been opened yet
    expect(w.text()).not.toContain(en["vendor.site.claim_step"]);
  });

  it("prefills the claimed name from the VENDOR, not the facility", async () => {
    // prefilling from the facility would score 1.00 every time and make the name
    // check theatre — the point is whether the business name resembles the site
    stub({
      "/vendor/profile": { name: "Range Line Repair Co", vendor_type: "service_center" },
      "/vendor/claims": { claims: [], service_kinds: KINDS },
      "/vendor/claimable": [
        {
          facility_id: FACILITY_ID,
          name: "Gateway Truck Service",
          address: null,
          services: ["tire"],
          already_claimed: false,
          claimed_by_me: false,
        },
      ],
    });
    const w = withRouter(VendorSite);
    await flushPromises();

    await w.find('input[type="search"]').setValue("gateway");
    await w.findAll("button").find((b) => b.text().includes(en["vendor.site.search"])).trigger("click");
    await flushPromises();
    await w.find(".hit__pick").trigger("click");
    await flushPromises();

    const name = w.find('input[type="text"]');
    expect(name.element.value).toBe("Range Line Repair Co");
  });

  it("answers a name mismatch with the site's own name and no score", async () => {
    stub({
      "/vendor/profile": { name: "Completely Different Ltd", vendor_type: "service_center" },
      "/vendor/claims": { claims: [], service_kinds: KINDS },
      "/vendor/claimable": [
        {
          facility_id: FACILITY_ID,
          name: "Gateway Truck Service",
          address: null,
          services: ["tire"],
          already_claimed: false,
          claimed_by_me: false,
        },
      ],
      "POST /vendor/claims": { __status: 422, detail: { error: "name_mismatch", score: 0.42 } },
    });
    const w = withRouter(VendorSite);
    await flushPromises();

    await w.find('input[type="search"]').setValue("gateway");
    await w.findAll("button").find((b) => b.text().includes(en["vendor.site.search"])).trigger("click");
    await flushPromises();
    await w.find(".hit__pick").trigger("click");
    await flushPromises();
    await w.findAll("button").find((b) => b.text().includes(en["vendor.site.submit"])).trigger("click");
    await flushPromises();

    expect(w.text()).toContain(en["vendor.site.mismatch"]);
    expect(w.find(".mismatch__name").text()).toBe("Gateway Truck Service");
    expect(w.text()).not.toContain("0.42");
    expect(w.text()).not.toContain("0.55");
  });

  it("locks what ingestion already knows and says whose fact it is", async () => {
    stub({
      "/vendor/profile": SERVICE_VENDOR,
      "/vendor/claims": {
        claims: [
          claim({
            status: "approved",
            services_ingested: ["tire"],
            services_added: ["towing"],
            services: ["tire", "towing"],
          }),
        ],
        service_kinds: KINDS,
      },
    });
    const w = withRouter(VendorSite);
    await flushPromises();

    const boxes = w.findAll('input[type="checkbox"]');
    const byKind = Object.fromEntries(KINDS.map((k, i) => [k, boxes[i]]));
    // present facts cannot be unticked — curation is additive by construction
    expect(byKind.tire.element.disabled).toBe(true);
    expect(byKind.towing.element.disabled).toBe(true);
    expect(byKind.wash.element.disabled).toBe(false);
    expect(w.text()).toContain(en["vendor.site.from_records"]);
    expect(w.text()).toContain(en["vendor.site.from_you"]);
    expect(w.text()).toContain(en["vendor.site.union_note"]);
  });

  it("sends only the additions, never the locked facts back", async () => {
    stub({
      "/vendor/profile": SERVICE_VENDOR,
      "/vendor/claims": {
        claims: [claim({ status: "approved", services: ["tire"], services_ingested: ["tire"] })],
        service_kinds: KINDS,
      },
      [`PATCH /vendor/claims/${CLAIM_ID}`]: {},
    });
    const w = withRouter(VendorSite);
    await flushPromises();

    const boxes = w.findAll('input[type="checkbox"]');
    await boxes[KINDS.indexOf("wash")].trigger("change");
    await w.findAll("button").find((b) => b.text() === en["portal.vendor.save"]).trigger("click");
    await flushPromises();

    const patch = calls.find((c) => c.key.startsWith("PATCH"));
    expect(patch.body.services_added).toEqual(["wash"]);
  });

  it("tells a food vendor there is nothing here rather than showing a dead search", async () => {
    stub({ "/vendor/profile": { name: "Osh Express", vendor_type: "food_mobile", verify_status: "unverified" } });
    const w = withRouter(VendorSite);
    await flushPromises();

    expect(w.text()).toContain(en["vendor.site.food_vendor"]);
    expect(w.find('input[type="search"]').exists()).toBe(false);
    // and it never asks the server for a search it is not entitled to
    expect(calls.some((c) => c.path === "/vendor/claimable")).toBe(false);
  });
});

// the other end of the flow: what an approved, curated claim is actually FOR
describe("what a driver sees for a claimed service centre", () => {
  // AI-CONTEXT: the profile endpoint has to answer for this surface to render (§23
  // entry 131). It used to fall back to `sampleProfile()` when the route 404'd, so
  // these two tests measured the service-centre card sitting on an invented facility.
  const PROFILE = {
    facility_id: FACILITY_ID,
    name: "Gateway Truck Service",
    check_in_procedure: null,
    overnight_parking: false,
    restrooms: false,
    dwell: { overall: { median_seconds: 0, p90_seconds: 0, sample_size: 0 }, by_hour: {} },
    ratings: { overall: null, review_count: 0, per_aspect: {} },
    detention_risk: { rate: null, sample_size: 0, basis: "m3_pending" },
    reviews: [],
  };

  async function profileAt(serviceCenter) {
    stub({
      [`/facility/${FACILITY_ID}/profile`]: PROFILE,
      ...(serviceCenter ? { [`/vendors/service-center/${FACILITY_ID}`]: serviceCenter } : {}),
    });
    const r = router();
    r.push(`/facility/${FACILITY_ID}`);
    await r.isReady();
    const w = mount(FacilityProfileSurface, { global: { plugins: [r] } });
    await flushPromises();
    return w;
  }

  it("names the business, its rung and its services", async () => {
    const w = await profileAt({
      facility_id: FACILITY_ID,
      name: "Gateway Truck Service",
      vendor_id: "v-1",
      vendor_name: "Gateway Truck Service",
      verify_status: "verified",
      services: ["tire", "towing"],
      hours: "24/7",
      phone: "4175550123",
    });

    expect(w.text()).toContain(en["profile.service_center"]);
    expect(w.find(".sc__who").text()).toContain("Gateway Truck Service");
    expect(w.find(".sc__services").text()).toContain(en["facility.service.tire"]);
    expect(w.text()).toContain("24/7");
    expect(w.text()).toContain("4175550123");
    // §11.7: the hours and phone are the business's own words, and it says so
    expect(w.text()).toContain(en["profile.sc_source"]);
  });

  it("keeps documents_on_file neutral, never positive (C-1)", async () => {
    const w = await profileAt({
      facility_id: FACILITY_ID,
      name: "Gateway Truck Service",
      vendor_id: "v-1",
      vendor_name: "Gateway Truck Service",
      verify_status: "documents_on_file",
      services: ["tire"],
      hours: null,
      phone: null,
    });
    // paperwork received is not an endorsement — only `verified` earns ledger green
    expect(w.find(".sc__tier").attributes("style")).toContain("--text-2");
  });

  it("leaves an unclaimed facility a plain POI", async () => {
    const w = await profileAt(null);
    expect(w.find(".sc__who").exists()).toBe(false);
    expect(w.text()).not.toContain(en["profile.service_center"]);
  });
});

describe("the rail (design-prd §22.2 navigation)", () => {
  it("offers My site to a service centre", async () => {
    stub({ "/vendor/profile": SERVICE_VENDOR });
    const w = withRouter(VendorPortalShell);
    await flushPromises();
    expect(w.find(".rail").text()).toContain(en["vendor.nav.site"]);
  });

  it("does not offer it to a mobile cook — a control that cannot be used", async () => {
    stub({ "/vendor/profile": { name: "Osh Express", vendor_type: "food_mobile" } });
    const w = withRouter(VendorPortalShell);
    await flushPromises();
    expect(w.find(".rail").text()).not.toContain(en["vendor.nav.site"]);
    expect(w.find(".rail").text()).toContain(en["vendor.nav.week"]);
  });
});
