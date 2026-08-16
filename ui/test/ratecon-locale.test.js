// AI-CONTEXT: the parse, in the driver's language (J1-A2).
//
// The confirm step is a COMPARISON against a piece of paper, and until now the only way
// to make it was to decode three input boxes labelled in trucking English. A driver whose
// locale is `uz` could confirm a contract they could not read — which is the confirm step
// existing in form and not in fact.
//
// Two rules pull in opposite directions here and both are load-bearing:
//
//  · what the APP understood is composed from parsed slots and rendered in the driver's
//    language, absence included;
//  · what the PAPER says stays verbatim and English, beside it, labelled as such — a
//    translated clause cannot be compared against the contract in the driver's hand, and
//    a claim is argued from the original (§12.3).
//
// The failure this guards against is the Q-9 one: a driver who meets English where they
// expected their own language cannot tell "we found nothing" from "we did not translate
// this". So absence must never fall back to English.
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import RateConImportSheet from "../src/core/components/RateConImportSheet.vue";
import { setToken, logout } from "../src/core/api.js";
import { useI18n } from "../src/core/i18n.js";
import { messages, LAUNCH_LOCALES } from "../src/core/i18n/index.js";

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

const FULL = {
  document_id: "doc-rc",
  readable: true,
  parsed: {
    broker_name: "Coyote Logistics",
    reference_number: "L-9001",
    rate_cents: 185000,
    detention_rate_cents_per_hour: 7500,
    free_time_minutes: 120,
    accessorial_terms: { tonu: "50% of linehaul if cancelled after arrival" },
  },
  contact: { email: null, phone: null },
  silent_on: [],
  stops: [
    {
      sequence: 0,
      stop_type: "delivery",
      name: "ACME Distribution Center",
      address: "8450 Lakeside Ave, Columbus, OH",
      appointment_start: null,
      appointment_end: null,
      location: { lat: 39.96, lon: -83.09, label: "8450 Lakeside Ave" },
      facility_candidates: [],
    },
  ],
};

// a real and common shape: a rate con that names a route and states no money at all
const SILENT_ON_MONEY = {
  ...FULL,
  parsed: { ...FULL.parsed, rate_cents: null, detention_rate_cents_per_hour: null,
            free_time_minutes: null },
  silent_on: ["detention", "free_time"],
};

function stub(draft) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url) =>
      String(url).endsWith("/load/import") ? jsonOk(draft) : jsonOk({}),
    ),
  );
}

async function readSheet() {
  const w = mount(RateConImportSheet);
  w.find(".rc__input").element.files = [new File(["x"], "rc.pdf", { type: "application/pdf" })];
  await w.find(".rc__input").trigger("change");
  await flushPromises();
  await w.find(".rc__cta").trigger("click");
  for (let i = 0; i < 5; i += 1) {
    await new Promise((r) => setTimeout(r, 0));
    await flushPromises();
  }
  await w.vm.$nextTick();
  return w;
}

beforeEach(() => setToken("tok-locale"));
afterEach(() => {
  useI18n().setLocale("en");
  vi.unstubAllGlobals();
  logout();
});

describe("the money terms, stated in the driver's language", () => {
  it("says what it understood, not only what it is missing", async () => {
    stub(FULL);
    const w = await readSheet();

    const reading = w.find(".rc__reading").text();
    expect(reading).toContain(messages.en["load.terms.pays"]);
    expect(reading).toContain("$1,850.00");
    expect(reading).toContain("$75.00");
    expect(reading).toContain("120");
  });

  it("renders in Uzbek for a driver whose locale is Uzbek", async () => {
    useI18n().setLocale("uz");
    stub(FULL);
    const w = await readSheet();

    const reading = w.find(".rc__reading").text();
    expect(reading).toContain(messages.uz["load.terms.pays"]);
    expect(reading).toContain(messages.uz["load.terms.free"]);
    // and NOT the English it would fall back to
    expect(reading).not.toContain(messages.en["load.terms.pays"]);
  });

  it("states an absent term as absence, in the driver's language", async () => {
    // the Q-9 principle. A driver who meets English here cannot tell "we found nothing"
    // from "we did not translate this" — so absence must never fall back to English,
    // and it must never become a fabricated line or a silent zero.
    useI18n().setLocale("uz");
    stub(SILENT_ON_MONEY);
    const w = await readSheet();

    const reading = w.find(".rc__reading").text();
    expect(reading).toContain(messages.uz["load.terms.absent"]);
    expect(reading).not.toContain(messages.en["load.terms.absent"]);
    // a contract silent on detention must never read as a detention rate of zero
    expect(reading).not.toContain("$0.00");
    expect(reading).not.toContain("0 ");
  });

  it("keeps the contract's own wording verbatim and English in every locale", async () => {
    // §12.3: a translated clause cannot be compared against the paper in the driver's
    // hand, and a claim is argued from the original.
    for (const locale of LAUNCH_LOCALES) {
      useI18n().setLocale(locale);
      stub(FULL);
      const w = await readSheet();

      expect(w.text(), `clause wording missing in ${locale}`).toContain(
        "50% of linehaul if cancelled after arrival",
      );
      // and the screen SAYS why it is English rather than leaving it to look like a
      // translation somebody forgot
      expect(w.find(".rc__original-note").text()).toBe(messages[locale]["load.rc_original_note"]);
      w.unmount();
      vi.unstubAllGlobals();
    }
  });

  it("marks the verbatim wording as English for a screen reader", async () => {
    // a Punjabi page reading an English clause aloud in Punjabi phonology is unusable;
    // `lang` is what lets the reader switch voice
    useI18n().setLocale("pa");
    stub(FULL);
    const w = await readSheet();

    expect(w.find(".rc__termtext").attributes("lang")).toBe("en");
  });

  it("shows no reading block at all when the parse could not read the paper", async () => {
    // an unreadable rate con must not produce a tidy summary of nothing
    stub({ document_id: "d", readable: false, parsed: null, silent_on: [], stops: [],
           contact: { email: null, phone: null } });
    const w = await readSheet();

    expect(w.find(".rc__reading").exists()).toBe(false);
  });
});
