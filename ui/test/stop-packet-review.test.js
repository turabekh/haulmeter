// AI-CONTEXT: A1 requirement 5's screen — "the driver reviews before it sends. Nothing
// leaves silently. A packet the driver did not see is a document they cannot vouch for."
//
// A queue that says "1 packet" and offers Send would satisfy the letter of that and
// none of its point. §11.7's rule — a figure never travels without what produced it —
// applies harder to a document than to a number, because the driver is vouching for it
// under their own name to someone who pays them.
//
// So the screen has to say WHO receives it, WHICH load it belongs to, and WHERE the
// stop was, before the action is reachable at all.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import StopPacketsSurface from "../src/surfaces/StopPacketsSurface.vue";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const PACKET = {
  id: "p-1",
  state: "draft",
  drafted_at: "2026-08-01T12:00:00+00:00",
  reference: "BL-77",
  recipient: "ap@bolt.example",
  counterparty_name: "Bolt Logistics",
  facility_name: "Dock 4",
};

function jsonOk(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function router() {
  return createRouter({ history: createMemoryHistory(), routes });
}

function mountWith(stub) {
  vi.stubGlobal("fetch", stub);
  return mount(StopPacketsSurface, { global: { plugins: [router()] } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  logout();
});

describe("Stop packet review (A1 req 5)", () => {
  it("names the recipient, the load and the stop before offering to send", async () => {
    setToken("tok");
    const w = mountWith(vi.fn(() => jsonOk([PACKET])));
    await flushPromises();

    const text = w.text();
    expect(text).toContain("ap@bolt.example"); // WHO receives it
    expect(text).toContain("BL-77"); // WHICH load
    expect(text).toContain("Dock 4"); // WHERE the stop was
  });

  it("sends only when the driver acts, and says so afterwards", async () => {
    setToken("tok");
    const stub = vi.fn((url, opts) =>
      String(url).includes("/send") && opts?.method === "POST"
        ? jsonOk({ id: "p-1", state: "sent" })
        : jsonOk([PACKET]),
    );
    const w = mountWith(stub);
    await flushPromises();

    expect(stub.mock.calls.some((c) => String(c[0]).includes("/send"))).toBe(false);
    await w.find(".packet__send").trigger("click");
    await flushPromises();
    expect(stub.mock.calls.some((c) => String(c[0]).includes("/protection/stop-packets/p-1/send"))).toBe(true);
  });

  it("an empty queue says what this screen is for, not just nothing", async () => {
    // §15.3: one sentence of purpose. A blank screen tells a driver the app is broken.
    setToken("tok");
    const w = mountWith(vi.fn(() => jsonOk([])));
    await flushPromises();
    expect(w.text()).toContain(en["packet.empty"]);
  });

  it("a deployment that cannot send says so instead of failing silently", async () => {
    // the 503 the API returns when PUBLIC_BASE_URL is unset. §12.4: what happened and
    // what to do — a tap that appears to work and does nothing is the worse outcome.
    setToken("tok");
    const stub = vi.fn((url, opts) =>
      String(url).includes("/send") && opts?.method === "POST"
        ? Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({}) })
        : jsonOk([PACKET]),
    );
    const w = mountWith(stub);
    await flushPromises();
    await w.find(".packet__send").trigger("click");
    await flushPromises();
    expect(w.text()).toContain(en["packet.send_failed"]);
  });
});




// AI-CONTEXT: THE REWORK. A1's automation was correct and invisible.
//
// EXIT drafted the packet server-side and the only thing that said so on the Load tab
// was a text link — "2 waiting" — that NAVIGATED the driver to /protection/packets to
// hunt for their own paperwork. For a driver who is not comfortable with phones, that
// hunt is the whole failure: the work was done and they could not find it.
//
// These assert the card ARRIVES and the review happens WITHOUT leaving the tab. The
// archive still exists (the describe above still mounts it) — this added a door.
import { observeMotion, __resetStateForTests, DRIVING_SUSTAIN_MS } from "../src/core/state.js";
import { lastEvents } from "../src/core/location.js";

const T0 = 1_760_000_000_000;

function mountLoad(stub) {
  vi.stubGlobal("fetch", stub);
  return mount(LoadSurface, { global: { plugins: [router()] } });
}

function packetsOnly(rows) {
  return vi.fn((url) =>
    String(url).includes("/protection/stop-packets") ? jsonOk(rows) : jsonOk({}),
  );
}

