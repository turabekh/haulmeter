// AI-CONTEXT: three write paths that failed in silence, or worse (§23 entry 222).
//
// §15.4: "failed money-moving actions are always explicit and persistent until
// resolved." All three of these are money paths, and none of them said so:
//
//   · filing a claim         — an EMPTY catch, on the one action this product exists for
//   · notifying the broker   — every failure reported as "detention hasn't started yet",
//                              which is not a worse message but a DIFFERENT FACT
//   · the chase ghostwriter  — a button labelled "Approve & send" whose entire handler
//                              was `sent.value = true`, then a screen reading "Sent"
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import GhostwriterSheet from "../src/core/components/GhostwriterSheet.vue";
import { routes } from "../src/router.js";
import { setToken, logout, setActiveStop, online } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const jsonOk = (b) => Promise.resolve({ ok: true, json: () => Promise.resolve(b) });
const METER = {
  stop_id: "stop-1", facility_name: "Dock 4", counterparty: "Acme", appointment: null,
  arrived: true, free_time_minutes: 120, rate_cents_per_hour: 7500,
  phase: "accruing", free_time_remaining_seconds: 0,
  detention_seconds: 3600, detention_cents: 7500,
  notice_sent: false, notice_delivery: "not_sent", photos_captured: 4, photos_required: 4,
  bol_captured: true, checklist: [], filed: false,
};

async function mountLoad(onWrite) {
  setToken("tok");
  setActiveStop("stop-1");
  vi.stubGlobal("fetch", vi.fn((url, opts) => {
    const u = String(url);
    if (opts?.method === "POST") return onWrite(u);
    if (u.includes("/meter")) return jsonOk(METER);
    return jsonOk({});
  }));
  const w = mount(LoadSurface, {
    global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] },
  });
  await flushPromises();
  return w;
}

async function tap(w, label) {
  const btn = w.findAll("button").find((b) => b.text().includes(label));
  expect(btn, `no control labelled "${label}"`).toBeTruthy();
  await btn.trigger("click");
  await flushPromises();
}

afterEach(() => { vi.unstubAllGlobals(); online.value = true; logout(); });

describe("Filing a claim that does not file", () => {
  it("says the claim was not filed, instead of nothing at all", async () => {
    online.value = true;
    const w = await mountLoad(() => Promise.resolve({ ok: false, status: 500 }));
    await tap(w, en["load.cta.claim"]);

    expect(w.text()).toContain(en["load.claim_failed"]);
  });

  it("says something different in a dead zone, because it is a different problem", async () => {
    const w = await mountLoad(() => { online.value = false; return Promise.reject(new Error("dead")); });
    await tap(w, en["load.cta.claim"]);

    expect(w.text()).toContain(en["load.claim_offline"]);
  });
});

describe("Notifying a broker when the notice does not go", () => {
  it("never claims detention has not started — that is a different fact", async () => {
    online.value = true;
    const w = await mountLoad(() => Promise.resolve({ ok: false, status: 500 }));
    await tap(w, en["load.cta.notice"]);

    expect(w.text()).not.toContain(en["load.notice_early"]);
    expect(w.text()).toContain(en["load.notice_failed"]);
  });

  it("distinguishes the dead dock from the refusal", async () => {
    const w = await mountLoad(() => { online.value = false; return Promise.reject(new Error("dead")); });
    await tap(w, en["load.cta.notice"]);

    expect(w.text()).toContain(en["load.notice_offline"]);
  });
});

describe("The chase ghostwriter hands the driver the words", () => {
  async function draft(clipboard) {
    vi.stubGlobal("fetch", vi.fn(() => jsonOk({ draft: "Please remit detention of $75.00." })));
    vi.stubGlobal("navigator", { clipboard });
    setToken("tok");
    const w = mount(GhostwriterSheet);
    await w.find("textarea").setValue("Held 3 hours at Dock 4");
    await tap(w, en["ghost.draft"]);
    return w;
  }

  it("says what is missing instead of doing nothing (§23 entry 233)", async () => {
    // THE REPORTED DEFECT. "Write it" is a full-weight Primary CTA sitting under an
    // empty box, fully enabled, and its handler opened with a bare `if (!f) return`.
    // Tapping it produced no request, no message and no change of any kind — measured
    // in the real app before this test was written. §7's form rule wants every error
    // "inline, specific, and next to its field"; a silent return is none of the three,
    // and a Primary that does nothing is indistinguishable from a broken app.
    const fetchMock = vi.fn(() => jsonOk({ draft: "unreachable" }));
    vi.stubGlobal("fetch", fetchMock);
    setToken("tok");
    const w = mount(GhostwriterSheet);

    await tap(w, en["ghost.draft"]);

    expect(w.text()).toContain(en["ghost.facts_required"]);
    // named precisely: other components mounted in this file poll their own endpoints,
    // and "fetch was never called" would be a claim about them rather than about drafting
    const drafts = fetchMock.mock.calls.filter(([u]) => String(u).includes("/voice/draft"));
    expect(drafts, "nothing to draft FROM — the request must not go").toEqual([]);
  });

  it("clears the complaint as soon as the driver types", async () => {
    vi.stubGlobal("fetch", vi.fn(() => jsonOk({ draft: "d" })));
    setToken("tok");
    const w = mount(GhostwriterSheet);
    await tap(w, en["ghost.draft"]);
    expect(w.text()).toContain(en["ghost.facts_required"]);

    await w.find("textarea").setValue("Held 3 hours at Dock 4");

    expect(w.text(), "a complaint that outlives its cause is noise").not.toContain(
      en["ghost.facts_required"],
    );
  });

  it("still writes when there ARE facts", async () => {
    // the sabotage guard: a fix that refuses everything would pass the test above
    const fetchMock = vi.fn(() => jsonOk({ draft: "Please remit detention of $75.00." }));
    vi.stubGlobal("fetch", fetchMock);
    setToken("tok");
    const w = mount(GhostwriterSheet);
    await w.find("textarea").setValue("Held 3 hours at Dock 4");

    await tap(w, en["ghost.draft"]);

    expect(fetchMock).toHaveBeenCalled();
    expect(w.text()).toContain("Please remit detention of $75.00.");
  });

  it("copies the message rather than claiming to send it", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    const w = await draft({ writeText });
    await tap(w, en["ghost.copy"]);

    expect(writeText).toHaveBeenCalledWith("Please remit detention of $75.00.");
    expect(w.text()).toContain(en["ghost.copied"]);
  });

  it("never tells a driver a message was sent — nothing here sends", async () => {
    // the validation law, as a test: "nothing 'sends' that didn't actually leave the
    // system". Entry 142 routes chasing through the driver on purpose.
    const w = await draft({ writeText: vi.fn(() => Promise.resolve()) });
    await tap(w, en["ghost.copy"]);

    expect(w.text()).not.toMatch(/\bSent\b/);
    expect(w.text()).not.toMatch(/Approve & send/);
  });

  it("says so when the clipboard refuses, and leaves the draft on screen", async () => {
    const w = await draft({ writeText: vi.fn(() => Promise.reject(new Error("denied"))) });
    await tap(w, en["ghost.copy"]);

    expect(w.text()).toContain(en["ghost.copy_failed"]);
    expect(w.text()).toContain("Please remit detention of $75.00.");
  });
});
