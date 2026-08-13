// AI-CONTEXT: §15.1's "queued items show a subtle pending glyph", built for the first
// time — and it is the honest form of the optimistic update the owner asked for.
//
// The collision it resolves: §23 entry 136 already ruled that a card must not vanish
// "while the write sits in a queue", because that "would tell a driver their decision is
// recorded when it is not". Entry 131 removed `livePins ?? SAMPLE_PINS` for the same
// reason. Showing a state the server has not reached is the honesty defect this codebase
// keeps paying to remove, and evidence backing a detention claim is the worst place for it.
//
// But a photograph the driver has just taken EXISTS — it is on their phone, in their
// hand. Rendering it immediately is a true statement about a local fact, not a guess
// about the server, and the glyph carries exactly the part that is still uncertain.
//
// Before this, a queued photo appeared NOWHERE: the only sync signal in the product is a
// global count on the status strip, so a driver walking a six-shot sequence in a dead
// zone watched a step counter advance past photographs they had no evidence existed.
// AI-CONTEXT: a real IndexedDB is required, not incidental. happy-dom implements none,
// and without one a "dead zone" capture cannot be stashed either — so it is CAPTURE_NOT_
// STORED rather than queued, and the pending-glyph cases would be asserting the lost path
// while claiming to assert the queued one.
import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import ConditionSurface from "../src/surfaces/ConditionSurface.vue";
import { setToken, logout, setActiveStop } from "../src/core/api.js";
import { __resetIdbForTests } from "../src/core/idb.js";
import en from "../src/core/i18n/en.json";

vi.mock("vue-router", () => ({ useRouter: () => ({ back: vi.fn(), push: vi.fn() }) }));

const SEQUENCE = ["trailer_exterior", "seals"];

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

function stubApi({ photoResponds }) {
  return vi.fn().mockImplementation((url) => {
    const u = String(url);
    if (u.includes("/condition/start")) {
      return jsonOk({ capture_id: "cap-1", sequence: SEQUENCE });
    }
    if (u.includes("/photo")) return photoResponds();
    return jsonOk({});
  });
}

async function shoot(w) {
  const input = w.find(".shoot__input");
  input.element.files = [new File(["x"], "shot.jpg", { type: "image/jpeg" })];
  await input.trigger("change");
  await flushPromises();
  await flushPromises();
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory();
  __resetIdbForTests();
  setToken("tok-glyph");
  setActiveStop("stop-1");
  globalThis.URL.createObjectURL = vi.fn(() => "blob:local-shot");
  globalThis.URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  logout();
  vi.unstubAllGlobals();
});

describe("a photograph the driver just took", () => {
  it("appears immediately, carrying a pending glyph until the server confirms", async () => {
    // a dead zone: the write queues, so the photograph is on the phone and nowhere else
    vi.stubGlobal("fetch", stubApi({ photoResponds: () => Promise.reject(new Error("offline")) }));
    const w = mount(ConditionSurface);
    await flushPromises();

    await shoot(w);

    const shots = w.findAll(".shots__item");
    expect(shots, "the capture must be on screen at once").toHaveLength(1);
    expect(shots[0].find("img").attributes("src")).toBe("blob:local-shot");
    expect(
      shots[0].find(".shots__pending").exists(),
      "§15.1: a queued item wears the glyph",
    ).toBe(true);
  });

  it("drops the glyph once the server has it", async () => {
    vi.stubGlobal("fetch", stubApi({ photoResponds: () => jsonOk({ artifact_id: "a-1" }) }));
    const w = mount(ConditionSurface);
    await flushPromises();

    await shoot(w);

    expect(w.findAll(".shots__item")).toHaveLength(1);
    expect(
      w.find(".shots__pending").exists(),
      "a confirmed photograph must not keep saying it is waiting",
    ).toBe(false);
  });

  it("says it is waiting in WORDS too, not only with a glyph", async () => {
    // §16: the glyph is aria-hidden, so the state has to reach a screen reader through
    // the only text the element has. A visual-only signal is not a signal.
    vi.stubGlobal("fetch", stubApi({ photoResponds: () => Promise.reject(new Error("offline")) }));
    const w = mount(ConditionSurface);
    await flushPromises();

    await shoot(w);

    expect(w.find(".shots__img").attributes("alt")).toContain(en["docs.cap_queued"]);
  });

  it("takes the photograph back off the strip when it was stored NOWHERE", async () => {
    // the one case where showing it would be the lie: `CAPTURE_NOT_STORED` means the
    // bytes reached neither the server nor the phone, so leaving the thumbnail up would
    // have the product asserting it holds evidence it does not have.
    vi.stubGlobal(
      "fetch",
      stubApi({ photoResponds: () => Promise.reject(new Error("offline")) }),
    );
    const broken = new IDBFactory();
    broken.open = () => {
      throw new Error("no storage");
    };
    globalThis.indexedDB = broken;
    __resetIdbForTests();

    const w = mount(ConditionSurface);
    await flushPromises();
    await shoot(w);

    expect(w.findAll(".shots__item"), "nothing may be shown for a capture that was lost").toHaveLength(0);
    expect(w.find(".cond__lost").exists(), "§15.4: and it says so").toBe(true);
  });
});
