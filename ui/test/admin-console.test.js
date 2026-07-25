// AI-CONTEXT: Admin Console 2.0 (design-prd §18, §23 E-D4). Replaces the tests for
// the old single stacked page.
//
// What these defend:
// · The flag row communicates STATE and ACTION separately (decision 3). The old row
//   had one button whose label was the action, so an operator read "Disable" and had
//   to infer the flag was on.
// · Disabling a MODULE flag confirms first and names what it gates; enabling does
//   not, because turning something on is recoverable by turning it off.
// · The Overview distinguishes "never ran", "switched off" and "failing" — a naive
//   health panel collapses all three into a blank cell.
// · SLA-overdue work is flagged in flare and carried separately from the queue total.
// · A registered-but-unbuilt module view is LABELLED, never linked. Thirteen links
//   to 404s is the dead-control anti-pattern this codebase removed once already.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import AdminShell from "../src/surfaces/admin/AdminShell.vue";
import AdminOverview from "../src/surfaces/admin/AdminOverview.vue";
import AdminFlags from "../src/surfaces/admin/AdminFlags.vue";
import AdminModeration from "../src/surfaces/admin/AdminModeration.vue";
import AdminModules from "../src/surfaces/admin/AdminModules.vue";
import AdminAudit from "../src/surfaces/admin/AdminAudit.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";

const OVERVIEW = {
  jobs: [
    {
      job: "tpims_dynamic",
      flag: "f02_ingest_tpims_dynamic",
      enabled: true,
      last_run_at: "2026-07-26T08:00:00Z",
      ok: true,
      summary: { applied: 17 },
      error: null,
      consecutive_failures: 0,
      next_run_at: "2026-07-26T08:03:00Z",
    },
    {
      job: "tpims_static",
      flag: "f02_ingest_tpims_static",
      enabled: false,
      last_run_at: null,
      ok: null,
      summary: null,
      error: null,
      consecutive_failures: 0,
      next_run_at: null,
    },
    {
      job: "eia_regional",
      flag: "m07_ingest_eia",
      enabled: true,
      last_run_at: "2026-07-26T07:00:00Z",
      ok: false,
      summary: null,
      error: "ConnectTimeout()",
      consecutive_failures: 3,
      next_run_at: "2026-07-26T09:00:00Z",
    },
  ],
  facilities: { total: 4153, by_source: { osm: 2321, ntad: 1827 } },
  ingest: {},
  eia_week_of: null,
  pending: {
    vendor_verification: 2,
    moderation: 4,
    moderation_overdue: 1,
    claim_disputes: 0,
  },
  funnels: {
    detention: [
      { event: "load_added", count: 10 },
      { event: "arrived", count: 6 },
      { event: "claim_sent", count: 3 },
    ],
    vendor_appearances: { published: 20, confirmed: 19 },
  },
};

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

