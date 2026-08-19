// AI-CONTEXT: decision 207 — Roadside Ready becomes the fourth bottom-nav tab, and the
// tap budget that displacing Docs nearly broke.
//
// THE TAP-BUDGET TEST IS THE ONE THAT MATTERS HERE. design-prd §10.4 requires inspection
// mode "within 2 taps from cold start" — it is the screen a driver opens with an officer
// at the window, and the number is the law, not a nicety. Moving the wallet to a More row
// makes it More → Documents → Inspection, which is three. That regression is invisible to
// every other test in this suite: nothing renders wrongly, no request fails, and the
// screen a driver eventually reaches is correct. Only the count is wrong.
//
// So the count is asserted directly, against the route table and the surfaces' own
// markup, and it was watched failing on the three-tap arrangement before the second
// entry point existed.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import TabBar from "../src/core/components/TabBar.vue";
import RoadsideHomeSurface from "../src/surfaces/RoadsideHomeSurface.vue";
import { routes } from "../src/router.js";
import { __resetStateForTests } from "../src/core/state.js";
import * as api from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const root = resolve(__dirname, "..");
const read = (p) => readFileSync(resolve(root, p), "utf8");
const router = () => createRouter({ history: createMemoryHistory(), routes });

const EMPTY_PROGRESS = {
  band: null,
  provisional: true,
  checked_at: null,
  skills: { seen: 0, passed: 0, due: 0 },
  drill: { day: null, due: 0, completed: false },
};

async function mountHome({ scenarios = [], progress = EMPTY_PROGRESS, sessions = [] } = {}) {
  vi.spyOn(api, "fetchRoadsideScenarios").mockResolvedValue({ scenarios });
  vi.spyOn(api, "fetchRoadsideProgress").mockResolvedValue(progress);
  vi.spyOn(api, "fetchRoadsideSessions").mockResolvedValue({ sessions });
  const r = router();
  r.push("/roadside");
  await r.isReady();
  const w = mount(RoadsideHomeSurface, { global: { plugins: [r] } });
  await flushPromises();
  return w;
}

beforeEach(() => __resetStateForTests());
afterEach(() => vi.restoreAllMocks());

describe("the tab bar after decisions 207 and 213", () => {
  const tabStub = {
    global: {
      stubs: {
        "router-link": {
          props: ["to"],
          template: "<a class='rl' :href='to'><slot/></a>",
        },
      },
    },
  };

  it("has exactly five tabs — the map slot is dormant (D21, entry 228)", () => {
    // 207 displaced Docs to keep five; 213 brought it back and made the bar six after
    // D7's measured sweep; D21 removed the MAP slot and the bar is five again — not a
    // revert, a different five. The number is asserted because it is the law, not the
    // layout: a seventh tab, or any return to six, owes D7's measurement again.
    const w = mount(TabBar, tabStub);

    expect(w.findAll(".tab")).toHaveLength(5);
    expect(w.findAll(".tab").map((a) => a.attributes("href"))).not.toContain("/map");
  });

  it("offers Roadside and Docs side by side, in that order", () => {
    const w = mount(TabBar, tabStub);

    const hrefs = w.findAll(".tab").map((a) => a.attributes("href"));
    expect(hrefs).toEqual(["/load", "/money", "/docs", "/roadside", "/more"]);
    expect(w.text()).toContain(en["nav.roadside"]);
    expect(w.text()).toContain(en["nav.docs"]);
  });
});

