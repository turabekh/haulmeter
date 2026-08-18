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
import RoadsideHomeSurface from "../src/surfaces/RoadsideHomeSurface.vue";
import RoadsideResultSurface from "../src/surfaces/RoadsideResultSurface.vue";
import RoadsideConsentSurface from "../src/surfaces/RoadsideConsentSurface.vue";
import RoadsideCoachSurface from "../src/surfaces/RoadsideCoachSurface.vue";
import RoadsideSessionSurface from "../src/surfaces/RoadsideSessionSurface.vue";
import RoadsideDrillSurface from "../src/surfaces/RoadsideDrillSurface.vue";
import RoadsideTranscriptSurface from "../src/surfaces/RoadsideTranscriptSurface.vue";
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

describe("Roadside — the tab root", () => {
  // AI-CONTEXT: these five moved from `RoadsideSurface` when decision 207 made Roadside a
  // tab and the hub became a program home. The BEHAVIOURS are unchanged and that is why
  // they moved rather than went — a new surface at an old route inherits every promise
  // the old one made. Only the selectors differ: the offer is now a card action.
  it("says WHY it is empty rather than showing an empty screen", async () => {
    // the state the module genuinely ships in: nothing reviewed, so nothing offered
    stubFetch({ "/roadside/scenarios": jsonOk({ scenarios: [] }) });
    const w = mount(RoadsideHomeSurface, { global: { plugins: [router()] } });
    await flushPromises();

    expect(w.text()).toContain(messages["roadside.empty"]);
    expect(w.find(".card__cta").exists()).toBe(false);
  });

  it("treats the module gate as an absence, not an error", async () => {
    // 404 is `require_module` saying the module is off (entry 105). A driver who has not
    // been given the feature must not be told something failed.
    stubFetch({ "/roadside/scenarios": jsonOk({ detail: "not enabled" }, 404) });
    const w = mount(RoadsideHomeSurface, { global: { plugins: [router()] } });
    await flushPromises();

    expect(w.text()).toContain(messages["roadside.empty"]);
    expect(w.text()).not.toContain(messages["roadside.failed"]);
  });

  it("offers the check when there is something to run", async () => {
    stubFetch({ "/roadside/scenarios": jsonOk({ scenarios: [SCENARIO] }) });
    const w = mount(RoadsideHomeSurface, { global: { plugins: [router()] } });
    await flushPromises();

    expect(w.find(".card__cta").text()).toBe(messages["roadside.start"]);
  });

  it("withdraws the offer while the truck is moving (SM-3, Q-4)", async () => {
    stubFetch({ "/roadside/scenarios": jsonOk({ scenarios: [SCENARIO] }) });
    const w = mount(RoadsideHomeSurface, { global: { plugins: [router()] } });
    await flushPromises();

    useDriverState().setState(DriverState.DRIVING);
    await flushPromises();

    expect(w.find(".card__cta").exists()).toBe(false);
    expect(w.text()).toContain(messages["roadside.session.paused_driving"]);
  });

  it("reports a server failure as a failure, with a way back", async () => {
    stubFetch({ "/roadside/scenarios": jsonOk({}, 500) });
    const w = mount(RoadsideHomeSurface, { global: { plugins: [router()] } });
    await flushPromises();

    expect(w.find('[role="alert"]').exists()).toBe(true);
    expect(w.find(".home__retry").exists()).toBe(true);
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

  it("says what it is waiting for instead of showing anonymous skeletons", async () => {
    // AI-CONTEXT: scoring moved off the conversation so the officer could answer in ~2s,
    // which means the model's judgement of every turn is owed on THIS screen. Measured on
    // production: a driver who left a 3-turn stop early waited 13.2s in front of grey
    // blocks with nothing telling them anything was happening.
    stubFetch({ "/roadside/session/sess-1/result": new Promise(() => {}) });

    const w = mount(RoadsideResultSurface, {
      global: { plugins: [await at("roadside-result", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    expect(w.text()).toContain(messages["roadside.result.working"]);
  });

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

  it("a tap changes the button, so the driver knows it registered", async () => {
    // AI-CONTEXT: THE DEFECT THE OWNER REPORTED AS "the play buttons do not work". Every
    // one of them did play — verified end to end against production, HTTP 206 and audible
    // — but the screen said NOTHING back on tap, so a phone on silent, a dead bluetooth
    // route and a genuinely broken URL were indistinguishable from each other and from a
    // button that did nothing at all. The old handler additionally swallowed every
    // rejection, which is why a real report left nothing behind to diagnose.
    const played = [];
    vi.stubGlobal("Audio", class {
      constructor(src) { this.src = src; played.push(src); }
      play() { return Promise.resolve(); }
      pause() {}
    });
    stubFetch({
      "/roadside/session/sess-1/coaching": jsonOk({
        coaching: [{ ...PLAN, missed_question_audio: "/media/document/mq" }],
      }),
    });
    const w = mount(RoadsideCoachSurface, {
      global: { plugins: [await at("roadside-coach", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    const button = w.find(".coach__play");
    expect(button.attributes("data-playing")).toBe("false");

    await button.trigger("click");
    await flushPromises();

    expect(played).toHaveLength(1);
    expect(w.find(".coach__play").attributes("data-playing")).toBe("true");
    expect(w.find(".coach__play").text()).toContain(messages["roadside.transcript.stop"]);
  });

  it("plays one clip at a time — a second tap does not talk over the first", async () => {
    const paused = [];
    vi.stubGlobal("Audio", class {
      constructor(src) { this.src = src; }
      play() { return Promise.resolve(); }
      pause() { paused.push(this.src); }
    });
    stubFetch({
      "/roadside/session/sess-1/coaching": jsonOk({
        coaching: [{
          ...PLAN,
          missed_question_audio: "/media/document/mq",
          phrase_family: [{ text: "How long you been behind the wheel?", audio_url: "/media/document/pf" }],
        }],
      }),
    });
    const w = mount(RoadsideCoachSurface, {
      global: { plugins: [await at("roadside-coach", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    const buttons = w.findAll(".coach__play");
    await buttons[0].trigger("click");
    await flushPromises();
    await buttons[1].trigger("click");
    await flushPromises();

    expect(paused.some((src) => src.endsWith("/media/document/mq"))).toBe(true);
    expect(w.findAll(".coach__play")[0].attributes("data-playing")).toBe("false");
    expect(w.findAll(".coach__play")[1].attributes("data-playing")).toBe("true");
  });

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
    // AI-CONTEXT: and NOT a receipt. The spoken echo ("Chicago.") is how a driver knows
    // they were understood; printing the transcript back with a replay scrubber and a
    // "Next question" button is what made a working conversation read as a quiz. A real
    // window does not show you what it thought you said.
    expect(w.text()).not.toContain("i am headed to chicago");
    expect(w.find(".session__next").exists()).toBe(false);
    expect(w.find("audio[controls]").exists()).toBe(false);
  });

  it("makes a listening noise the moment the driver stops talking", async () => {
    // AI-CONTEXT: THE GAP-FILLER, asserted on WHEN it plays rather than that it exists.
    // Its entire value is landing in the silence a person leaves when they stop speaking —
    // ~1.5s before the officer can answer. Played after the upload it would arrive a round
    // trip late, in the middle of the gap instead of at the start of it. So the assertion
    // is that the sound is constructed during sendAnswer, before anything is sent.
    stubSocket();
    // records PLAYS, not constructions — the clips are preloaded when the pool arrives, so
    // counting `new Audio()` would count the preload and prove nothing about timing
    const played = [];
    vi.stubGlobal("Audio", class {
      constructor(src) {
        this.src = src;
      }
      load() {}
      play() {
        played.push(this.src);
        return Promise.resolve();
      }
    });
    const w = mount(RoadsideSessionSurface, {
      global: { plugins: [await at("roadside-session", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    frame({
      type: "officer",
      text: "Where are you headed?",
      audio_url: null,
      thinking_audio_urls: ["/media/document/mm?sig=x"],
    });
    await flushPromises();

    expect(played).toHaveLength(0); // preloaded, but not yet sounded
    expect(socket.sent.some((f) => f.type === "answer")).toBe(false);

    // record how many noises had played AT THE MOMENT the answer went up, so this
    // asserts the ORDER rather than merely that both eventually happened
    let playedWhenSent = null;
    const realSend = socket.send.bind(socket);
    socket.send = (data) => {
      if (JSON.parse(data).type === "answer" && playedWhenSent === null) {
        playedWhenSent = played.length;
      }
      realSend(data);
    };

    await w.vm.sendAnswer();
    await flushPromises();

    expect(socket.sent.some((f) => f.type === "answer")).toBe(true);
    expect(played.some((src) => src.includes("/media/document/mm"))).toBe(true);
    expect(playedWhenSent).toBe(1); // the noise was already out before the upload
  });

  it("shows what it heard ONLY when it did not understand", async () => {
    // The one case a driver cannot infer from the officer's reply, and the case Q-2 says
    // must be stated rather than hidden — so the receipt survives exactly here.
    stubSocket();
    const w = mount(RoadsideSessionSurface, {
      global: { plugins: [await at("roadside-session", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    frame({ type: "officer", text: "Where are you headed?", audio_url: null });
    await flushPromises();
    frame({
      type: "scored",
      transcript: "mmff whrr",
      review_needed: true,
      echo: "",
      echo_audio_url: null,
      ack: "",
      ack_audio_url: null,
      tags: [],
    });
    await flushPromises();

    expect(w.text()).toContain("mmff whrr");
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

  it("plays the bytes off the socket rather than fetching them", async () => {
    // AI-CONTEXT: measured from a distant client, fetching the mp3 from `audio_url` cost
    // 1050ms AFTER the frame arrived — a fresh TLS round trip for 17KB — so the real time
    // to first speech was a second worse than every server-side number said. The socket
    // already carried the sentence; it now carries the sound. `audio_url` still rides
    // along, so this asserts which one the surface actually PLAYS.
    stubSocket();
    const w = mount(RoadsideSessionSurface, {
      global: { plugins: [await at("roadside-session", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    frame({ type: "officer", text: "Where to?", audio_url: null, audio_pending: true });
    await flushPromises();
    frame({
      type: "officer_audio",
      seq: 1,
      audio_url: "/media/document/abc?sig=x",
      audio_b64: "QUJD",
    });
    await flushPromises();

    const src = w.find("audio").attributes("src");
    expect(src).toBe("data:audio/mpeg;base64,QUJD");
    expect(src).not.toContain("/media/document");
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

describe("Roadside — today's practice", () => {
  // AI-CONTEXT: THIS SURFACE HAD NO TESTS AT ALL, which is most of why it was still on the
  // interaction entry 187 removed from the stop: hold-to-talk, and a question that waited
  // to be tapped. Nothing failed when the rest of the module moved on, because nothing was
  // watching. These cover the behaviour a driver meets first.
  const PLAN = {
    plan: {
      id: "p-1",
      day: 3,
      completed: false,
      items: [
        { variant_id: "v-1", text: "How much drive time do you have today?",
          audio_url: "/media/document/a?sig=x" },
        { variant_id: "v-2", text: "Where's this load headed?", audio_url: null },
      ],
    },
  };

  function stubMedia() {
    const getUserMedia = vi.fn(() => Promise.resolve({ getTracks: () => [] }));
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
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
    return getUserMedia;
  }

  it("asks the question out loud and opens the mic when it finishes — no taps", async () => {
    const getUserMedia = stubMedia();
    const clips = [];
    vi.stubGlobal("Audio", class {
      constructor(src) {
        this.src = src;
        clips.push(this);
      }
      play() {
        return Promise.resolve();
      }
      pause() {}
    });
    stubFetch({ "/roadside/drill/today": jsonOk(PLAN) });

    const w = mount(RoadsideDrillSurface, {
      global: { plugins: [await at("roadside-drill", {})] },
    });
    await flushPromises();

    // the question plays itself
    expect(clips.some((c) => String(c.src).includes("/media/document/a"))).toBe(true);
    // ...and the microphone is NOT open while he is still asking
    expect(getUserMedia).not.toHaveBeenCalled();

    clips[0].onended();
    await flushPromises();

    expect(getUserMedia).toHaveBeenCalled();
    expect(w.text()).toContain("How much drive time do you have today?");
  });

  it("opens the mic anyway when the question has no audio to wait for", async () => {
    const getUserMedia = stubMedia();
    vi.stubGlobal("Audio", class {
      play() {
        return Promise.resolve();
      }
      pause() {}
    });
    const noAudio = {
      plan: { ...PLAN.plan, items: [{ variant_id: "v-2", text: "Where's this load headed?", audio_url: null }] },
    };
    stubFetch({ "/roadside/drill/today": jsonOk(noAudio) });

    mount(RoadsideDrillSurface, { global: { plugins: [await at("roadside-drill", {})] } });
    await flushPromises();

    // a silent question must not leave the driver waiting for a mic that never opens
    expect(getUserMedia).toHaveBeenCalled();
  });

  it("says nothing is due rather than showing an empty screen", async () => {
    stubMedia();
    vi.stubGlobal("Audio", class {
      play() {
        return Promise.resolve();
      }
      pause() {}
    });
    stubFetch({ "/roadside/drill/today": jsonOk({ plan: null }) });

    const w = mount(RoadsideDrillSurface, {
      global: { plugins: [await at("roadside-drill", {})] },
    });
    await flushPromises();

    expect(w.text()).toContain(messages["roadside.drill.none"]);
  });
});

describe("Roadside — the stop played back", () => {
  // AI-CONTEXT: `Turn.audio_ref` existed from the first migration, `classify_audio_30d`
  // existed, the retention sweep ran unflagged — and nothing ever wrote the column. The
  // consent screen promised every driver "the voice recording, the 30-day deletion with
  // scores kept" while the socket transcribed the audio and dropped it.
  const SCRIPT = {
    session_id: "sess-1",
    completed: true,
    turns: [
      { seq: 1, speaker: "officer", text: "Where are you headed?",
        audio_url: "/media/document/o1?sig=x", unclear: false },
      { seq: 2, speaker: "driver", text: "i am headed to dallas",
        audio_url: "/media/document/d1?sig=x", unclear: false },
    ],
  };

  it("shows both voices in order, each playable", async () => {
    const played = [];
    vi.stubGlobal("Audio", class {
      constructor(src) {
        this.src = src;
      }
      play() {
        played.push(this.src);
        return Promise.resolve();
      }
      pause() {}
    });
    stubFetch({ "/roadside/session/sess-1/transcript": jsonOk(SCRIPT) });

    const w = mount(RoadsideTranscriptSurface, {
      global: { plugins: [await at("roadside-transcript", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    expect(w.text()).toContain("Where are you headed?");
    expect(w.text()).toContain("i am headed to dallas");

    await w.findAll(".turn__play")[1].trigger("click");
    await flushPromises();
    expect(played[0]).toContain("/media/document/d1");
  });

  it("keeps the words when the recording has expired, and says why", async () => {
    // the 30-day sweep takes the voice and leaves the text — consent describes exactly
    // this, so the screen must not offer a play button that fails when tapped
    vi.stubGlobal("Audio", class {
      play() {
        return Promise.resolve();
      }
      pause() {}
    });
    const expired = {
      ...SCRIPT,
      turns: [{ seq: 1, speaker: "driver", text: "something i said a month ago",
                audio_url: null, unclear: false }],
    };
    stubFetch({ "/roadside/session/sess-1/transcript": jsonOk(expired) });

    const w = mount(RoadsideTranscriptSurface, {
      global: { plugins: [await at("roadside-transcript", { sessionId: "sess-1" })] },
    });
    await flushPromises();

    expect(w.text()).toContain("something i said a month ago");
    expect(w.findAll(".turn__play")).toHaveLength(0);
    expect(w.text()).toContain(messages["roadside.transcript.expired"]);
  });
});