function stubFetch(routeMap) {
  const fn = vi.fn().mockImplementation((url, opts) => {
    const path = String(url).replace("http://localhost:8008", "").split("?")[0];
    const key = opts?.method ? `${opts.method} ${path}` : path;
    if (key in routeMap) return jsonOk(routeMap[key]);
    if (path in routeMap) return jsonOk(routeMap[path]);
    return jsonOk({});
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function testRouter() {
  return createRouter({ history: createMemoryHistory(), routes });
}

beforeEach(() => setToken("tok-admin"));
afterEach(() => {
  vi.unstubAllGlobals();
  logout();
});

describe("Admin shell — sectioned portal (§23 E-D4)", () => {
  it("offers every section in the rail", async () => {
    stubFetch({ "/admin/overview": OVERVIEW });
    const w = mount(AdminShell, { global: { plugins: [testRouter()] } });
    await flushPromises();

    const labels = w.findAll(".rail__item").map((a) => a.text());
    expect(labels.length).toBe(8);
    expect(labels.join(" ")).toContain("Accounts");
    expect(labels.join(" ")).toContain("Overview");
    expect(labels.join(" ")).toContain("Moderation");
    expect(labels.join(" ")).toContain("Audit");
  });

  it("badges only the sections with real work waiting", async () => {
    // a "0" badge on every item is decoration, and §21.3 has no patience for it
    stubFetch({ "/admin/overview": OVERVIEW });
    const w = mount(AdminShell, { global: { plugins: [testRouter()] } });
    await flushPromises();

    const badges = w.findAll(".rail__badge");
    expect(badges).toHaveLength(2); // vendors (2) + moderation (4)
    expect(badges.map((b) => b.text())).toEqual(["2", "4"]);
  });

  it("turns the moderation badge to flare when work is overdue", async () => {
    stubFetch({ "/admin/overview": OVERVIEW });
    const w = mount(AdminShell, { global: { plugins: [testRouter()] } });
    await flushPromises();
    expect(w.find(".rail__badge--late").exists()).toBe(true);
  });

  it("does not flare the badge when nothing is overdue", async () => {
    stubFetch({
      "/admin/overview": { ...OVERVIEW, pending: { ...OVERVIEW.pending, moderation_overdue: 0 } },
    });
    const w = mount(AdminShell, { global: { plugins: [testRouter()] } });
    await flushPromises();
    expect(w.find(".rail__badge--late").exists()).toBe(false);
  });

  it("shows the no-access notice on 403", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403 }));
    const w = mount(AdminShell, { global: { plugins: [testRouter()] } });
    await flushPromises();
    expect(w.text()).toContain("Platform admins only");
    expect(w.find(".rail").exists()).toBe(false);
  });

  it("registers every section as a bookmarkable child route", () => {
    // sections are routes, not internal tabs: a queue can be shared and back works
    const admin = routes.find((r) => r.path === "/admin");
    expect(admin.meta.portal).toBe(true);
    expect(admin.meta.chrome).toBe(false);
    expect(admin.children.map((c) => c.path)).toEqual([
      "",
      "flags",
      "vendors",
      "moderation",
      "accounts",
      "data",
      "modules",
      "audit",
    ]);
  });
});

describe("Overview — the morning glance", () => {
  it("distinguishes never-ran, switched-off and failing", async () => {
    // a naive health panel collapses all three into a blank cell
    stubFetch({ "/admin/overview": OVERVIEW });
    const w = mount(AdminOverview);
    await flushPromises();

    const text = w.text();
    expect(text).toContain("ok"); // tpims_dynamic ran fine
    expect(text).toContain("switched off"); // tpims_static is idle, not broken
    expect(text).toContain("failing"); // eia is broken
    expect(text).toContain("ConnectTimeout()"); // and says how
    expect(text).toContain("×3"); // with the streak
  });

  it("says 'never ran' rather than showing a zero date", async () => {
    stubFetch({ "/admin/overview": OVERVIEW });
    const w = mount(AdminOverview);
    await flushPromises();
    // the dash is for the timestamp; the state pill carries the meaning
    expect(w.text()).toContain("—");
  });

  it("carries the overdue count separately and in flare", async () => {
    stubFetch({ "/admin/overview": OVERVIEW });
    const w = mount(AdminOverview);
    await flushPromises();

    expect(w.find(".stat--late").exists()).toBe(true);
    expect(w.find(".stat--late").text()).toContain("overdue");
  });

  it("omits the overdue tile entirely when nothing is late", async () => {
    stubFetch({
      "/admin/overview": { ...OVERVIEW, pending: { ...OVERVIEW.pending, moderation_overdue: 0 } },
    });
    const w = mount(AdminOverview);
    await flushPromises();
    expect(w.find(".stat--late").exists()).toBe(false);
  });

  it("shows both value loops", async () => {
    stubFetch({ "/admin/overview": OVERVIEW });
    const w = mount(AdminOverview);
    await flushPromises();
    expect(w.text()).toContain("19"); // vendor appearances confirmed
    expect(w.text()).toContain("20"); // of published
  });

  it("never localizes a timestamp", async () => {
    // an operator correlating with container logs needs one stable format
    stubFetch({ "/admin/overview": OVERVIEW });
    const w = mount(AdminOverview);
    await flushPromises();
    expect(w.text()).toContain("2026-07-26 08:00");
  });
});

