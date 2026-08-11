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
import { messages } from "../src/core/i18n/index.js";
import { useI18n } from "../src/core/i18n.js";

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


// AI-CONTEXT: the state the owner photographed, which NOTHING had ever measured.
//
// Every packet state in the layout harness — `load-packet-ready`, `load-packet-review`,
// `load-worst-case` — mocks a LIVE load beside the packet. "Paperwork waiting, no load
// running" is where a driver stands every time they finish a run, and it had no harness
// state and no assertion, so this shipped:
//
//   [ You left Harvest Foods DC. Your paperwork is ready. ]
//   [           Review & send            ]  <- filled Primary
//   [              No load                              ]
//   [                 —                                 ]
//   [            Add a load              ]  <- a SECOND filled Primary
//
// Two identical full-bleed Primaries with nothing to rank them (§8 allows one), and a
// resting Meter reading "No load —" directly under a card announcing the dock just
// left. The em-dash sits where this product puts money, so the screen a driver opens
// straight after a drop could read as their detention having disappeared.
//
// These assertions are about the COMBINATION. The blocks were each correct alone,
// which is exactly why measuring them one at a time went green over this.
describe("Paperwork waiting with no load — one job at a time (§8, §22.2)", () => {
  afterEach(() => {
    __resetStateForTests();
    lastEvents.value = [];
  });

  // filled Primary = `.cta` that is neither the text nor the outline grade (§8).
  function primaries(w) {
    return w.findAll(".cta").filter((b) => {
      const c = b.classes();
      return !c.includes("cta--text") && !c.includes("cta--outline");
    });
  }

  it("puts exactly ONE filled Primary on the screen", async () => {
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();

    const filled = primaries(w);
    expect(filled.length).toBe(1);
    expect(filled[0].classes()).toContain("packet-card__cta");
  });

  it("does not say 'No load' underneath the dock the driver just left", async () => {
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();

    expect(w.find(".packet-card").exists()).toBe(true);
    expect(w.find(".meter-card").exists()).toBe(false);
    expect(w.text()).not.toContain(en["load.empty_title"]);
    expect(w.text()).not.toContain(en["load.empty_hint"]);
  });

  it("keeps both destinations, one grade quieter", async () => {
    // the fix is a RANKING, not a removal: a driver who wants to start the next load
    // before sending the last one's paperwork must still be able to.
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();

    const row = w.find(".rungs--empty");
    expect(row.exists()).toBe(true);
    expect(row.text()).toContain(en["load.rc_add"]);
    expect(row.text()).toContain(en["load.history"]);
    expect(row.findAll(".rungs__item").length).toBe(2);
  });

  it("still opens the import sheet from the quiet control", async () => {
    // a control that is quieter must not be a control that is dead (§23's dead-control
    // pattern) — the tertiary grade changes the weight, never the wiring.
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();

    await w.findAll(".rungs--empty .rungs__item")[0].trigger("click");
    await flushPromises();
    expect(w.text()).toContain(en["load.rc_lead"]); // the import sheet's own first line
  });

  it("hands the Meter and the Primary back the moment the packet is sent", async () => {
    // the two states are SEQUENCED, so the second must actually arrive. A fix that
    // hid the empty state permanently would be worse than the collision it replaced.
    setToken("tok");
    const stub = vi.fn((url, opts) =>
      String(url).includes("/send") && opts?.method === "POST"
        ? jsonOk({ id: "p-1", state: "sent" })
        : String(url).includes("/protection/stop-packets")
          ? jsonOk([PACKET])
          : jsonOk({}),
    );
    const w = mountLoad(stub);
    await flushPromises();
    expect(w.find(".meter-card").exists()).toBe(false);

    await w.find(".packet-card__cta").trigger("click");
    await flushPromises();
    await w.find(".review__send").trigger("click");
    await flushPromises();

    expect(w.find(".packet-card").exists()).toBe(false);
    expect(w.find(".meter-card").exists()).toBe(true);
    expect(w.find(".rungs--empty").exists()).toBe(false);
    expect(primaries(w).length).toBe(1);
    expect(primaries(w)[0].text()).toContain(en["load.rc_add"]);
    expect(w.text()).toContain(en["load.empty_hint"]);
  });

  it("leaves the DRIVING glance card exactly as §10.2 specifies", async () => {
    // §10.2 at speed: "collapses to Meter-only glance card + voice hint". The collision
    // this fixes is a decision between two buttons, and there are no buttons at speed —
    // so the Meter must NOT stand down here.
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();

    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    await flushPromises();

    expect(w.find(".meter-card").exists()).toBe(true);
    expect(w.find(".rungs--empty").exists()).toBe(false);
  });
});

