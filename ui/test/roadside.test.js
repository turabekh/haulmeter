// AI-CONTEXT: M15's driver surfaces (E3 §E3.1.6), and what each of them must not do.
//
// The four states are asserted per surface because §22.3 requires them and because the
// EMPTY one is the state this module actually ships in today: nothing has been through
// review, so `GET /roadside/scenarios` legitimately returns nothing. A surface that
// rendered a spinner forever, or an offer that 404s on tap, would both look like working
// code from a passing suite.
//
// The band tests are the ones that matter most. `label_key` arrives from the server
// already carrying its provisional state, and the whole point of that design is that a
// client cannot drop the word by accident — so these assert the surface RENDERS THE KEY
// rather than deciding anything, and that a raw key never reaches a driver.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import RoadsideSurface from "../src/surfaces/RoadsideSurface.vue";
import RoadsideResultSurface from "../src/surfaces/RoadsideResultSurface.vue";
import RoadsideConsentSurface from "../src/surfaces/RoadsideConsentSurface.vue";
import RoadsideCoachSurface from "../src/surfaces/RoadsideCoachSurface.vue";
import RoadsideSessionSurface from "../src/surfaces/RoadsideSessionSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import { DriverState, useDriverState, __resetStateForTests } from "../src/core/state.js";
import messages from "../src/core/i18n/en.json";

function jsonOk(body, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
}