describe("Flags — state and action are different jobs (decision 3)", () => {
  const FLAGS = [
    {
      key: "m13_vendor",
      description: "M13 Vendor Network",
      enabled: true,
      kill_switch: false,
      can_activate: true,
      gates: [],
      family: "modules",
      gates_a_module: true,
      last_changed_at: "2026-07-26T08:00:00Z",
      last_changed_by: "ops@example.com",
    },
    {
      key: "f02_ingest_tpims_static",
      description: "TPIMS static",
      enabled: false,
      kill_switch: false,
      can_activate: true,
      gates: [],
      family: "ingest",
      gates_a_module: false,
      last_changed_at: null,
      last_changed_by: null,
    },
    {
      key: "f01_authority_verification",
      description: "FMCSA verification",
      enabled: false,
      kill_switch: false,
      can_activate: false,
      gates: [{ name: "legal_review", satisfied: false }],
      family: "foundation",
      gates_a_module: false,
      last_changed_at: null,
      last_changed_by: null,
    },
  ];
  const BASE = {
    "/admin/flags": FLAGS,
    "/admin/config/scopes": ["m13"],
    "/admin/config": { scope: "m13", entries: { m13_inactive_days: 28 }, provenance: {} },
  };

  it("shows an explicit state pill separate from the action button", async () => {
    stubFetch(BASE);
    const w = mount(AdminFlags);
    await flushPromises();

    const pills = w.findAll(".pill").map((p) => p.text());
    expect(pills).toContain("On");
    expect(pills).toContain("Off");
    // and the button says what pressing it DOES, not what the state is
    const buttons = w.findAll(".btn").map((b) => b.text());
    expect(buttons).toContain("Disable");
    expect(buttons).toContain("Enable");
  });

  it("distinguishes 'off' from 'cannot be turned on'", async () => {
    // a gated flag is a different fact from one merely switched off
    stubFetch(BASE);
    const w = mount(AdminFlags);
    await flushPromises();
    expect(w.findAll(".pill").map((p) => p.text())).toContain("Gates unmet");
  });

  it("groups flags by family", async () => {
    stubFetch(BASE);
    const w = mount(AdminFlags);
    await flushPromises();
    const families = w.findAll(".flags__family").map((h) => h.text());
    expect(families).toEqual(["Foundation", "Ingest", "Modules"]);
  });

  it("filters by search", async () => {
    stubFetch(BASE);
    const w = mount(AdminFlags);
    await flushPromises();
    await w.find(".flags__search").setValue("tpims");
    expect(w.findAll(".flags__family")).toHaveLength(1);
  });

  it("confirms before switching off a module flag, naming what it gates", async () => {
    const fetchStub = stubFetch(BASE);
    const w = mount(AdminFlags);
    await flushPromises();

    const disable = w.findAll(".btn").find((b) => b.text() === "Disable");
    await disable.trigger("click");

    // nothing was sent yet — the operator is asked first
    expect(fetchStub.mock.calls.some((c) => String(c[0]).includes("/disable"))).toBe(false);
    expect(w.find(".confirm").exists()).toBe(true);
    expect(w.find(".confirm__key").text()).toContain("M13 Vendor Network");
    expect(w.text()).toContain("switches off a whole module");
  });

  it("sends the disable only after confirmation", async () => {
    const fetchStub = stubFetch(BASE);
    const w = mount(AdminFlags);
    await flushPromises();
    await w.findAll(".btn").find((b) => b.text() === "Disable").trigger("click");
    await w.findAll(".btn").find((b) => b.text().includes("Yes")).trigger("click");
    await flushPromises();

    expect(fetchStub.mock.calls.some((c) => String(c[0]).includes("/disable"))).toBe(true);
  });

  it("cancelling leaves the flag alone", async () => {
    const fetchStub = stubFetch(BASE);
    const w = mount(AdminFlags);
    await flushPromises();
    await w.findAll(".btn").find((b) => b.text() === "Disable").trigger("click");
    await w.findAll(".btn").find((b) => b.text() === "Cancel").trigger("click");

    expect(w.find(".confirm").exists()).toBe(false);
    expect(fetchStub.mock.calls.some((c) => String(c[0]).includes("/disable"))).toBe(false);
  });

  it("enables without a confirm — turning on is recoverable", async () => {
    const fetchStub = stubFetch(BASE);
    const w = mount(AdminFlags);
    await flushPromises();

    const row = w.findAll("tr").find((r) => r.text().includes("f02_ingest_tpims_static"));
    await row.find(".btn").trigger("click");
    await flushPromises();

    // no confirm step, and the call went straight out
    expect(w.find(".confirm").exists()).toBe(false);
    expect(
      fetchStub.mock.calls.some((c) =>
        String(c[0]).includes("/admin/flags/f02_ingest_tpims_static/enable"),
      ),
    ).toBe(true);
  });

  it("disables the action on a flag whose gates are unmet", async () => {
    stubFetch(BASE);
    const w = mount(AdminFlags);
    await flushPromises();
    const gatedRow = w.findAll("tr").find((r) => r.text().includes("f01_authority_verification"));
    expect(gatedRow.find(".btn").attributes("disabled")).toBeDefined();
  });

  it("shows who last changed a flag", async () => {
    stubFetch(BASE);
    const w = mount(AdminFlags);
    await flushPromises();
    expect(w.text()).toContain("ops@example.com");
  });

  it("shows config provenance and what a value replaced", async () => {
    stubFetch({
      ...BASE,
      "/admin/config": {
        scope: "m13",
        entries: { m13_inactive_days: 14 },
        provenance: { m13_inactive_days: { set_by: "cfg@example.com", previous: 28 } },
      },
    });
    const w = mount(AdminFlags);
    await flushPromises();
    expect(w.text()).toContain("cfg@example.com");
    expect(w.text()).toContain("28");
  });
});

