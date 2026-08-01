// AI-CONTEXT: A1 req 1 says the capture checklist "is configuration (F13), not code".
// That is only true if an operator can FIND it and CHANGE it in the console.
//
// Two things were in the way, and both were measured before either was built:
//   1. the panel rendered `body.entries` — rows that EXIST. A key nobody had set yet
//      appeared nowhere, and the checklist is the first config any component reads, so
//      it would have shipped invisible.
//   2. the editor is one text input. The checklist value is an OBJECT; `v-model` on it
//      renders "[object Object]" and saving writes that string back, destroying the
//      config an operator opened the page to adjust.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import AdminFlags from "../src/surfaces/admin/AdminFlags.vue";
import { setToken, logout } from "../src/core/api.js";

const CHECKLIST = { pickup: ["bol", "seal"], delivery: ["bol", "pod"] };

const ROUTES = {
  "/admin/flags": [],
  "/admin/config/scopes": ["global"],
  "/admin/config": {
    scope: "global",
    entries: { "f02.dedupe_radius_m": 60 },
    provenance: {},
    declared: {
      "a01.capture_checklist": {
        default: CHECKLIST,
        description: "Capture checklist per stop type (A1 req 1)",
        set: false,
        value: CHECKLIST,
      },
    },
  },
};

function stubFetch(routeMap, sink) {
  const fn = vi.fn().mockImplementation((url, opts) => {
    const path = String(url).replace("http://localhost:8008", "").split("?")[0];
    if (opts?.method === "POST" && path === "/admin/config") {
      sink.push(JSON.parse(opts.body));
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve(path in routeMap ? routeMap[path] : {}),
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => setToken("tok-admin"));
afterEach(() => {
  vi.unstubAllGlobals();
  logout();
});

describe("Admin config — what is TUNABLE, not only what is tuned", () => {
  it("lists a declared key nobody has set yet", async () => {
    stubFetch(ROUTES, []);
    const w = mount(AdminFlags);
    await flushPromises();
    expect(w.text()).toContain("a01.capture_checklist");
    w.unmount();
  });

  it("renders an object value as editable JSON, not [object Object]", async () => {
    stubFetch(ROUTES, []);
    const w = mount(AdminFlags);
    await flushPromises();
    const values = w.findAll(".field__input").map((i) => i.element.value);
    expect(values.some((v) => v.includes("[object Object]"))).toBe(false);
    expect(values.some((v) => v.includes('"delivery"'))).toBe(true);
    w.unmount();
  });

  it("saves an edited object as an OBJECT, not as a string", async () => {
    // the destructive half: a JSON string round-tripped as text turns a dict into a
    // quoted blob, and `capture_checklist` would read it as a list of characters.
    const posted = [];
    stubFetch(ROUTES, posted);
    const w = mount(AdminFlags);
    await flushPromises();
    const row = w
      .findAll("tr")
      .find((r) => r.text().includes("a01.capture_checklist"));
    await row.find(".field__input").setValue('{"delivery": ["bol", "pod", "lumper_receipt"]}');
    await row.find(".btn").trigger("click");
    await flushPromises();
    expect(posted).toHaveLength(1);
    expect(posted[0].value).toEqual({ delivery: ["bol", "pod", "lumper_receipt"] });
    w.unmount();
  });

  it("refuses to save malformed JSON rather than storing the broken text", async () => {
    const posted = [];
    stubFetch(ROUTES, posted);
    const w = mount(AdminFlags);
    await flushPromises();
    const row = w
      .findAll("tr")
      .find((r) => r.text().includes("a01.capture_checklist"));
    await row.find(".field__input").setValue('{"delivery": [');
    await row.find(".btn").trigger("click");
    await flushPromises();
    expect(posted).toHaveLength(0);
    expect(row.text()).toContain("JSON");
    w.unmount();
  });

  it("still keeps scalars scalar", async () => {
    // §23's existing lesson, not to be undone: a config read as "28" where 28 was meant
    // is a silent type change that only shows up as odd behaviour later.
    const posted = [];
    stubFetch(ROUTES, posted);
    const w = mount(AdminFlags);
    await flushPromises();
    const row = w.findAll("tr").find((r) => r.text().includes("f02.dedupe_radius_m"));
    await row.find(".field__input").setValue("45");
    await row.find(".btn").trigger("click");
    await flushPromises();
    expect(posted[0].value).toBe(45);
    w.unmount();
  });
});