describe("Load tab — the paperwork ARRIVES (A1 req 5, the rework)", () => {
  afterEach(() => {
    __resetStateForTests();
    lastEvents.value = [];
  });

  it("says nothing at all when no paperwork is waiting", async () => {
    // absent rather than empty. §10.2's Load tab is dense already, and a permanent
    // "0 waiting" row is noise on the screen a driver reads at a dock.
    setToken("tok");
    const w = mountLoad(packetsOnly([]));
    await flushPromises();
    expect(w.find(".packet-card").exists()).toBe(false);
  });

  it("names the dock the driver just left, in plain language", async () => {
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();

    const card = w.find(".packet-card");
    expect(card.exists()).toBe(true);
    expect(card.text()).toContain("Dock 4");
    expect(card.text()).toContain("BL-77"); // which load, so it is not "some paperwork"
  });

  it("does NOT navigate the driver away to find it", async () => {
    // the exact v1 defect this journey exists to close: a link to /protection/packets
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();

    expect(w.find(".load__packets").exists()).toBe(false);
    expect(w.findAll("a").some((a) => (a.attributes("href") || "").includes("/protection/packets")))
      .toBe(false);
  });

  it("carries ONE action, not two (§8: one action max per card)", async () => {
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();
    expect(w.findAll(".packet-card button").length).toBe(1);
  });

  it("arrives on the EXIT itself, without leaving the tab and coming back", async () => {
    // the packet is drafted when the server sees the EXIT. Reading the queue once on
    // mount meant a driver watching the Meter as they pulled off the dock saw nothing.
    setToken("tok");
    let rows = [];
    const w = mountLoad(
      vi.fn((url) =>
        String(url).includes("/protection/stop-packets") ? jsonOk(rows) : jsonOk({}),
      ),
    );
    await flushPromises();
    expect(w.find(".packet-card").exists()).toBe(false);

    rows = [PACKET];
    lastEvents.value = [{ event_type: "EXIT", facility_id: "f-1" }];
    await flushPromises();

    expect(w.find(".packet-card").exists()).toBe(true);
  });

  // AI-CONTEXT: found by WALKING it (HANDOFF-116), not by the suite.
  //
  // The queue arrives oldest-first, which is right for the archive and wrong for this
  // card: the card claims "You left <facility>", which is about the stop just departed.
  // With two drafts waiting the card announced the new EXIT and opened the sheet for the
  // OLDER stop — whose contents read "Nothing was captured at this stop" while the BOL
  // photographed minutes earlier sat in the newer packet. Same facility, so the headline
  // was identical and nothing on screen distinguished them.
  it("names the stop just LEFT, not the oldest one still waiting", async () => {
    setToken("tok");
    const older = { ...PACKET, id: "p-old", facility_name: "Yesterday Dock", contents: [] };
    const newer = {
      ...PACKET, id: "p-new", facility_name: "Today Dock",
      reference: "BL-99", contents: ["bol"],
    };
    const w = mountLoad(packetsOnly([older, newer])); // API order: oldest first
    await flushPromises();

    const card = w.find(".packet-card");
    expect(card.text()).toContain("Today Dock");
    expect(card.text()).not.toContain("Yesterday Dock");

    await w.find(".packet-card__cta").trigger("click");
    await flushPromises();
    expect(w.find(".review").text()).toContain(en["load.doc.bol"]);
  });

  it("withdraws the Send at speed and says why (Forbidden #11, SM-3)", async () => {
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();

    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    await flushPromises();

    expect(w.find(".packet-card").exists()).toBe(true); // the news is still information
    expect(w.find(".packet-card__cta").exists()).toBe(false);
    expect(w.text()).toContain(en["packet.ready_driving"]);
  });
});