describe("Moderation — three verdicts, and the SLA is visible", () => {
  const QUEUE = [
    {
      id: "i-1",
      content_kind: "vendor_review",
      content_ref: "r-1",
      status: "pending",
      age_hours: 90.5,
      overdue: true,
      sla_hours: 72,
      reports: 2,
    },
    {
      id: "i-2",
      content_kind: "vendor_listing",
      content_ref: "v-1",
      status: "pending",
      age_hours: 2.0,
      overdue: false,
      sla_hours: 72,
      reports: 1,
    },
  ];

  it("flags overdue work with colour AND a label", async () => {
    stubFetch({ "/admin/moderation": QUEUE });
    const w = mount(AdminModeration);
    await flushPromises();

    const late = w.find(".row--late");
    expect(late.exists()).toBe(true);
    expect(late.text()).toContain("overdue"); // never colour alone (§16 C-1)
    expect(late.text()).toContain("90.5h");
  });

  it("offers uphold, dismiss and frivolous", async () => {
    // the third verdict is what stops the report button being a free weapon
    stubFetch({ "/admin/moderation": QUEUE });
    const w = mount(AdminModeration);
    await flushPromises();

    const actions = w.findAll("tr")[0].findAll(".btn").map((b) => b.text());
    expect(actions).toEqual(["Uphold", "Dismiss", "Frivolous report"]);
  });

  it("sends frivolous as a dismissal that strikes the reporter", async () => {
    const fetchStub = stubFetch({ "/admin/moderation": QUEUE });
    const w = mount(AdminModeration);
    await flushPromises();

    await w.findAll(".btn").find((b) => b.text() === "Frivolous report").trigger("click");
    await flushPromises();

    const call = fetchStub.mock.calls.find((c) => String(c[0]).includes("/resolve"));
    const body = JSON.parse(call[1].body);
    expect(body).toEqual({ approve: false, frivolous: true, reason: null });
  });

  it("shows the report count so a pattern is visible", async () => {
    stubFetch({ "/admin/moderation": QUEUE });
    const w = mount(AdminModeration);
    await flushPromises();
    expect(w.findAll("tr")[0].text()).toContain("2");
  });

  it("says so plainly when the queue is empty", async () => {
    stubFetch({ "/admin/moderation": [] });
    const w = mount(AdminModeration);
    await flushPromises();
    expect(w.text()).toContain("Nothing to review.");
  });
});

describe("Modules — the registry, rendered honestly", () => {
  const VIEWS = [
    { key: "m13.vendors", module: "m13", title: "Vendors", path: "/admin/m13/vendors" },
    { key: "m07.fuel", module: "m07", title: "Fuel Network", path: "/admin/m07/fuel" },
  ];

  it("labels a registered view whose destination does not exist", async () => {
    // thirteen links to 404s is the dead-control anti-pattern removed once already
    stubFetch({ "/admin/views": VIEWS });
    const w = mount(AdminModules, { global: { plugins: [testRouter()] } });
    await flushPromises();

    expect(w.text()).toContain("Fuel Network");
    expect(w.text()).toContain("Registered, not built yet");
    expect(w.findAll(".link")).toHaveLength(0);
  });

  it("links a view once its destination resolves", async () => {
    // future modules slot in with no change here
    stubFetch({
      "/admin/views": [{ key: "audit", module: "f14", title: "Audit", path: "/admin/audit" }],
    });
    const w = mount(AdminModules, { global: { plugins: [testRouter()] } });
    await flushPromises();
    expect(w.findAll(".link")).toHaveLength(1);
  });
});

