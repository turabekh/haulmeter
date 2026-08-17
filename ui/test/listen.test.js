// AI-CONTEXT: the hands-free detector (M15-FR3). Hold-to-talk was the single most robotic
// thing about the simulation — nobody holds a button while answering a police officer, and
// a driver at a window has their hands on paperwork.
//
// These drive the analyser directly rather than a real microphone: the detector's contract
// is "given these levels over time, start, end, or give up", and that is testable without
// audio hardware. What it cannot prove is that a truck cab sounds the way the fixtures do —
// that is what the calibration exists for and what a real session has to confirm.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { listenForSpeech, CALIBRATION_MS, SPEECH_FACTOR } from "../src/core/listen.js";

let level = 0;
let frame = null;
let now = 0;

function harness() {
  now = 0;
  vi.spyOn(Date, "now").mockImplementation(() => now);
  vi.stubGlobal("requestAnimationFrame", (cb) => {
    frame = cb;
    return 1;
  });
  vi.stubGlobal("cancelAnimationFrame", () => {
    frame = null;
  });

  const analyser = {
    fftSize: 8,
    getFloatTimeDomainData: (buf) => buf.fill(level),
    connect: () => {},
  };
  vi.stubGlobal("AudioContext", class {
    createMediaStreamSource() {
      return { connect: () => {}, disconnect: () => {} };
    }
    createAnalyser() {
      return analyser;
    }
    close() {}
  });
}

function advance(ms, at) {
  level = at;
  now += ms;
  if (frame) {
    const cb = frame;
    frame = null;
    cb();
  }
}

beforeEach(harness);
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("hands-free listening", () => {
  it("learns the room's floor before deciding anything", () => {
    // a fixed dB floor either never triggers in an idling cab or never stops in a quiet
    // one. The first moments calibrate; speech is a multiple of what was learned.
    const started = vi.fn();
    listenForSpeech({}, { onSpeechStart: started });

    // loud noise DURING calibration is the room, not speech
    advance(100, 0.2);
    advance(100, 0.2);
    expect(started).not.toHaveBeenCalled();
  });

  it("starts on speech above the learned floor", () => {
    const started = vi.fn();
    listenForSpeech({}, { onSpeechStart: started });

    advance(CALIBRATION_MS + 1, 0.01); // calibrate on a quiet room
    advance(50, 0.01 * SPEECH_FACTOR * 3); // then talk
    expect(started).toHaveBeenCalled();
  });

  it("ends the turn after a pause, not on the first gap", () => {
    // "I have been driving… six hours" has a gap in the middle of it. Ending there would
    // cut a driver off mid-answer, which is the rudest thing this can do.
    const ended = vi.fn();
    listenForSpeech({}, { onSpeechEnd: ended });

    advance(CALIBRATION_MS + 1, 0.01);
    advance(50, 0.5);
    advance(400, 0.001); // a breath
    expect(ended).not.toHaveBeenCalled();

    advance(50, 0.5); // still talking
    // TWO ticks: the first marks where silence began, the second measures it. A real
    // requestAnimationFrame fires every ~16ms, so this is the harness being coarse rather
    // than the detector needing a nudge.
    advance(16, 0.001);
    advance(1200, 0.001);
    expect(ended).toHaveBeenCalled();
  });

  it("gives up rather than listening forever when it hears nothing", () => {
    // a loud cab or a dead mic. The surface hands the driver a button instead of leaving
    // them talking into something that is not listening.
    const timedOut = vi.fn();
    listenForSpeech({}, { onTimeout: timedOut }, { timeoutMs: 1000 });

    advance(CALIBRATION_MS + 1, 0.001);
    advance(2000, 0.001);
    expect(timedOut).toHaveBeenCalled();
  });

  it("degrades to nothing when the browser has no Web Audio", () => {
    vi.stubGlobal("AudioContext", undefined);
    vi.stubGlobal("webkitAudioContext", undefined);
    const handle = listenForSpeech({}, {});
    expect(typeof handle.stop).toBe("function"); // the caller keeps its button
  });
});
