// AI-CONTEXT: the load record — read before it is downloaded or sent (§23 entry 137).
//
// Past loads offered a driver two things: open ONE stop's evidence, or "Export whole
// load", which downloaded a PDF they had never seen. There was no way to look at the
// document first and no way to send it to anybody — and that second gap became
// load-bearing the moment a driver could DISCARD a stop packet (entry 136): declining
// paperwork is only safe if there is a way back to it.
//
// The property worth guarding hardest is that the SCREEN AGREES WITH THE DOCUMENT. The
// API test asserts the counts against `load_pack` itself; these assert that what the
// endpoint says reaches the driver's eyes, and that neither action can fire without it.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import LoadRecordSurface from "../src/surfaces/LoadRecordSurface.vue";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import { __resetStateForTests, observeMotion, DRIVING_SUSTAIN_MS } from "../src/core/state.js";
import en from "../src/core/i18n/en.json";
import { messages } from "../src/core/i18n/index.js";
import { useI18n } from "../src/core/i18n.js";

const LOAD_ID = "aaaaaaaa-0000-0000-0000-000000000001";
const T0 = 1_760_000_000_000;

const RECORD = {
  load_id: LOAD_ID,
  reference_number: "BRL-78426",
  created_at: "2026-08-07T12:00:00+00:00",
  status: "closed",
  origin_name: "Harvest Foods DC",
  destination_name: "Kroger DC",
  stop_count: 2,
  counterparty_name: "Bolt Logistics",
  counterparty_email: "ap@bolt.example",
  detention_cents: 18750,
  claim_state: "invoiced",
  photo_count: 3,
  document_types: ["bol", "pod"],
  gps_events: 2,
  chain_valid: true,
  stops: [
    {
      stop_id: "bbbbbbbb-0000-0000-0000-000000000001",
      sequence: 0,
      stop_type: "pickup",
      facility_name: "Harvest Foods DC",
      detention_cents: null,
      photos: [
        // AI-CONTEXT: `thumb_url` is how a photograph reaches the screen now. The server
        // mints a short-lived signed URL per photo so the browser can load it from a
        // plain <img src> — an <img> cannot send an Authorization header, and that one
        // constraint is what forced the old fetch-blob-objectURL loop and cost this
        // surface its lazy-loading, its parallelism and its cache.
        { artifact_id: "p1", prompt: "seals", captured_at: "2026-08-07T13:00:00+00:00", has_image: true, thumb_url: "/media/evidence/p1?size=thumb&exp=1&sig=x" },
        { artifact_id: "p2", prompt: "seals", captured_at: "2026-08-07T13:01:00+00:00", has_image: true, thumb_url: "/media/evidence/p2?size=thumb&exp=1&sig=y" },
      ],
      document_types: ["bol"],
      gps_events: 1,
      chain_valid: true,
    },
    {
      stop_id: "bbbbbbbb-0000-0000-0000-000000000002",
      sequence: 1,
      stop_type: "delivery",
      facility_name: "Kroger DC",
      detention_cents: 18750,
      photos: [
        { artifact_id: "p3", prompt: "seals", captured_at: "2026-08-08T09:00:00+00:00", has_image: false },
      ],
      document_types: ["pod"],
      gps_events: 1,
      chain_valid: true,
    },
  ],
};