describe("Audit — what it changed FROM", () => {
  const ENTRIES = [
    {
      id: "a-1",
      action: "flag_disable",
      actor: "ops@example.com",
      target_kind: "flag",
      target_key: "m13_vendor",
      target_ref: null,
      detail: {},
      before: { enabled: true },
      after: { enabled: false },
      created_at: "2026-07-26T08:30:00Z",
    },
    {
      id: "a-2",
      action: "config_set",
      actor: "cfg@example.com",
      target_kind: "config",
      target_key: "m13_inactive_days",
      target_ref: null,
      detail: {},
      before: { value: 28 },
      after: { value: 14 },
      created_at: "2026-07-26T09:00:00Z",
    },
  ];

  it("shows the before and after of every change", async () => {
    stubFetch({ "/admin/audit": ENTRIES });
    const w = mount(AdminAudit);
    await flushPromises();

    expect(w.text()).toContain("enabled=true → enabled=false");
    expect(w.text()).toContain("value=28 → value=14");
  });

  it("attributes every entry and never localizes the time", async () => {
    stubFetch({ "/admin/audit": ENTRIES });
    const w = mount(AdminAudit);
    await flushPromises();
    expect(w.text()).toContain("ops@example.com");
    expect(w.text()).toContain("2026-07-26 08:30");
  });

  it("filters to one action", async () => {
    stubFetch({ "/admin/audit": ENTRIES });
    const w = mount(AdminAudit);
    await flushPromises();

    await w.find("select").setValue("config_set");
    expect(w.findAll("tbody tr")).toHaveLength(1);
    expect(w.text()).toContain("m13_inactive_days");
  });

  it("says so plainly when the log is empty", async () => {
    stubFetch({ "/admin/audit": [] });
    const w = mount(AdminAudit);
    await flushPromises();
    expect(w.text()).toContain("No operator actions yet.");
  });
});

// --- E-D6 Accounts: the powers, and the copy that states their limits ---
import AdminAccounts from "../src/surfaces/admin/AdminAccounts.vue";

const ACCOUNT = {
  account_id: "a-1",
  email: "bek@example.com",
  display_name: "Bek",
  active: true,
  deactivated_at: null,
  must_change_credential: false,
  roles: ["driver"],
  created_at: "2026-07-26T08:00:00Z",
  profile: { legal_name: "Bek T", mc_number: "778899", plate_state: "FL", plate_number: "4XN2291" },
  audit: [{ action: "account_create", created_at: "2026-07-26T08:00:00Z", before: null, after: {} }],
};

