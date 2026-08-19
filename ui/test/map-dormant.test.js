// AI-CONTEXT: the proof of the map-dormancy slice (owner decision D21, §23 entry 228).
//
// The map is DORMANT, not deleted: every map component and its tests stay in the tree and
// stay green, because dormant code keeping its proofs is the entire argument for dormancy
// over deletion. What these assert is the NAVIGATION truth — that no driver-visible path
// still points at a surface no tab can reach — and the one coupling the flip must not
// break: M11's ghostwriter, which the Money tab's chase flow is built on.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import TabBar from "../src/core/components/TabBar.vue";
import MoneySurface from "../src/surfaces/MoneySurface.vue";
import { routes, MAP_DORMANT } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const jsonOk = (b) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) });

function testRouter() {
  return createRouter({ history: createMemoryHistory(), routes });
}

const tabStub = {
  global: { stubs: { RouterLink: { props: ["to"], template: '<a class="tab" :href="to"><slot /></a>' } } },
};

afterEach(() => { vi.unstubAllGlobals(); logout(); });

describe("The map is dormant (D21)", () => {
  it("is flagged in ONE greppable place, so reactivation is not a hunt", () => {
    expect(MAP_DORMANT).toBe(true);
  });

  it("lands a signed-in driver on /load, not /map", async () => {
    const r = testRouter();
    await r.push("/");
    await r.isReady();

    expect(r.currentRoute.value.path).toBe("/load");
  });

  it("sends a bookmarked /map somewhere real rather than 404ing", async () => {
    // the driver who saved the tab before the flip is the person this exists for
    const r = testRouter();
    await r.push("/map");
    await r.isReady();

    expect(r.currentRoute.value.path).toBe("/load");
  });

  it("renders five tabs and no link to the map", () => {
    const w = mount(TabBar, tabStub);
    const hrefs = w.findAll(".tab").map((a) => a.attributes("href"));

    expect(hrefs).toEqual(["/load", "/money", "/docs", "/roadside", "/more"]);
    expect(w.text()).not.toContain(en["nav.map"]);
  });

  it("keeps the Money tab's chase on the ghostwriter — the M11 coupling this protects", async () => {
    // `m11_voice` is NOT touched by the flip: only the map's mic ENTRY goes. The chase
    // flow (§23 entry 142) routes through the ghostwriter so the driver sends the message
    // themselves, and that must survive the map going dark.
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn((url) => {
      const u = String(url);
      if (u.includes("/accessorial/owed")) return jsonOk([{
        receivable_id: "r1", kind: "detention", state: "invoiced", amount_cents: 18750,
        aging_days: 12, counterparty_name: "Blue Road", facility_name: "Dock",
        stop_id: "s1", history: [], fee_cents: 0, net_cents: 18750,
      }]);
      if (u.includes("/accessorial/unfiled")) return jsonOk([]);
      if (u.includes("/money/earnings")) return jsonOk({ ddd_cents: 0, recovered_cents: 0, fuel_saved_cents: 0, flagged_cents: 0 });
      if (u.includes("/me")) return jsonOk({ verified: false });
      return jsonOk({});
    }));
    const r = testRouter();
    r.push("/money");
    await r.isReady();
    const w = mount(MoneySurface, { global: { plugins: [r] } });
    await flushPromises();

    await w.find(".rows .row").trigger("click");
    await flushPromises();
    const chase = w.findAll(".cm .cta").find((b) => b.text().includes(en["money.act_chase"]));
    expect(chase, "the chase control must survive the map flip").toBeTruthy();
    await chase.trigger("click");
    await flushPromises();

    expect(w.text()).toContain(en["ghost.title"]);
  });
});