describe("The review sheet — over the Load tab, never away from it (NAV-3)", () => {
  const WITH_CONTENTS = { ...PACKET, contents: ["bol", "cargo_condition"], claim: null };

  async function openSheet(rows, stub) {
    setToken("tok");
    const w = mountLoad(stub || packetsOnly(rows));
    await flushPromises();
    await w.find(".packet-card__cta").trigger("click");
    await flushPromises();
    return w;
  }

  it("shows WHAT is in the packet before offering to send it", async () => {
    // §11.7 applied to a document: the driver is vouching for this under their own
    // name to the person who pays them. "1 packet" and a Send button is not a review.
    const w = await openSheet([WITH_CONTENTS]);
    const text = w.find(".review").text();
    expect(text).toContain(en["load.doc.bol"]);
    expect(text).toContain(en["load.doc.cargo_condition"]);
  });

  it("pre-fills the recipient from the counterparty, and lets the driver change it", async () => {
    const w = await openSheet([WITH_CONTENTS]);
    const input = w.find(".review__input");
    expect(input.element.value).toBe("ap@bolt.example"); // A1 req 6's default
    await input.setValue("night.desk@bolt.example");
    expect(input.element.value).toBe("night.desk@bolt.example"); // ...and editable
  });

  it("sends nothing until the driver acts, then sends to the address they chose", async () => {
    const stub = vi.fn((url, opts) =>
      String(url).includes("/send") && opts?.method === "POST"
        ? jsonOk({ id: "p-1", state: "sent" })
        : jsonOk([WITH_CONTENTS]),
    );
    const w = await openSheet(null, stub);
    expect(stub.mock.calls.some((c) => String(c[0]).includes("/send"))).toBe(false);

    await w.find(".review__input").setValue("night.desk@bolt.example");
    await w.find(".review__send").trigger("click");
    await flushPromises();

    const send = stub.mock.calls.find((c) => String(c[0]).includes("/send"));
    expect(send).toBeTruthy();
    expect(JSON.parse(send[1].body).recipient).toBe("night.desk@bolt.example");
  });

  it("shows the claim as its own section only when one is filed, and says so on the button", async () => {
    // the bundle (owner decision): two labelled sections, ONE Send. §12.2 — the button
    // says exactly what happens, so its label changes with what rides along.
    const packetOnly = await openSheet([WITH_CONTENTS]);
    expect(packetOnly.find(".review__send").text()).toBe(en["packet.send"]);
    expect(packetOnly.find(".review__figure").exists()).toBe(false);

    const bundled = await openSheet([
      { ...WITH_CONTENTS, claim: { id: "c-1", state: "filed", amount_cents: 8750 } },
    ]);
    expect(bundled.find(".review__figure").text()).toContain("87.50");
    expect(bundled.find(".review__send").text()).toBe(en["packet.send_with_claim"]);
  });

  it("the card clears once the packet is sent", async () => {
    const stub = vi.fn((url, opts) =>
      String(url).includes("/send") && opts?.method === "POST"
        ? jsonOk({ id: "p-1", state: "sent" })
        : jsonOk([WITH_CONTENTS]),
    );
    const w = await openSheet(null, stub);
    await w.find(".review__send").trigger("click");
    await flushPromises();
    expect(w.find(".packet-card").exists()).toBe(false);
  });

  it("a deployment that cannot address itself refuses plainly and keeps the packet", async () => {
    // the 503 when PUBLIC_BASE_URL is unset. §12.4: what happened and what to do — and
    // the draft must survive, because the paperwork has not gone anywhere.
    const stub = vi.fn((url, opts) =>
      String(url).includes("/send") && opts?.method === "POST"
        ? Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({}) })
        : jsonOk([WITH_CONTENTS]),
    );
    const w = await openSheet(null, stub);
    await w.find(".review__send").trigger("click");
    await flushPromises();

    expect(w.find(".review__error").text()).toBe(en["packet.send_failed"]);
    expect(w.find(".packet-card").exists()).toBe(true);
  });
});


// AI-CONTEXT: §15.1 — offline is a mode, not an error.
//
// The packet is drafted SERVER-side on EXIT, and a dock is where signal dies. Reading
// the queue through a bare `fetch` meant a driver who left a shipper and lost signal in
// the same minute arrived at a Load tab with no card on it and no way to know their
// paperwork was waiting. It reads through the F12 cache now, like every other GET the
// app depends on.
describe("The card offline (§15.1)", () => {
  it("still renders from cache when the network is gone", async () => {
    setToken("tok");
    let live = true;
    const stub = vi.fn((url) => {
      if (!live) return Promise.reject(new Error("offline"));
      return String(url).includes("/protection/stop-packets") ? jsonOk([PACKET]) : jsonOk({});
    });
    const first = mountLoad(stub);
    await flushPromises();
    expect(first.find(".packet-card").exists()).toBe(true);

    live = false; // the dead zone
    const second = mountLoad(stub);
    await flushPromises();

    expect(second.find(".packet-card").exists()).toBe(true);
    expect(second.find(".packet-card").text()).toContain("Dock 4");
  });
});