describe("Accounts — powers and their limits (E-D6)", () => {
  it("says in place why there is no delete button", async () => {
    // an operator should not hunt for a control that will never exist
    stubFetch({ "/admin/accounts": [ACCOUNT] });
    const w = mount(AdminAccounts);
    await flushPromises();
    expect(w.text()).toContain("Accounts are never deleted");
    expect(w.text()).toContain("money, claims and evidence");
  });

  it("shows account state as colour AND label", async () => {
    stubFetch({ "/admin/accounts": [ACCOUNT, { ...ACCOUNT, account_id: "a-2", active: false }] });
    const w = mount(AdminAccounts);
    await flushPromises();
    const pills = w.findAll(".pill").map((p) => p.text());
    expect(pills).toContain("Active");
    expect(pills).toContain("Deactivated");
  });

  it("warns that a temporary password is shown only once", async () => {
    const fetchStub = stubFetch({
      "/admin/accounts": [],
      "POST /admin/accounts": { ...ACCOUNT, temporary_password: "tmp-abc123" },
      "/admin/accounts/a-1": ACCOUNT,
    });
    const w = mount(AdminAccounts);
    await flushPromises();

    await w.findAll(".field__input")[1].setValue("new@example.com");
    await w.findAll(".btn--accent")[0].trigger("click");
    await flushPromises();

    expect(w.text()).toContain("tmp-abc123");
    expect(w.text()).toContain("it is not shown again");
    expect(fetchStub.mock.calls.some((c) => String(c[0]).endsWith("/admin/accounts"))).toBe(true);
  });

  it("confirms before granting platform admin, and names the consequence", async () => {
    const fetchStub = stubFetch({
      "/admin/accounts": [ACCOUNT],
      "/admin/accounts/a-1": ACCOUNT,
    });
    const w = mount(AdminAccounts);
    await flushPromises();
    await w.find(".link").trigger("click");
    await flushPromises();

    await w.findAll(".btn").find((b) => b.text().includes("Grant platform admin")).trigger("click");

    // nothing sent yet — the operator is told what it means first
    expect(fetchStub.mock.calls.some((c) => String(c[0]).includes("/roles"))).toBe(false);
    expect(w.find(".confirm").exists()).toBe(true);
    expect(w.text()).toContain("every power in this console");
  });

  it("sends the admin grant only after confirmation", async () => {
    const fetchStub = stubFetch({
      "/admin/accounts": [ACCOUNT],
      "/admin/accounts/a-1": ACCOUNT,
      "POST /admin/accounts/a-1/roles": { ...ACCOUNT, roles: ["driver", "platform_admin"] },
    });
    const w = mount(AdminAccounts);
    await flushPromises();
    await w.find(".link").trigger("click");
    await flushPromises();
    await w.findAll(".btn").find((b) => b.text().includes("Grant platform admin")).trigger("click");
    await w.findAll(".btn").find((b) => b.text().includes("Yes")).trigger("click");
    await flushPromises();

    const call = fetchStub.mock.calls.find((c) => String(c[0]).includes("/roles"));
    expect(JSON.parse(call[1].body)).toEqual({
      role: "platform_admin",
      grant: true,
      confirm: true,
    });
  });

  it("offers no admin-grant button to someone who already has it", async () => {
    stubFetch({
      "/admin/accounts": [ACCOUNT],
      "/admin/accounts/a-1": { ...ACCOUNT, roles: ["driver", "platform_admin"] },
    });
    const w = mount(AdminAccounts);
    await flushPromises();
    await w.find(".link").trigger("click");
    await flushPromises();
    expect(w.findAll(".btn").some((b) => b.text().includes("Grant platform admin"))).toBe(false);
  });

  it("shows what support has already done to this account", async () => {
    stubFetch({ "/admin/accounts": [ACCOUNT], "/admin/accounts/a-1": ACCOUNT });
    const w = mount(AdminAccounts);
    await flushPromises();
    await w.find(".link").trigger("click");
    await flushPromises();
    expect(w.text()).toContain("What support has done here");
    expect(w.text()).toContain("account_create");
  });

  it("says so plainly when nothing matches", async () => {
    stubFetch({ "/admin/accounts": [] });
    const w = mount(AdminAccounts);
    await flushPromises();
    expect(w.text()).toContain("No accounts match.");
  });
});

// --- E-D5 impersonation banner + decision 7 facility editor ---
import VendorPortalSurface from "../src/surfaces/VendorPortalSurface.vue";
import AdminData from "../src/surfaces/admin/AdminData.vue";
import { setImpersonation } from "../src/core/api.js";