function stubFetch(routeMap) {
  const fn = vi.fn().mockImplementation((url, opts) => {
    const path = String(url).replace("http://localhost:8008", "").split("?")[0];
    const key = opts?.method ? `${opts.method} ${path}` : path;
    if (key in routeMap) return routeMap[key];
    if (path in routeMap) return routeMap[path];
    return jsonOk({});
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const router = () => createRouter({ history: createMemoryHistory(), routes });

// AI-CONTEXT: these surfaces read `route.params`, so a bare `plugins: [router()]` leaves
// the id undefined and the surface fetches `/roadside/session/undefined/result` — which
// the stub answers with `{}` and the assertion then measures an empty screen. Landing the
// router on the real route first is the difference between testing the surface and
// testing the fallback.
async function at(name, params) {
  const r = router();
  r.push({ name, params });
  await r.isReady();
  return r;
}

const SCENARIO = { id: "s-1", difficulty: "clear", intents: ["destination"] };

beforeEach(() => setToken("tok-driver"));
afterEach(() => {
  vi.unstubAllGlobals();
  __resetStateForTests();
  logout();
});

describe("Roadside — the catalogue", () => {
  it("says WHY it is empty rather than showing an empty screen", async () => {
    // the state the module genuinely ships in: nothing reviewed, so nothing offered
    stubFetch({ "/roadside/scenarios": jsonOk({ scenarios: [] }) });
    const w = mount(RoadsideSurface, { global: { plugins: [router()] } });
    await flushPromises();

    expect(w.text()).toContain(messages["roadside.empty"]);
    expect(w.find(".roadside__cta").exists()).toBe(false);
  });

  it("treats the module gate as an absence, not an error", async () => {
    // 404 is `require_module` saying the module is off (entry 105). A driver who has not
    // been given the feature must not be told something failed.
    stubFetch({ "/roadside/scenarios": jsonOk({ detail: "not enabled" }, 404) });
    const w = mount(RoadsideSurface, { global: { plugins: [router()] } });
    await flushPromises();

    expect(w.text()).toContain(messages["roadside.empty"]);
    expect(w.text()).not.toContain(messages["roadside.failed"]);
  });

  it("offers the check when there is something to run", async () => {
    stubFetch({ "/roadside/scenarios": jsonOk({ scenarios: [SCENARIO] }) });
    const w = mount(RoadsideSurface, { global: { plugins: [router()] } });
    await flushPromises();

    expect(w.find(".roadside__cta").text()).toBe(messages["roadside.start"]);
  });

  it("withdraws the offer while the truck is moving (SM-3, Q-4)", async () => {
    stubFetch({ "/roadside/scenarios": jsonOk({ scenarios: [SCENARIO] }) });
    const w = mount(RoadsideSurface, { global: { plugins: [router()] } });
    await flushPromises();

    useDriverState().setState(DriverState.DRIVING);
    await flushPromises();

    expect(w.find(".roadside__cta").exists()).toBe(false);
    expect(w.text()).toContain(messages["roadside.session.paused_driving"]);
  });

  it("reports a server failure as a failure, with a way back", async () => {
    stubFetch({ "/roadside/scenarios": jsonOk({}, 500) });
    const w = mount(RoadsideSurface, { global: { plugins: [router()] } });
    await flushPromises();

    expect(w.find(".roadside__failed").exists()).toBe(true);
    expect(w.find(".roadside__retry").exists()).toBe(true);
  });
});

describe("Roadside — consent", () => {
  it("states all three facts before any microphone exists", async () => {
    const w = mount(RoadsideConsentSurface, {
      global: { plugins: [await at("roadside-consent", { scenarioId: "s-1" })] },
    });
    await flushPromises();

    const text = w.text();
    expect(text).toContain(messages["roadside.consent.recording"]);
    // the 30-day promise F6's retention sweep actually keeps (entry 178)
    expect(text).toContain(messages["roadside.consent.retention"]);
    expect(text).toContain(messages["roadside.consent.mic"]);
  });

  it("gives declining the same weight as agreeing", async () => {
    const w = mount(RoadsideConsentSurface, {
      global: { plugins: [await at("roadside-consent", { scenarioId: "s-1" })] },
    });
    await flushPromises();

    // a decline rendered as a faint link is not a choice being offered, and the value of
    // the consent record rests on the choice being real
    expect(w.find(".consent__decline").element.tagName).toBe("BUTTON");
    expect(w.find(".consent__agree").element.tagName).toBe("BUTTON");
  });

  it("sends consent WITH the request that opens the session", async () => {
    const fetchMock = stubFetch({
      "POST /roadside/session": jsonOk({ session_id: "sess-1", consent_at: "2026-08-18T00:00:00Z" }),
    });
    const w = mount(RoadsideConsentSurface, {
      global: { plugins: [await at("roadside-consent", { scenarioId: "s-1" })] },
    });
    await flushPromises();

    await w.find(".consent__agree").trigger("click");
    await flushPromises();

    const body = JSON.parse(fetchMock.mock.calls.find((c) => c[1]?.method === "POST")[1].body);
    expect(body.consented).toBe(true);
  });

  it("withdraws the agree action at speed", async () => {
    const w = mount(RoadsideConsentSurface, {
      global: { plugins: [await at("roadside-consent", { scenarioId: "s-1" })] },
    });
    await flushPromises();

    useDriverState().setState(DriverState.DRIVING);
    await flushPromises();

    expect(w.find(".consent__agree").exists()).toBe(false);
    expect(w.find(".consent__decline").exists()).toBe(true);
  });
});

describe("Roadside — the result", () => {
  const RESULT = {
    session_id: "sess-1",
    band: "green",
    provisional: true,
    label_key: "roadside.band.green_provisional",
    agreement_pct: null,
    review_needed_turns: 0,
    failure_tags: [],
  };

  it("renders the band the server named, provisional word included", async () => {
    stubFetch({ "/roadside/session/sess-1/result": jsonOk(RESULT) });
    const w = mount(RoadsideResultSurface, {
      global: { plugins: [await at("roadside-result", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    expect(w.find(".result__band").text()).toBe(messages["roadside.band.green_provisional"]);
    expect(w.text()).toContain(messages["roadside.result.provisional"]);
  });

  it("has a string for every band key the server can send", () => {
    // the API composes `roadside.band.{band}` + optional `_provisional`, so a missing
    // catalogue entry renders a RAW KEY to a driver — silently, because `t()` falls back
    // to the key in production
    for (const band of ["green", "yellow", "red"]) {
      expect(messages[`roadside.band.${band}`]).toBeTruthy();
      expect(messages[`roadside.band.${band}_provisional`]).toBeTruthy();
    }
  });

  it("shows no percentage anywhere (E3 §E3.1.4)", async () => {
    stubFetch({
      "/roadside/session/sess-1/result": jsonOk({ ...RESULT, agreement_pct: 92 }),
    });
    const w = mount(RoadsideResultSurface, {
      global: { plugins: [await at("roadside-result", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    // a naked number invites comparison on a scale nobody has calibrated
    expect(w.text()).not.toMatch(/\d+\s*%/);
    expect(w.text()).not.toContain("92");
  });

  it("names the skills to practise, not the faults", async () => {
    stubFetch({
      "/roadside/session/sess-1/result": jsonOk({
        ...RESULT,
        failure_tags: ["INTENT_MISUNDERSTOOD", "NO_RESPONSE"],
      }),
    });
    const w = mount(RoadsideResultSurface, {
      global: { plugins: [await at("roadside-result", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    expect(w.text()).toContain(messages["roadside.tag.INTENT_MISUNDERSTOOD"]);
    expect(w.text()).toContain(messages["roadside.tag.NO_RESPONSE"]);
    // the raw tag is an internal token and must never reach a driver
    expect(w.text()).not.toContain("INTENT_MISUNDERSTOOD");
  });

  it("has a string for all ten failure tags", () => {
    const TAGS = [
      "INTENT_MISUNDERSTOOD", "SLOT_WRONG_FACT", "MULTI_PART_PARTIAL", "REPETITION_REQUIRED",
      "TERMINOLOGY_UNKNOWN", "SIGN_INCORRECT", "DYNAMIC_SIGN_INCORRECT", "UNINTELLIGIBLE",
      "IRRELEVANT", "NO_RESPONSE",
    ];
    for (const tag of TAGS) expect(messages[`roadside.tag.${tag}`]).toBeTruthy();
  });

  it("states the turns waiting on a human rather than hiding them (Q-2)", async () => {
    stubFetch({
      "/roadside/session/sess-1/result": jsonOk({ ...RESULT, review_needed_turns: 2 }),
    });
    const w = mount(RoadsideResultSurface, {
      global: { plugins: [await at("roadside-result", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    expect(w.find(".result__review").text()).toContain("2");
    // and the placeholder actually substituted — a visible {n} is the entry-74 defect
    expect(w.text()).not.toContain("{n}");
  });
});

describe("Roadside — the teaching loop (FR5)", () => {
  const PLAN = {
    intent_key: "hos_hours_driven",
    missed_question: "How many hours have you been driving today?",
    missed_question_audio: null,
    explanation: null,
    glosses: {},
    phrase_family: [{ text: "How long you been behind the wheel?", audio_url: null }],
    model_answer: "I've been driving six hours today.",
    model_answer_audio: null,
    retest_variant_id: "v-1",
    retest_question: "How long you been behind the wheel?",
  };

  it("says the coaching is not in your language yet, rather than showing English", async () => {
    // Q-9. The server sends `explanation: null`; a surface that filled that gap from an
    // English row would defeat the law in the one place a domain test cannot see.
    stubFetch({ "/roadside/session/sess-1/coaching": jsonOk({ coaching: [PLAN] }) });
    const w = mount(RoadsideCoachSurface, {
      global: { plugins: [await at("roadside-coach", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    expect(w.text()).toContain(messages["roadside.coach.no_explanation"]);
  });

  it("shows the explanation when the driver's language has one", async () => {
    stubFetch({
      "/roadside/session/sess-1/coaching": jsonOk({
        coaching: [{ ...PLAN, explanation: "'clock' — qolgan haydash vaqti" }],
      }),
    });
    const w = mount(RoadsideCoachSurface, {
      global: { plugins: [await at("roadside-coach", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    expect(w.text()).toContain("'clock' — qolgan haydash vaqti");
    expect(w.text()).not.toContain(messages["roadside.coach.no_explanation"]);
  });

  it("walks the loop: the miss, the family, the model answer, the retest", async () => {
    stubFetch({ "/roadside/session/sess-1/coaching": jsonOk({ coaching: [PLAN] }) });
    const w = mount(RoadsideCoachSurface, {
      global: { plugins: [await at("roadside-coach", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    const text = w.text();
    expect(text).toContain("How many hours have you been driving today?");
    expect(text).toContain("How long you been behind the wheel?");
    expect(text).toContain("I've been driving six hours today.");
    expect(text).toContain(messages["roadside.coach.shadow"]);
  });

  it("says there is nothing to practise when nothing was missed", async () => {
    stubFetch({ "/roadside/session/sess-1/coaching": jsonOk({ coaching: [] }) });
    const w = mount(RoadsideCoachSurface, {
      global: { plugins: [await at("roadside-coach", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    expect(w.text()).toContain(messages["roadside.coach.empty"]);
  });

  it("withdraws the retest microphone at speed", async () => {
    stubFetch({ "/roadside/session/sess-1/coaching": jsonOk({ coaching: [PLAN] }) });
    const w = mount(RoadsideCoachSurface, {
      global: { plugins: [await at("roadside-coach", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    useDriverState().setState(DriverState.DRIVING);
    await flushPromises();

    expect(w.find(".coach__mic").exists()).toBe(false);
  });
});

describe("Roadside — the session surface renders what the socket sends", () => {
  // AI-CONTEXT: THIS EXISTS BECAUSE AN EDIT SILENTLY DID NOTHING. `playInOrder` was
  // defined and never called and `echoText` was declared and never assigned, because a
  // string replacement's anchor had already been changed by an earlier one. Every server
  // test passed, the frame carried the fields, and the driver heard silence between
  // questions. A frame the surface does not read is a feature that does not exist.
  let socket;

  function stubSocket() {
    class FakeSocket {
      static OPEN = 1;
      constructor() {
        this.readyState = 1;
        this.sent = [];
        socket = this;
      }
      send(data) {
        this.sent.push(JSON.parse(data));
      }
      close() {}
    }
    vi.stubGlobal("WebSocket", FakeSocket);
    vi.stubGlobal("Audio", class {
      play() {
        return Promise.resolve();
      }
    });
    // AI-CONTEXT: the surface opens the mic itself when a question has no audio to wait
    // for — that is the hands-free behaviour, not a test artifact. Without a stubbed
    // `mediaDevices` it correctly renders MIC_DENIED and the assertion measures that
    // screen instead of the one under test.
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: () => Promise.resolve({ getTracks: () => [] }) },
    });
    vi.stubGlobal("MediaRecorder", class {
      constructor() {
        this.state = "inactive";
      }
      start() {
        this.state = "recording";
      }
      stop() {
        this.state = "inactive";
      }
    });
  }

  function frame(payload) {
    socket.onmessage({ data: JSON.stringify(payload) });
  }

  it("shows the officer's greeting on the first question", async () => {
    stubSocket();
    const w = mount(RoadsideSessionSurface, {
      global: { plugins: [await at("roadside-session", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    frame({
      type: "officer",
      text: "Where are you headed?",
      audio_url: null,
      opening: "Afternoon. Just a routine check.",
      opening_audio_url: null,
    });
    await flushPromises();

    expect(w.text()).toContain("Afternoon. Just a routine check.");
    expect(w.text()).toContain("Where are you headed?");
  });

  it("says the driver's own answer back, then acknowledges", async () => {
    stubSocket();
    const w = mount(RoadsideSessionSurface, {
      global: { plugins: [await at("roadside-session", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    frame({ type: "officer", text: "Where are you headed?", audio_url: null });
    await flushPromises();
    frame({
      type: "scored",
      transcript: "i am headed to chicago",
      review_needed: false,
      echo: "Chicago",
      echo_audio_url: null,
      ack: "Okay.",
      ack_audio_url: null,
      tags: [],
    });
    await flushPromises();

    expect(w.text()).toContain("Chicago");
    expect(w.text()).toContain("Okay.");
    expect(w.text()).toContain("i am headed to chicago");
  });

  it("shows the officer's line before his voice exists, and keeps the mic shut", async () => {
    // AI-CONTEXT: THE LATENCY FIX, ASSERTED ON THE SCREEN. The model takes ~3.0s to
    // choose the line and Azure ~1.2s to say it; serialized behind one frame that was
    // 4.2s of a screen where nothing happened. The text now ships first — but the mic
    // must NOT open on it, or the driver is recorded answering a question they have not
    // heard. Both halves are the test.
    stubSocket();
    const getUserMedia = vi.fn(() => Promise.resolve({ getTracks: () => [] }));
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    const w = mount(RoadsideSessionSurface, {
      global: { plugins: [await at("roadside-session", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    frame({ type: "officer", text: "Let me see your logbook.", audio_url: null, audio_pending: true });
    await flushPromises();

    expect(w.text()).toContain("Let me see your logbook.");
    expect(getUserMedia).not.toHaveBeenCalled();

    frame({ type: "officer_audio", seq: 1, audio_url: "/media/document/abc?sig=x" });
    await flushPromises();

    expect(w.find("audio").attributes("src")).toContain("/media/document/abc");
  });

  it("releases the driver to answer when the officer's voice fails to synthesize", async () => {
    // A voice that never arrives must not become a mic that never opens: the question is
    // readable, so the driver can answer it. Silence beats a dead screen.
    stubSocket();
    const getUserMedia = vi.fn(() => Promise.resolve({ getTracks: () => [] }));
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    mount(RoadsideSessionSurface, {
      global: { plugins: [await at("roadside-session", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    frame({ type: "officer", text: "Let me see your logbook.", audio_url: null, audio_pending: true });
    await flushPromises();
    expect(getUserMedia).not.toHaveBeenCalled();

    frame({ type: "officer_audio", seq: 1, audio_url: null });
    await flushPromises();

    expect(getUserMedia).toHaveBeenCalled();
  });
});