function jsonOk(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function stub(record = RECORD, overrides = {}) {
  return vi.fn((url, opts) => {
    const u = String(url);
    if (u.includes("/record")) {
      // a 500, not a rejection: `apiGet` flips the shared `online` ref on a transport
      // throw, so rejecting here would make the SERVER-failure case render as a dead
      // zone and the test would assert the wrong sentence (§15.1 vs §15.4).
      if (record === "fail") {
        return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
      }
      return jsonOk(record);
    }
    if (u.includes("/share")) return overrides.share ? overrides.share() : jsonOk({ id: "s-1" });
    if (u.includes("/export")) return overrides.export ? overrides.export() : jsonOk({});
    if (u.includes("/evidence/photo")) {
      return Promise.resolve({ ok: true, blob: () => Promise.resolve(new Blob(["x"])) });
    }
    return jsonOk({});
  });
}

async function mountRecord(fetchStub) {
  vi.stubGlobal("fetch", fetchStub);
  const router = createRouter({ history: createMemoryHistory(), routes });
  router.push(`/load/${LOAD_ID}/record`);
  await router.isReady();
  const w = mount(LoadRecordSurface, { global: { plugins: [router] } });
  await flushPromises();
  return w;
}

afterEach(() => {
  vi.unstubAllGlobals();
  __resetStateForTests();
  useI18n().setLocale("en");
  logout();
});

describe("Seeing a past load before doing anything with it", () => {
  it("says what is in the record, in words rather than a file", async () => {
    setToken("tok");
    const w = await mountRecord(stub());
    const text = w.text();

    expect(text).toContain(en["rec.whats_in"]);
    expect(text).toContain(en["rec.photos"].replace("{n}", "3"));
    expect(text).toContain(en["rec.gps"]);
    expect(text).toContain("$187.50");
    expect(text).toContain(en["docs.type.bol"]);
    expect(text).toContain(en["docs.type.pod"]);
  });

  it("shows BOTH docks of a two-stop load, in route order", async () => {
    // every read built before §23 entry 78 assumed one stop, and this is the shape that
    // catches it: a driver who photographed both ends must see both ends.
    setToken("tok");
    const w = await mountRecord(stub());
    const names = w.findAll(".stop__name").map((n) => n.text());

    expect(names.length).toBe(2);
    expect(names[0]).toContain("Harvest Foods DC");
    expect(names[1]).toContain("Kroger DC");
  });

  it("shows the actual photographs, not just a count", async () => {
    // the owner's whole point: "6 photos" is a number, these are the photographs. A
    // driver vouching for a document to the person who pays them should see it.
    setToken("tok");
    const w = await mountRecord(stub());
    await flushPromises();

    expect(w.findAll(".shots__item").length).toBe(3);
    const imgs = w.findAll(".shots__img");
    expect(imgs.length).toBe(2); // the third photo has no image

    // the photographs are ordinary images the browser owns: deferred below the fold,
    // decoded off the main thread, cached by the browser rather than held in JS memory
    // resolved the way a browser does — a bare string comparison is what let the
    // page-origin defect ship (see media-url-origin.test.js)
    const src = new URL(imgs[0].attributes("src"), "https://haulmeter.online/x");
    expect(src.pathname.endsWith("/media/evidence/p1")).toBe(true);
    expect(src.href).not.toBe("https://haulmeter.online/media/evidence/p1?size=thumb&exp=1&sig=x");
    expect(imgs[0].attributes("loading")).toBe("lazy");
    expect(imgs[0].attributes("decoding")).toBe("async");
  });

  it("reaches each dock's full evidence from the dock it belongs to", async () => {
    setToken("tok");
    const w = await mountRecord(stub());
    const opens = w.findAll(".stop__open");
    expect(opens.length).toBe(2);
    expect(opens[0].text()).toContain(en["rec.open_stop"]);
  });

  it("declares all four states (§22.3): loading, loaded, empty, failed", async () => {
    setToken("tok");

    const failed = await mountRecord(stub("fail"));
    expect(failed.text()).toContain(en["rec.failed"]);
    expect(failed.find(".cta").exists()).toBe(false); // §15.4: never data, never actions

    const empty = await mountRecord(
      stub({ ...RECORD, photo_count: 0, gps_events: 0, document_types: [], stops: [] }),
    );
    expect(empty.text()).toContain(en["rec.empty"]);
    // §15.3 with nothing to act on: offering Send here would be a button that can only fail
    expect(empty.find(".cta").exists()).toBe(false);
  });
});

describe("Sending a past load — the mechanism that existed and had no caller", () => {
  it("offers Send as the one Primary, with download beside it", async () => {
    setToken("tok");
    const w = await mountRecord(stub());
    const filled = w.findAll(".cta").filter((b) => !b.classes().includes("cta--outline"));

    expect(filled.length).toBe(1); // §8: one Primary per screen
    expect(filled[0].text()).toContain(en["rec.send"]);
    expect(w.find(".cta--outline").text()).toContain(en["rec.download"]);
  });

  it("sends the WHOLE LOAD, not one stop", async () => {
    // `/protection/load/{id}/share` has accepted kind="load" since the whole-route pack
    // was written and the only caller in the product passed "stop" — so a driver could
    // only ever email one dock's half of their own evidence. This is the assertion that
    // the right pack goes out.
    setToken("tok");
    const s = stub();
    const w = await mountRecord(s);
    await w.findAll(".cta").filter((b) => !b.classes().includes("cta--outline"))[0].trigger("click");
    await flushPromises();
    await w.find(".send .cta").trigger("click");
    await flushPromises();

    const call = s.mock.calls.find((c) => String(c[0]).includes("/share"));
    expect(call, "nothing was shared").toBeTruthy();
    expect(String(call[0])).toContain(`/protection/load/${LOAD_ID}/share`);
    expect(String(call[0])).not.toContain("/protection/stop/");
  });

  it("defaults to the broker on file and lets the driver change it", async () => {
    setToken("tok");
    const s = stub();
    const w = await mountRecord(s);
    await w.findAll(".cta").filter((b) => !b.classes().includes("cta--outline"))[0].trigger("click");
    await flushPromises();

    const input = w.find(".send__input");
    expect(input.element.value).toBe("ap@bolt.example");
    await input.setValue("night.desk@bolt.example");
    await w.find(".send .cta").trigger("click");
    await flushPromises();

    const call = s.mock.calls.find((c) => String(c[0]).includes("/share"));
    expect(JSON.parse(call[1].body).recipient).toBe("night.desk@bolt.example");
  });

  it("says there is no address rather than sending to nobody", async () => {
    // HANDOFF-122 §3: nothing in this product had ever written `contact_email`, so this
    // is the common case, and Send must not be tappable into a void.
    setToken("tok");
    const w = await mountRecord(stub({ ...RECORD, counterparty_email: null }));
    await w.findAll(".cta").filter((b) => !b.classes().includes("cta--outline"))[0].trigger("click");
    await flushPromises();

    expect(w.find(".send").text()).toContain(en["rec.no_email"]);
    expect(w.find(".send .cta").attributes("disabled")).toBeDefined();
  });

  it("refuses to offer a send at all when the chain does not check out", async () => {
    // §11.7 and the evidence-integrity session: `share_pack` REFUSES an invalid chain,
    // so a Primary offered here could only produce a refusal. Say it up front instead.
    setToken("tok");
    const w = await mountRecord(stub({ ...RECORD, chain_valid: false }));

    expect(w.text()).toContain(en["rec.broken"]);
    const send = w.findAll(".cta").filter((b) => !b.classes().includes("cta--outline"))[0];
    expect(send.attributes("disabled")).toBeDefined();
  });

  it("never claims a delivery it only queued (§15.1)", async () => {
    // F-03's defect was a row claiming a send it never got. A queued share is not a
    // delivery, and saying "Sent" over one would rebuild that on a screen.
    setToken("tok");
    const s = stub(RECORD, { share: () => jsonOk({ queued: true }) });
    const w = await mountRecord(s);
    await w.findAll(".cta").filter((b) => !b.classes().includes("cta--outline"))[0].trigger("click");
    await flushPromises();
    await w.find(".send .cta").trigger("click");
    await flushPromises();

    expect(w.text()).toContain(en["rec.send_offline"]);
    expect(w.text()).not.toContain(en["rec.sent"]);
  });

  it("withdraws both acting controls at speed and stays readable (SM-3)", async () => {
    setToken("tok");
    const w = await mountRecord(stub());
    observeMotion({ speedMps: 25, now: T0 });
    observeMotion({ speedMps: 25, now: T0 + DRIVING_SUSTAIN_MS });
    await flushPromises();

    expect(w.find(".cta").exists()).toBe(false);
    expect(w.text()).toContain(en["rec.driving"]);
    expect(w.text()).toContain(en["rec.whats_in"]); // the record itself is still readable
  });

  it("spins and disables while sending, in the driver's language", async () => {
    useI18n().setLocale("uz");
    setToken("tok");
    let release;
    const gate = new Promise((r) => (release = r));
    const s = stub(RECORD, { share: () => gate.then(() => jsonOk({ id: "s-1" })) });
    const w = await mountRecord(s);
    await w.findAll(".cta").filter((b) => !b.classes().includes("cta--outline"))[0].trigger("click");
    await flushPromises();
    await w.find(".send .cta").trigger("click");
    await flushPromises();

    const btn = w.find(".send .cta");
    expect(btn.attributes("disabled")).toBeDefined();
    expect(btn.find(".spin").exists()).toBe(true);
    expect(btn.text()).toContain(messages.uz["busy.sending"]);
    release();
    await flushPromises();
  });
});

describe("Past loads sends the driver to the record (§23 entry 137)", () => {
  it("gives every row ONE destination instead of three behaviours", async () => {
    // the row used to navigate for a one-stop load, EXPAND for a multi-stop one, and
    // hide an "Export whole load" download inside that expansion — a PDF the driver had
    // never seen. One row, one tap, one screen.
    setToken("tok");
    const rows = [
      { load_id: LOAD_ID, stop_id: "s1", facility_name: "Harvest Foods DC",
        destination_name: "Kroger DC", reference_number: "BRL-78426",
        created_at: "2026-08-07T12:00:00+00:00", stop_count: 2, detention_cents: 18750,
        claim_state: "invoiced", evidence_count: 3, documents: ["bol"], stops: [] },
    ];
    const s = vi.fn((url) => {
      const u = String(url);
      if (u.includes("/load/history")) return jsonOk({ loads: rows });
      if (u.includes("/protection/stop-packets")) return jsonOk([]);
      return jsonOk({});
    });
    vi.stubGlobal("fetch", s);
    const router = createRouter({ history: createMemoryHistory(), routes });
    router.push("/load");
    await router.isReady();
    const w = mount(LoadSurface, { global: { plugins: [router] } });
    await flushPromises();

    await w.find(".cta--text").trigger("click"); // "Past loads"
    await flushPromises();
    await w.find(".hist__main").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe(`/load/${LOAD_ID}/record`);
    // and the blind download is gone from the sheet entirely
    expect(w.find(".hist__export").exists()).toBe(false);
  });
});