// AI-CONTEXT: HANDOFF-122 §3 — nothing in this product had ever written
// `contact_email`, so on most real loads this packet has nowhere to go. That fact was
// reachable only by tapping through to the sheet, where the driver met "No email on
// file" as a surprise. §12.4 wants what happened and what to do, while they can act.
describe("Where the paperwork is going, said before the tap (§12.4)", () => {
  afterEach(() => {
    __resetStateForTests();
    lastEvents.value = [];
  });

  it("names the address on the card", async () => {
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();

    const to = w.find(".packet-card__to");
    expect(to.exists()).toBe(true);
    expect(to.text()).toContain("ap@bolt.example");
    expect(to.classes()).not.toContain("packet-card__to--missing");
  });

  it("says so when there is no address, rather than waiting for the sheet", async () => {
    setToken("tok");
    const w = mountLoad(packetsOnly([{ ...PACKET, recipient: null }]));
    await flushPromises();

    const to = w.find(".packet-card__to");
    expect(to.text()).toContain(en["packet.needs_email"]);
    // §16: colour is never the sole signal — the icon and the label carry it too.
    expect(to.classes()).toContain("packet-card__to--missing");
    expect(to.find("svg").exists()).toBe(true);
  });

  it("labels the reference instead of printing a bare code", async () => {
    // "BL-77" alone is a code with no noun: a driver cannot tell their own load number
    // from a tracking number the app invented.
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();

    const ref = w.find(".packet-card__ref");
    expect(ref.text()).toBe(en["packet.ref"].replace("{ref}", "BL-77"));
    expect(ref.text()).not.toBe("BL-77");
  });

  it("says none of it at speed — the card is a line of text there", async () => {
    setToken("tok");
    const w = mountLoad(packetsOnly([PACKET]));
    await flushPromises();

    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    await flushPromises();

    expect(w.find(".packet-card__to").exists()).toBe(false);
    expect(w.find(".packet-card__cta").exists()).toBe(false);
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


// AI-CONTEXT: §8's button loading state, built for the first time (owner request,
// 2026-08-11) — "Loading state = inline spinner replacing label, width locked."
//
// That sentence has been in the design constitution since it was written and nothing in
// this product implemented it. About a dozen buttons already set `:disabled` while a
// write was in flight, so the GUARD existed and the FEEDBACK did not: on a dock with two
// bars a driver tapped Send and watched a button identical to an untapped one. The
// reasonable response to that is to tap it again.
//
// `deferred` holds the request open, which is the only way to observe the in-flight
// state at all — a stub that resolves immediately has already finished by the time the
// assertion runs, and a test written against one would pass no matter what the button
// rendered mid-flight.
function deferred() {
  let resolve;
  const promise = new Promise((r) => (resolve = r));
  return { promise, resolve };
}

describe("Buttons say they are working (§8 loading state)", () => {
  afterEach(() => {
    __resetStateForTests();
    lastEvents.value = [];
    useI18n().setLocale("en");
  });

  async function openWithPendingSend() {
    setToken("tok");
    const gate = deferred();
    const stub = vi.fn((url, opts) =>
      String(url).includes("/send") && opts?.method === "POST"
        ? gate.promise.then(() => jsonOk({ id: "p-1", state: "sent" }))
        : jsonOk([PACKET]),
    );
    const w = mountLoad(stub);
    await flushPromises();
    await w.find(".packet-card__cta").trigger("click");
    await flushPromises();
    return { w, gate };
  }

  it("disables Send and shows a spinner while the packet is in flight", async () => {
    const { w, gate } = await openWithPendingSend();
    const send = w.find(".review__send");
    expect(send.attributes("disabled")).toBeUndefined();
    expect(send.find(".spin").exists()).toBe(false);

    await send.trigger("click");
    await flushPromises();

    expect(w.find(".review__send").attributes("disabled")).toBeDefined();
    expect(w.find(".review__send .spin").exists()).toBe(true);
    expect(w.find(".review__send").text()).toContain(en["busy.sending"]);

    gate.resolve();
    await flushPromises();
  });

  it("says it in the driver's language, not English", async () => {
    // the owner's actual ask. A busy label hardcoded in English is the same defect as a
    // raw translation key — worse, because it looks deliberate.
    for (const loc of ["uz", "ru", "es", "pa", "so"]) {
      useI18n().setLocale(loc);
      const { w, gate } = await openWithPendingSend();
      await w.find(".review__send").trigger("click");
      await flushPromises();

      expect(w.find(".review__send").text(), `${loc} busy label`).toContain(
        messages[loc]["busy.sending"],
      );
      expect(w.find(".review__send").text()).not.toContain(en["busy.sending"]);
      gate.resolve();
      await flushPromises();
    }
  });

  it("the spinner is hidden from assistive tech — the LABEL carries the state", async () => {
    // §16: never motion alone, never colour alone. A screen reader gets the disabled
    // attribute and the changed label; the ring is decoration for the eye.
    const { w, gate } = await openWithPendingSend();
    await w.find(".review__send").trigger("click");
    await flushPromises();

    expect(w.find(".review__send .spin").attributes("aria-hidden")).toBe("true");
    gate.resolve();
    await flushPromises();
  });

  it("a second tap while in flight does not send twice", async () => {
    const { w, gate } = await openWithPendingSend();
    await w.find(".review__send").trigger("click");
    await flushPromises();
    await w.find(".review__send").trigger("click");
    await flushPromises();
    gate.resolve();
    await flushPromises();

    // counted on the stub itself: the guard is in `onSendPacket`, and the assertion has
    // to be about REQUESTS rather than about the button being disabled — a disabled
    // attribute that a synthetic click ignores would still fire the handler.
    expect(
      vi.mocked(globalThis.fetch).mock.calls.filter(
        (c) => String(c[0]).includes("/send") && c[1]?.method === "POST",
      ).length,
    ).toBe(1);
  });
});


// AI-CONTEXT: the review's SECOND exit (owner request, 2026-08-11).
//
// A1 req 5 is "the driver reviews before it sends" and a review could only ever conclude
// one way. A packet the driver did not want stayed on the Load tab, and the only control
// that could clear it was Send — so the product's answer to "I don't need to send this"
// was to send it.
//
// §8 wants a destructive action to have "its own confirm sheet" and caps sheets at "max
// 1 deep"; the review sheet is already that one. So the confirm is a STEP inside it.
describe("Discarding paperwork without sending it (§8 destructive)", () => {
  afterEach(() => {
    __resetStateForTests();
    lastEvents.value = [];
  });

  async function openReview(stub) {
    setToken("tok");
    const w = mountLoad(stub || packetsOnly([PACKET]));
    await flushPromises();
    await w.find(".packet-card__cta").trigger("click");
    await flushPromises();
    return w;
  }

  function discardStub(ok = true) {
    return vi.fn((url, opts) => {
      if (String(url).includes("/discard") && opts?.method === "POST") {
        return ok
          ? jsonOk({ id: "p-1", state: "discarded" })
          : Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
      }
      return String(url).includes("/protection/stop-packets")
        ? jsonOk([PACKET])
        : jsonOk({});
    });
  }

  it("offers a way out that is not Send", async () => {
    const w = await openReview();
    expect(w.find(".review").text()).toContain(en["packet.discard"]);
  });

  it("does NOT discard on the first tap — it asks first", async () => {
    // §8: destructive requires a confirm. The assertion that matters is that NO request
    // was made, not merely that a confirm appeared.
    const stub = discardStub();
    const w = await openReview(stub);
    await w.findAll(".review .cta--text")[0].trigger("click");
    await flushPromises();

    expect(stub.mock.calls.some((c) => String(c[0]).includes("/discard"))).toBe(false);
    expect(w.text()).toContain(en["packet.discard_body"]);
    expect(w.find(".cta--destructive").exists()).toBe(true);
    // the SHEET'S OWN TITLE has to move too. Found by looking at the screenshot, not by
    // the suite: the confirm body asked about discarding under a heading that still read
    // "Review before it sends", and `packet.discard_title` was translated into all six
    // locales and rendered by nothing — a key with no caller, which is the shape these
    // handoffs keep finding. Nothing here can go green over it again.
    expect(w.find(".sheet__title").text()).toBe(en["packet.discard_title"]);
  });

  it("puts the review title back when the driver keeps it", async () => {
    const w = await openReview();
    await w.findAll(".review .cta--text")[0].trigger("click");
    await flushPromises();
    await w.findAll(".review .cta--text")[0].trigger("click");
    await flushPromises();
    expect(w.find(".sheet__title").text()).toBe(en["packet.review_title"]);
  });

  it("discards on the confirm, and the card clears", async () => {
    const stub = discardStub();
    const w = await openReview(stub);
    await w.findAll(".review .cta--text")[0].trigger("click");
    await flushPromises();
    await w.find(".cta--destructive").trigger("click");
    await flushPromises();

    expect(
      stub.mock.calls.some((c) => String(c[0]).includes("/protection/stop-packets/p-1/discard")),
    ).toBe(true);
    expect(w.find(".packet-card").exists()).toBe(false);
  });

  it("never sends anything on the way out", async () => {
    // the invariant the whole feature rests on. Discard is the opposite of Send, and a
    // discard path that also posted /send would be the worst possible bug here.
    const stub = discardStub();
    const w = await openReview(stub);
    await w.findAll(".review .cta--text")[0].trigger("click");
    await flushPromises();
    await w.find(".cta--destructive").trigger("click");
    await flushPromises();

    expect(stub.mock.calls.some((c) => String(c[0]).includes("/send"))).toBe(false);
  });

  it("Keep it goes back to the review with the packet untouched", async () => {
    const stub = discardStub();
    const w = await openReview(stub);
    await w.findAll(".review .cta--text")[0].trigger("click");
    await flushPromises();
    await w.findAll(".review .cta--text")[0].trigger("click"); // "Keep it"
    await flushPromises();

    expect(stub.mock.calls.some((c) => String(c[0]).includes("/discard"))).toBe(false);
    expect(w.find(".review__send").exists()).toBe(true);
    expect(w.find(".packet-card").exists()).toBe(true);
  });

  it("reopening the sheet starts on the review, never on the confirm", async () => {
    // a sheet that reopened on the destructive step would put a flare-filled button
    // under a driver who tapped "Check and send".
    const w = await openReview();
    await w.findAll(".review .cta--text")[0].trigger("click");
    await flushPromises();
    expect(w.find(".cta--destructive").exists()).toBe(true);

    await w.find(".sheet__close").trigger("click");
    await flushPromises();
    expect(w.find(".review").exists()).toBe(false); // the sheet really did close
    await w.find(".packet-card__cta").trigger("click");
    await flushPromises();

    expect(w.find(".cta--destructive").exists()).toBe(false);
    expect(w.find(".review__send").exists()).toBe(true);
  });

  it("a failed discard says so and keeps the packet", async () => {
    // §12.4, and deliberately NOT the offline wording Send uses: a discard is not
    // queued, so promising it will happen later would be a promise nothing keeps.
    const w = await openReview(discardStub(false));
    await w.findAll(".review .cta--text")[0].trigger("click");
    await flushPromises();
    await w.find(".cta--destructive").trigger("click");
    await flushPromises();

    expect(w.text()).toContain(en["packet.discard_failed"]);
    expect(w.find(".packet-card").exists()).toBe(true);
  });

  it("shows a spinner and a localized busy label while discarding", async () => {
    setToken("tok");
    const gate = deferred();
    const stub = vi.fn((url, opts) =>
      String(url).includes("/discard") && opts?.method === "POST"
        ? gate.promise.then(() => jsonOk({ id: "p-1", state: "discarded" }))
        : jsonOk([PACKET]),
    );
    const w = mountLoad(stub);
    await flushPromises();
    await w.find(".packet-card__cta").trigger("click");
    await flushPromises();
    await w.findAll(".review .cta--text")[0].trigger("click");
    await flushPromises();
    await w.find(".cta--destructive").trigger("click");
    await flushPromises();

    expect(w.find(".cta--destructive").attributes("disabled")).toBeDefined();
    expect(w.find(".cta--destructive .spin").exists()).toBe(true);
    expect(w.find(".cta--destructive").text()).toContain(en["busy.discarding"]);
    gate.resolve();
    await flushPromises();
  });
});
