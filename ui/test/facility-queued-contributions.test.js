// AI-CONTEXT: the question a driver TYPED, and the review they wrote, had nowhere to go.
//
// Entry 150 gave §15.1's glyph to the wallet. This is the same defect one surface over,
// and in one respect it is worse: a photograph at least still exists in the phone's
// camera roll, while these two are text a driver composed in this app and nowhere else.
//
// `onAsk` clears the input, closes the sheet and calls `loadQuestions()` — which reads the
// SERVER. Offline the question is not there, and the fetch that would have shown it fails
// too, so the section renders §15.4's "No connection" line. The driver is looking at a
// screen that says the questions could not be loaded, having just written one. `onReview`
// is the same shape against the reviews list.
//
// Both writes are safe — `queuedPost` stored them with a stable idempotency key — so the
// only thing missing was the app admitting it. The rule the wallet paid for is applied
// here from the start: the queued item renders OUTSIDE the section's load-state chain,
// because offline is exactly when that chain is in its failed branch and exactly when the
// queued item exists.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import FacilityProfileSurface from "../src/surfaces/FacilityProfileSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout, askQuestion, submitReview, queueForTests } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

// AI-CONTEXT: FLAT. The surface reads `profile.name` and `profile.reviews` directly —
// an older fixture in `ui-components.test.js` nests it under `facility`, which renders an
// empty `<h1>` and no reviews list while every assertion in that file still passes,
// because none of them read the name. Caught here by `w.text()` coming back "".
const PROFILE = {
  id: "f-1",
  name: "Harvest Foods DC",
  ratings: { overall: 3.8, review_count: 2, per_aspect: {} },
  reviews: [],
  dwell: { overall: { sample_size: 0, median_seconds: null } },
};

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

/* AI-CONTEXT: the dead zone AS A DRIVER MEETS IT, which is not "every read fails".
 *
 * `apiGet` serves its cache when the network is gone, so a facility page the driver has
 * already opened still renders offline — that is F12 working. The Q&A list is the part
 * that does NOT cache (`fetchQuestions` calls `fetch` directly), so it fails while the
 * page around it is intact. That is the real state: a rendered facility, §15.4's line
 * where the questions were, and a question the driver just wrote.
 *
 * The COLD case — offline on a facility never opened before — is deliberately not covered
 * by this feature. There is no facility name on the screen to attach anything to, and a
 * floating "waiting to sync" block with nothing around it would be a worse answer than
 * the failed line. Stated here rather than discovered as a gap later. */
function cachedOffline() {
  localStorage.setItem("longhaul.cache.profile:f-1", JSON.stringify(PROFILE));
  return vi.fn(() => Promise.reject(new Error("network")));
}

// online for the reads, so the surface LOADS, but the contribution still queues. This
// separates "the row renders" from "the row survives the failed branch".
function readsOnly() {
  return vi.fn((url, opts) => {
    if (opts?.method === "POST") return Promise.reject(new Error("network"));
    const u = String(url);
    if (u.includes("/facility/f-1/profile")) return jsonOk(PROFILE);
    if (u.includes("/community/questions")) return jsonOk([]);
    if (u.includes("/vendors/service-center/")) return jsonOk(null);
    return jsonOk({});
  });
}

function testRouter() {
  return createRouter({ history: createMemoryHistory(), routes });
}

async function mountFacility() {
  const router = testRouter();
  router.push("/facility/f-1");
  await router.isReady();
  const w = mount(FacilityProfileSurface, { global: { plugins: [router] } });
  await flushPromises();
  return w;
}

describe("a queued question and review are on the screen (§15.1)", () => {
  beforeEach(() => {
    localStorage.clear();
    setToken("tok-facility");
  });

  afterEach(() => {
    logout();
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("shows the question the driver typed, marked pending", async () => {
    vi.stubGlobal("fetch", readsOnly());

    const res = await askQuestion("f-1", "Is the north gate open after 8pm?");
    expect(res.queued).toBe(true);
    const w = await mountFacility();

    expect(w.text()).toContain("Is the north gate open after 8pm?");
    expect(w.find(".qa__item--pending").exists()).toBe(true);
    w.unmount();
  });

  it("shows it even when the questions themselves could not be loaded", async () => {
    // THE STATE IT IS FOR. Offline the list fetch fails and §15.4's line takes the
    // section — so a queued question inside that chain renders in every case but this one.
    vi.stubGlobal("fetch", cachedOffline());

    await askQuestion("f-1", "Is the north gate open after 8pm?");
    const w = await mountFacility();

    expect(w.text()).toContain("Is the north gate open after 8pm?");
    expect(w.find(".qa__item--pending").exists()).toBe(true);
    w.unmount();
  });

  it("shows a queued review the same way", async () => {
    vi.stubGlobal("fetch", readsOnly());

    await submitReview("f-1", { overall: 4 }, "Quick in and out, dock 12 is the fast one.");
    const w = await mountFacility();

    expect(w.text()).toContain("Quick in and out, dock 12 is the fast one.");
    expect(w.find(".reviews__item--pending").exists()).toBe(true);
    w.unmount();
  });

  it("shows only THIS facility's queued contributions", async () => {
    /* AI-CONTEXT: the filter that a path check alone cannot make. `/community/questions`
     * carries its facility in the BODY, so every facility page would otherwise show every
     * queued question in the app — including one written about a lot 600 miles away, on
     * the screen a driver is using to decide whether to pull in here. The review path
     * carries the id in the URL instead, so both shapes are exercised. */
    vi.stubGlobal("fetch", readsOnly());
    queueForTests([
      { path: "/community/questions", body: { facility_id: "f-2", text: "Elsewhere entirely" }, opId: "op-a" },
      { path: "/facility/f-2/review", body: { ratings: { overall: 1 }, text: "Another lot" }, opId: "op-b" },
    ]);

    const w = await mountFacility();

    expect(w.text()).not.toContain("Elsewhere entirely");
    expect(w.text()).not.toContain("Another lot");
    expect(w.find(".qa__item--pending").exists()).toBe(false);
    expect(w.find(".reviews__item--pending").exists()).toBe(false);
    w.unmount();
  });

  it("carries the pending glyph, not a second sentence of chrome", async () => {
    // §13.1's restraint and §15.1's "sync completion is silent": the glyph says it, the
    // same Clock in `--text-3` the wallet and the condition sheet already use.
    vi.stubGlobal("fetch", readsOnly());
    await askQuestion("f-1", "Is the north gate open after 8pm?");

    const w = await mountFacility();

    const glyph = w.find(".qa__item--pending .queued__glyph");
    expect(glyph.exists()).toBe(true);
    expect(glyph.attributes("title")).toBe(en["docs.cap_queued"]);
    w.unmount();
  });

  it("skips a queued write it cannot render rather than throwing", async () => {
    // this queue outlives a deploy on a driver's phone (entry 150)
    vi.stubGlobal("fetch", readsOnly());
    queueForTests([
      { path: "/community/questions", body: { facility_id: "f-1" }, opId: "op-notext" },
      { path: "/facility/f-1/review", opId: "op-nobody" },
    ]);

    const w = await mountFacility();

    expect(w.find(".qa__item--pending").exists()).toBe(false);
    expect(w.find(".reviews__item--pending").exists()).toBe(false);
    expect(w.text()).toContain(PROFILE.name);
    w.unmount();
  });
});