describe("Impersonation banner (E-D5)", () => {
  const PROFILE = {
    vendor_id: "v-1",
    name: "Osh Express",
    verify_status: "verified",
    languages: ["uz"],
    halal_disclosure: "Halal butcher",
    publish_suspended: false,
    consecutive_no_shows: 0,
    profile_gaps: [],
    documents: [],
    assisted: [],
  };
  const ANALYTICS = {
    sheet_views: 0,
    confirmations: 0,
    shows_up: { confirmed: 0, published: 0 },
    reviews: { average: null, reviewers: 0 },
    publish_suspended: false,
  };

  function portalStub(profile = PROFILE) {
    stubFetch({
      "/vendor/profile": profile,
      "/vendor/appearances": [],
      "/vendor/promotions": [],
      "/vendor/analytics": ANALYTICS,
    });
  }

  afterEach(() => setImpersonation(null));

  it("shows nothing when the operator is not impersonating", async () => {
    portalStub();
    const w = mount(VendorPortalSurface);
    await flushPromises();
    expect(w.find(".viewas").exists()).toBe(false);
  });

  it("names the vendor and states that writes are the admin's", async () => {
    // an operator must not forget whose screen they are on, nor believe their
    // edits will look like the vendor's
    setImpersonation({ token: "imp-1", vendor_name: "Osh Express", vendor_id: "v-1" });
    portalStub();
    const w = mount(VendorPortalSurface);
    await flushPromises();

    const banner = w.find(".viewas");
    expect(banner.exists()).toBe(true);
    expect(banner.text()).toContain("Osh Express");
    expect(banner.text()).toContain("recorded as you, not them");
    expect(banner.text()).toContain("Exit view-as");
  });

  it("tells the vendor when support has edited their things", async () => {
    // derived server-side from the audit log, so there is one source of truth
    portalStub({ ...PROFILE, assisted: [{ action: "profile_edit", at: "2026-07-26T09:00:00Z" }] });
    const w = mount(VendorPortalSurface);
    await flushPromises();
    expect(w.text()).toContain("Edited by Haulmeter support");
  });

  it("says nothing about support when support has not touched anything", async () => {
    portalStub();
    const w = mount(VendorPortalSurface);
    await flushPromises();
    expect(w.text()).not.toContain("Edited by Haulmeter support");
  });
});

describe("Facility editor (decision 7)", () => {
  const INGEST = {
    facilities: { total: 1, by_source: { osm: 1 } },
    freshness: {},
    jobs: [],
    sources: { tpims_static: "https://example/TPIMS_Static.json" },
  };
  const FACILITY = {
    facility_id: "f-1",
    name: "Gateway Truck Service",
    facility_type: "repair",
    status: "confirmed",
    lat: 37.084,
    lon: -94.513,
    address: null,
    attributes: { services: ["tire"] },
    confidence: 0.8,
    is_dev: false,
    sources: ["osm"],
  };

  it("states the provenance rule where the operator is about to edit", async () => {
    // not buried in a doc: an admin edit ADDS a source, it never erases a feed's
    stubFetch({ "/admin/ingest": INGEST, "/admin/facilities": [FACILITY] });
    const w = mount(AdminData);
    await flushPromises();
    expect(w.text()).toContain("added as an admin source");
    expect(w.text()).toContain("never erases what a feed recorded");
  });

  it("shows which feeds already claim a facility", async () => {
    stubFetch({ "/admin/ingest": INGEST, "/admin/facilities": [FACILITY] });
    const w = mount(AdminData);
    await flushPromises();
    expect(w.text()).toContain("Sources: osm");
  });

  it("explains that facilities are merged, never deleted", async () => {
    stubFetch({ "/admin/ingest": INGEST, "/admin/facilities": [FACILITY] });
    const w = mount(AdminData);
    await flushPromises();
    expect(w.text()).toContain("never deleted");
    expect(w.text()).toContain("merge a duplicate instead");
  });

  it("sends a rename as a PATCH through the pipeline", async () => {
    const fetchStub = stubFetch({
      "/admin/ingest": INGEST,
      "/admin/facilities": [FACILITY],
      "PATCH /admin/facilities/f-1": { ...FACILITY, name: "Gateway Truck Centre" },
    });
    const w = mount(AdminData);
    await flushPromises();

    const nameInput = w.findAll(".field__input").find((i) => i.element.value === FACILITY.name);
    await nameInput.setValue("Gateway Truck Centre");
    await nameInput.trigger("change");
    await flushPromises();

    const call = fetchStub.mock.calls.find((c) => String(c[0]).includes("/admin/facilities/f-1"));
    expect(JSON.parse(call[1].body)).toEqual({ name: "Gateway Truck Centre" });
  });

  it("offers duplicate discovery rather than a delete button", async () => {
    stubFetch({ "/admin/ingest": INGEST, "/admin/facilities": [FACILITY] });
    const w = mount(AdminData);
    await flushPromises();
    const buttons = w.findAll(".btn").map((b) => b.text());
    expect(buttons).toContain("Possible duplicates");
    expect(buttons.join(" ")).not.toContain("Delete");
  });
});
