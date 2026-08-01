// AI-CONTEXT: A1 requirement 1 on the screen — "a capture checklist per stop type — BOL,
// seal, cargo condition, lumper receipt, damage. The checklist is configuration (F13),
// not code."
//
// §10.2's evidence card carried ONE paperwork row, hardcoded to the BOL. A driver
// dropping a load was never asked for the POD and a driver collecting one was never
// asked for the seal — and `has_bol` already paid for the near half of this lesson:
// it rendered an unconditional tick, and "a checklist that always says yes is
// decoration". A checklist that always asks the same question is the same decoration
// with more steps.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout, setActiveStop } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

function jsonOk(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function meter(checklist) {
  return {
    stop_id: "stop-1",
    facility_name: "Dock 4",
    counterparty: "Acme",
    appointment: null,
    arrived: true,
    free_time_minutes: 120,
    rate_cents_per_hour: 7500,
    phase: "accruing",
    free_time_remaining_seconds: 0,
    detention_seconds: 600,
    detention_cents: 1250,
    notice_sent: false,
    photos_captured: 0,
    photos_required: 4,
    bol_captured: false,
    checklist,
  };
}

async function mountWith(checklist) {
  setToken("tok");
  setActiveStop("stop-1");
  vi.stubGlobal(
    "fetch",
    vi.fn((url) =>
      String(url).includes("/load/stop-1/meter") ? jsonOk(meter(checklist)) : jsonOk({}),
    ),
  );
  const w = mount(LoadSurface, {
    global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] },
  });
  await flushPromises();
  return w;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setActiveStop(null);
  logout();
});

const DELIVERY = [
  { item: "bol", kind: "document", captured: true, required: true },
  { item: "pod", kind: "document", captured: false, required: true },
  { item: "cargo_condition", kind: "condition_photo", captured: false, required: true },
  { item: "lumper_receipt", kind: "document", captured: false, required: true },
  { item: "damage", kind: "document", captured: false, required: false },
];

describe("A1 req 1 — the capture checklist on §10.2's card", () => {
  it("asks a DELIVERY for the POD, which the hardcoded row never could", async () => {
    const w = await mountWith(DELIVERY);
    expect(w.find(".checklist").text()).toContain(en["load.doc.pod_missing"]);
    w.unmount();
  });

  it("asks a PICKUP for the SEAL instead — a different stop, a different list", async () => {
    const w = await mountWith([
      { item: "bol", kind: "document", captured: false, required: true },
      { item: "seal", kind: "document", captured: false, required: true },
    ]);
    const text = w.find(".checklist").text();
    expect(text).toContain(en["load.doc.seal_missing"]);
    expect(text).not.toContain(en["load.doc.pod_missing"]);
    w.unmount();
  });

  it("flips the LABEL, not only the glyph (§16)", async () => {
    // the failure this exists for: status carried by an icon alone is the part a driver
    // misses, which is why §16 requires colour AND icon AND label. `bol` is captured in
    // DELIVERY and `pod` is not — the two rows must not read the same.
    const w = await mountWith(DELIVERY);
    const text = w.find(".checklist").text();
    expect(text).toContain(en["load.doc.bol"]);
    expect(text).not.toContain(en["load.doc.bol_missing"]);
    w.unmount();
  });

  it("does not render cargo condition twice", async () => {
    // it is on the configured checklist AND it is the photos row, which already carries
    // the 2/4 denominator §10.2 asks for. Two rows saying the same thing in different
    // words is worse than one.
    //
    // AI-CONTEXT: this counted rows containing "0/4" and was VACUOUS — a stray
    // cargo_condition row renders `load.doc.cargo_condition`, which is not an i18n key
    // and never contains "0/4", so the assertion passed with the filter deleted. Caught
    // by removing the filter and watching it stay green. Count the ROWS: DELIVERY's four
    // document items plus the three fixed rows (on-time, photos, notice) is seven, and
    // the fifth configured item appearing as its own row makes eight.
    const w = await mountWith(DELIVERY);
    expect(w.findAll(".checklist__item")).toHaveLength(7);
    w.unmount();
  });

  it("says a clean stop is COMPLETE, not deficient", async () => {
    // damage is if-applicable. A checklist that reports a clean stop as incomplete is
    // one a driver learns to dismiss, and a dismissed checklist is the rubber stamp
    // `draft_stop_packet_on_exit` was built to avoid.
    const w = await mountWith(DELIVERY);
    expect(w.find(".checklist").text()).toContain(en["load.doc.damage_missing"]);
    expect(en["load.doc.damage_missing"]).not.toMatch(/not captured|missing/i);
    w.unmount();
  });

  it("still says something when an offline payload predates the checklist", async () => {
    // a cached meter from before A1 has no `checklist` at all. Rendering nothing would
    // tell a driver this stop needs no paperwork, which is the one answer never right.
    const w = await mountWith(undefined);
    expect(w.find(".checklist").text()).toContain(en["load.doc.bol_missing"]);
    w.unmount();
  });
});

describe("the Docs-tab chooser, which the same change touched", () => {
  it("labels every type the API offers — a chip with no key renders the key", async () => {
    // AI-CONTEXT: "when a mechanism is fixed in one place, check whether it belongs in
    // the others". Adding `seal`, `damage` and `lumper_receipt` to the server's
    // DRIVER_DOC_TYPES so the checklist rows are capturable ALSO puts them in this
    // chooser, which renders `docs.type.<type>`. Three missing keys would have shipped
    // as three chips reading "docs.type.seal" beside "BOL".
    //
    // WHAT THIS DOES NOT COVER, stated plainly: the list arrives from the server, and
    // this test supplies it. A type added server-side without a label here is still not
    // caught by anything — the api container cannot read `ui/`, so the two halves of
    // this contract have no shared test.
    const TYPES = [
      "cdl", "med_card", "insurance", "permit", "rate_con", "bol", "pod", "other",
      "lumper_receipt", "seal", "damage",
    ];
    for (const ty of TYPES) {
      expect(en[`docs.type.${ty}`], `no label for the ${ty} chip`).toBeTruthy();
      expect(en[`docs.type.${ty}`]).not.toBe(`docs.type.${ty}`);
    }
  });
});

describe("a checklist row a driver can actually close", () => {
  it("opens the capture sheet for THAT item, not always the BOL", async () => {
    // the defect this exists for: the sheet was `fixed-type="bol"`, so five rows would
    // have asked for five artifacts and every one of them would have filed a BOL.
    const w = await mountWith(DELIVERY);
    const rows = w.findAll(".checklist__snap");
    const pod = rows.find((r) => r.text().includes(en["load.doc.pod_missing"]));
    expect(pod, "the POD row was not tappable").toBeTruthy();
    await pod.trigger("click");
    await flushPromises();
    expect(w.findComponent({ name: "DocumentCaptureSheet" }).props("fixedType")).toBe("pod");
    w.unmount();
  });

  it("offers no action on a row already captured", async () => {
    const w = await mountWith(DELIVERY);
    const captured = w
      .findAll(".checklist__item")
      .find((r) => r.text().includes(en["load.doc.bol"]));
    expect(captured.find(".checklist__snap").exists()).toBe(false);
    w.unmount();
  });
});
