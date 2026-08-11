// AI-CONTEXT: the pre-arrival screen and the arrival itself (§23 entry 138).
//
// Three things the owner asked for, and the third turned out to be a defect rather than
// a feature:
//
//   1. before arrival the evidence card is four rows of "not yet" between the Meter and
//      the one action the screen exists to offer — it pushed "I have arrived" off a
//      360 dp screen;
//   2. tapping it from far away should ask, not silently record;
//   3. the arrival coordinates should be recorded when they differ from the load's
//      address — which they always could have been, because the client never sent its
//      position at all and the SERVER filled the gap with the facility's own
//      coordinates. See api/tests/api/test_load_api.py for that half.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import { __resetStateForTests } from "../src/core/state.js";
import { lastFix, lastEvents } from "../src/core/location.js";
import { setActiveStop } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const STOP = "11111111-2222-3333-4444-555555555555";
const FIX = { lat: 32.7767, lon: -96.797, accuracyM: 12.5, speedMps: 0 };

// pre-arrival: the Meter counts down to the appointment and the ladder offers "arrive"
const PRE_ARRIVAL = {
  stop_id: STOP,
  facility_name: "Harvest Foods DC",
  counterparty: "Bolt Logistics",
  appointment: "2099-01-01T14:00:00+00:00",
  appointment_end: "2099-01-01T16:00:00+00:00",
  appointment_source: "rate_con_parse",
  phase: "not_arrived",
  free_time_minutes: 120,
  free_time_remaining_seconds: 7200,
  detention_seconds: 0,
  rate_cents_per_hour: 7500,
  detention_cents: 0,
  notice_sent: false,
  notice_delivery: "not_sent",
  bol_captured: false,
  photos_captured: 0,
  photos_required: 4,
  checklist: [
    { item: "bol", kind: "document", captured: false, required: true },
    { item: "pod", kind: "document", captured: false, required: true },
  ],
  filed: false,
  on_time: null,
  next_stop: null,
  load_id: "aaaa0000-0000-0000-0000-000000000001",
  counterparty_email: "ap@bolt.example",
};