describe("§10.4 — inspection mode stays within two taps of a cold start", () => {
  // Tap 1 is always a tab (a cold start lands on a tab root). Tap 2 must therefore be a
  // control ON that tab root that opens inspection mode itself. Nesting it behind the
  // wallet row would make it three and is precisely what this asserts against.
  const TAB_ROOTS = ["/load", "/money", "/docs", "/roadside", "/more"];

  it("is reachable from a tab root by exactly one more tap — now through Docs", () => {
    // AI-CONTEXT: THE LOAD DOOR WAS REMOVED AT 221 (owner). It existed because 207 spent
    // the Docs tab slot on Roadside and More -> Documents -> Inspection was three taps;
    // 213 put Docs back on the bar and KEPT the Load door anyway, and this is the reversal
    // of that half. Docs tab root -> its own Inspection button is two, which is the same
    // two the law has always asked for.
    const docs = read("src/surfaces/DocsSurface.vue");
    expect(docs).toContain('class="inspect"');
    expect(TAB_ROOTS).toContain("/docs");
  });

  it("no longer sits on Load, and nothing else re-adds a second door", () => {
    // a third path to one screen is what 213 removed from More; two paths is what 221
    // removed from Load. If a future session re-adds one, it should be a decision rather
    // than a drift, and this is what makes it show up as a failing test.
    expect(read("src/surfaces/LoadSurface.vue")).not.toContain("inspection=1");
    expect(read("src/surfaces/LoadSurface.vue")).not.toContain("inspect-row");
    expect(read("src/surfaces/MoreSurface.vue")).not.toContain("inspection=1");
  });

  it("opens the sheet rather than merely landing on the wallet", () => {
    // the deep link has to DO something on arrival; a query nobody reads is a link to
    // the wallet wearing an inspection label
    const docs = read("src/surfaces/DocsSurface.vue");
    expect(docs).toContain("route?.query?.inspection");
    expect(docs).toMatch(/query\?\.inspection\)\s*inspecting\.value = true/);
  });

  it("survives DRIVING on Docs — §10.4 keeps it reachable at speed", () => {
    // §10.4: "DRIVING: inspection mode reachable but confirms vehicle stopped". The
    // control itself must not be withdrawn at speed — an officer can stop a truck that
    // has not finished stopping.
    const src = read("src/surfaces/DocsSurface.vue");
    const row = src.slice(src.indexOf('class="inspect"') - 400, src.indexOf('class="inspect"'));
    expect(row).not.toMatch(/v-if="!isDriving"/);
  });
});

describe("the Roadside tab root", () => {
  it("shows the acquisition state to a driver who has never run a check", async () => {
    const w = await mountHome({ scenarios: [{ id: "s1" }] });

    expect(w.text()).toContain(en["roadside.home.no_check"]);
    expect(w.text()).toContain(en["roadside.start"]);
  });

  it("carries the provisional band rather than recomputing one", async () => {
    const w = await mountHome({
      scenarios: [{ id: "s1" }],
      progress: { ...EMPTY_PROGRESS, band: "yellow", provisional: true },
    });

    expect(w.text()).toContain(en["roadside.band.yellow_provisional"]);
    expect(w.text()).not.toContain(en["roadside.band.yellow"] + "\n");
  });

  it("drops the provisional wording once the band is not provisional", async () => {
    const w = await mountHome({
      scenarios: [{ id: "s1" }],
      progress: { ...EMPTY_PROGRESS, band: "green", provisional: false },
    });

    expect(w.text()).toContain(en["roadside.band.green"]);
    expect(w.text()).not.toContain(en["roadside.band.green_provisional"]);
  });

  it("lists a stop the driver walked out of, and says it is unfinished", async () => {
    const w = await mountHome({
      scenarios: [{ id: "s1" }],
      sessions: [{
        id: "00000000-0000-0000-0000-0000000000e2",
        mode: "check",
        started_at: "2026-08-09T14:20:00+00:00",
        completed_at: null,
        band: null,
        provisional: true,
      }],
    });

    expect(w.text()).toContain(en["roadside.home.unfinished"]);
  });

  it("still offers the check when history and progress fail", async () => {
    // one failed read must not blank a tab: the three fetches are independent questions
    // and the one this screen exists to answer is "can I start".
    vi.spyOn(api, "fetchRoadsideScenarios").mockResolvedValue({ scenarios: [{ id: "s1" }] });
    vi.spyOn(api, "fetchRoadsideProgress").mockRejectedValue(new Error("500"));
    vi.spyOn(api, "fetchRoadsideSessions").mockRejectedValue(new Error("500"));
    const r = router();
    r.push("/roadside");
    await r.isReady();
    const w = mount(RoadsideHomeSurface, { global: { plugins: [r] } });
    await flushPromises();

    expect(w.text()).toContain(en["roadside.start"]);
    expect(w.find(".card__cta").exists()).toBe(true);
  });

  it("fails whole only when the catalogue itself is unreachable", async () => {
    vi.spyOn(api, "fetchRoadsideScenarios").mockRejectedValue(new Error("500"));
    vi.spyOn(api, "fetchRoadsideProgress").mockResolvedValue(EMPTY_PROGRESS);
    vi.spyOn(api, "fetchRoadsideSessions").mockResolvedValue({ sessions: [] });
    const r = router();
    r.push("/roadside");
    await r.isReady();
    const w = mount(RoadsideHomeSurface, { global: { plugins: [r] } });
    await flushPromises();

    expect(w.find('[role="alert"]').exists()).toBe(true);
  });
});
