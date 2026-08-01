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