function jsonOk(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function stub({ meter = PRE_ARRIVAL, arrive } = {}) {
  return vi.fn((url, opts) => {
    const u = String(url);
    if (u.includes("/arrive") && opts?.method === "POST") {
      return arrive ? arrive(opts) : jsonOk({ arrived: true, claim_id: "c-1" });
    }
    if (u.includes("/meter")) return jsonOk(meter);
    if (u.includes("/protection/stop-packets")) return jsonOk([]);
    return jsonOk({});
  });
}

async function mountLoad(fetchStub) {
  vi.stubGlobal("fetch", fetchStub);
  setToken("tok");
  setActiveStop(STOP);
  const router = createRouter({ history: createMemoryHistory(), routes });
  router.push("/load");
  await router.isReady();
  const w = mount(LoadSurface, { global: { plugins: [router] } });
  await flushPromises();
  return w;
}

afterEach(() => {
  vi.unstubAllGlobals();
  __resetStateForTests();
  lastFix.value = null;
  lastEvents.value = [];
  setActiveStop(null);
  logout();
});

describe("Before the driver arrives, the screen is the Meter and one action", () => {
  it("collapses the evidence card to a single row", async () => {
    const w = await mountLoad(stub());

    const row = w.find(".collapsed");
    expect(row.exists()).toBe(true);
    expect(row.text()).toContain(en["load.paperwork_for_stop"]);
    expect(w.find(".checklist").exists()).toBe(false); // the four "not yet" rows are shut
  });

  it("says how much of it is done, so the row is not a mystery", async () => {
    const w = await mountLoad(stub());
    // a figure, in the "photos 2/4" shape §10.2 already specifies — a denominator is
    // what turns a task with no end into a task with an end.
    expect(w.find(".collapsed__count").text()).toBe("0/2");
  });

  it("keeps I have arrived on the screen, above the fold", async () => {
    // the whole point of collapsing. The CTA is the last thing rendered, so "is it
    // present and is the card shut" is the assertion a DOM test can actually make;
    // the layout harness measures the geometry at 360 dp.
    const w = await mountLoad(stub());
    const cta = w.findAll(".cta").filter((b) => !b.classes().includes("cta--text"))[0];
    expect(cta.text()).toContain(en["load.arrive"]);
  });

  it("opens on tap, so nothing inside it becomes unreachable", async () => {
    // the broker email field lives in that card, and the drive TO the dock is exactly
    // when a driver can fix the address the detention notice will go to.
    const w = await mountLoad(stub());
    await w.find(".collapsed").trigger("click");
    await flushPromises();

    expect(w.find(".checklist").exists()).toBe(true);
    expect(w.find(".bmail, .checklist__email").exists()).toBe(true);
    expect(w.find(".collapsed").exists()).toBe(false);
  });

  it("closes again from the header it opened into", async () => {
    // `evidenceOpen` was one-way: a driver who tapped the row to check the broker
    // address could not put it back, so a screen they were given a way out of quietly
    // became the screen they were stuck on.
    const w = await mountLoad(stub());
    await w.find(".collapsed").trigger("click");
    await flushPromises();
    expect(w.find(".checklist").exists()).toBe(true);

    await w.find(".card__toggle").trigger("click");
    await flushPromises();

    expect(w.find(".checklist").exists()).toBe(false);
    expect(w.find(".collapsed").exists()).toBe(true);
    expect(w.find(".collapsed__count").text()).toBe("0/2"); // and it comes back intact
  });

  it("names the same thing open and shut", async () => {
    // one object opening and closing, not two rows that happen to swap places.
    const w = await mountLoad(stub());
    const shut = w.find(".collapsed").text();
    await w.find(".collapsed").trigger("click");
    await flushPromises();

    expect(w.find(".card__toggle").text()).toContain(en["load.paperwork_for_stop"]);
    expect(shut).toContain(en["load.paperwork_for_stop"]);
  });

  it("has no collapse control once the driver has arrived", async () => {
    // §10.2 wants this open at the dock — it is the job list there, not clutter, and a
    // control that hides it would be a way to lose the checklist mid-stop.
    const w = await mountLoad(stub({ meter: { ...PRE_ARRIVAL, phase: "within_free_time" } }));
    expect(w.find(".card__toggle").exists()).toBe(false);
    expect(w.find(".checklist").exists()).toBe(true);
  });

  it("is open by default once the driver has arrived", async () => {
    // after arrival the card is the driver's job list, not clutter.
    const w = await mountLoad(stub({ meter: { ...PRE_ARRIVAL, phase: "within_free_time" } }));
    expect(w.find(".collapsed").exists()).toBe(false);
    expect(w.find(".checklist").exists()).toBe(true);
  });
});

describe("Tapping I have arrived", () => {
  it("sends the device's OWN fix, not nothing", async () => {
    // the defect underneath the owner's third ask: this posted an empty body, and the
    // server filled the gap with the FACILITY'S coordinates — so the position fix a
    // detention claim rests on was a reading of where the warehouse is.
    lastFix.value = FIX;
    const s = stub();
    const w = await mountLoad(s);
    await w.findAll(".cta").filter((b) => !b.classes().includes("cta--text"))[0].trigger("click");
    await flushPromises();

    const call = s.mock.calls.find((c) => String(c[0]).includes("/arrive"));
    const body = JSON.parse(call[1].body);
    expect(body.lat).toBe(FIX.lat);
    expect(body.lon).toBe(FIX.lon);
    expect(body.accuracy_m).toBe(12.5);
  });

  it("sends NO position rather than a substitute when the phone has no fix", async () => {
    // an absent reading is a fact. Filling it in is the defect this entry removes.
    lastFix.value = null;
    const s = stub();
    const w = await mountLoad(s);
    await w.findAll(".cta").filter((b) => !b.classes().includes("cta--text"))[0].trigger("click");
    await flushPromises();

    const body = JSON.parse(s.mock.calls.find((c) => String(c[0]).includes("/arrive"))[1].body);
    expect(body.lat).toBeNull();
    expect(body.lon).toBeNull();
  });

  it("asks before recording when the driver looks far from the dock", async () => {
    lastFix.value = FIX;
    const s = stub({
      arrive: () =>
        Promise.resolve({
          ok: false,
          status: 409,
          json: () =>
            Promise.resolve({
              detail: { reason: "too_far", distance_m: 13700, facility_name: "Harvest Foods DC" },
            }),
        }),
    });
    const w = await mountLoad(s);
    await w.findAll(".cta").filter((b) => !b.classes().includes("cta--text"))[0].trigger("click");
    await flushPromises();

    expect(w.text()).toContain(en["load.far_title"]);
    expect(w.text()).toContain("8.5 mi"); // §12.5: units are never localised
    expect(w.text()).toContain("Harvest Foods DC");
  });

  it("lets the driver say they are there anyway, and records it", async () => {
    // a gate queue at a big DC is legitimately arriving. The warning is a question,
    // never a gate — a block would strand the driver this button exists for.
    lastFix.value = FIX;
    let confirmedCall = null;
    const s = stub({
      arrive: (opts) => {
        const body = JSON.parse(opts.body);
        if (body.confirmed) {
          confirmedCall = body;
          return jsonOk({ arrived: true, claim_id: "c-1" });
        }
        return Promise.resolve({
          ok: false,
          status: 409,
          json: () =>
            Promise.resolve({
              detail: { reason: "too_far", distance_m: 13700, facility_name: "Harvest Foods DC" },
            }),
        });
      },
    });
    const w = await mountLoad(s);
    await w.findAll(".cta").filter((b) => !b.classes().includes("cta--text"))[0].trigger("click");
    await flushPromises();

    const go = w.findAll(".cta").find((b) => b.text().includes(en["load.far_go"]));
    expect(go, "the confirm button is missing").toBeTruthy();
    await go.trigger("click");
    await flushPromises();

    expect(confirmedCall).toBeTruthy();
    expect(confirmedCall.lat).toBe(FIX.lat); // the position rides along with the answer
    expect(w.text()).not.toContain(en["load.far_title"]); // and the question is done
  });

  it("Not yet closes the question without recording anything", async () => {
    lastFix.value = FIX;
    const s = stub({
      arrive: () =>
        Promise.resolve({
          ok: false,
          status: 409,
          json: () =>
            Promise.resolve({ detail: { reason: "too_far", distance_m: 13700 } }),
        }),
    });
    const w = await mountLoad(s);
    await w.findAll(".cta").filter((b) => !b.classes().includes("cta--text"))[0].trigger("click");
    await flushPromises();

    await w.findAll(".cta--text").find((b) => b.text().includes(en["load.far_back"])).trigger("click");
    await flushPromises();

    expect(w.text()).not.toContain(en["load.far_title"]);
    const confirmed = s.mock.calls
      .filter((c) => String(c[0]).includes("/arrive"))
      .map((c) => JSON.parse(c[1].body))
      .filter((b) => b.confirmed);
    expect(confirmed).toHaveLength(0);
  });

  it("a real failure says so instead of asking a question", async () => {
    // §12.4, and the distinction that matters: a 409 is the server asking, a 500 is the
    // server failing, and telling a driver "are you at the dock?" for the second would
    // send them looking for the wrong fix.
    lastFix.value = FIX;
    const s = stub({
      arrive: () =>
        Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }),
    });
    const w = await mountLoad(s);
    await w.findAll(".cta").filter((b) => !b.classes().includes("cta--text"))[0].trigger("click");
    await flushPromises();

    expect(w.text()).toContain(en["load.arrive_failed"]);
    expect(w.text()).not.toContain(en["load.far_title"]);
  });
});
