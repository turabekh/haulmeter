// AI-CONTEXT: hands-free listening (M15-FR3) — the single biggest thing between a
// simulated conversation and a form with a microphone attached.
//
// HOLD-TO-TALK IS THE ROBOT. Nobody holds a button while answering a police officer. It
// also fails the situation the module simulates: a driver at a window has their hands on
// paperwork, a licence, a phone they are holding up. So the officer finishes speaking, the
// mic opens by itself, and the turn ends when the driver stops talking.
//
// WHY AN ENERGY GATE AND NOT A LIBRARY. The browser ships an analyser; the whole detector
// is a moving average of RMS against a floor learned from the room. A VAD model would be
// megabytes over a truck-stop connection to make the same decision, and this one degrades
// honestly: if it never hears speech, `onTimeout` fires and the surface offers the button.
//
// THE THRESHOLD IS LEARNED, NOT CONSTANT. A truck cab idling is not a quiet kitchen, and a
// fixed dB floor either never triggers in one or never stops in the other. The first
// moments of the stream calibrate the floor, and speech is a multiple of it.
export const CALIBRATION_MS = 400;
// how much louder than the room counts as talking
export const SPEECH_FACTOR = 2.5;
// silence that ends a turn. Long enough to survive the pause inside "I have been driving…
// six hours", short enough that a finished answer does not sit there.
export const END_SILENCE_MS = 1100;
// nothing at all for this long: the mic is dead, denied, or the room is loud enough to
// swamp the gate. The surface falls back to a button rather than waiting forever.
export const NO_SPEECH_TIMEOUT_MS = 12000;

export function listenForSpeech(stream, { onSpeechStart, onSpeechEnd, onTimeout } = {}, opts = {}) {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return { stop: () => {} }; // no Web Audio: the caller keeps its button

  const ctx = new AudioCtx();
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);

  const buffer = new Float32Array(analyser.fftSize);
  const started = Date.now();
  let floor = null;
  let calibration = [];
  let speaking = false;
  let quietSince = null;
  let stopped = false;
  let raf = null;

  const endSilence = opts.endSilenceMs ?? END_SILENCE_MS;
  const timeout = opts.timeoutMs ?? NO_SPEECH_TIMEOUT_MS;

  function rms() {
    analyser.getFloatTimeDomainData(buffer);
    let sum = 0;
    for (let i = 0; i < buffer.length; i += 1) sum += buffer[i] * buffer[i];
    return Math.sqrt(sum / buffer.length);
  }

  function tick() {
    if (stopped) return;
    const level = rms();
    const elapsed = Date.now() - started;

    if (elapsed < CALIBRATION_MS) {
      calibration.push(level);
      raf = requestAnimationFrame(tick);
      return;
    }
    if (floor === null) {
      const avg = calibration.reduce((a, b) => a + b, 0) / (calibration.length || 1);
      // a silent room measures ~0; the epsilon stops the threshold collapsing to zero and
      // treating the microphone's own noise as speech
      floor = Math.max(avg, 0.005);
      calibration = [];
    }

    const loud = level > floor * SPEECH_FACTOR;
    if (loud) {
      quietSince = null;
      if (!speaking) {
        speaking = true;
        onSpeechStart?.();
      }
    } else if (speaking) {
      quietSince ??= Date.now();
      if (Date.now() - quietSince >= endSilence) {
        stop();
        onSpeechEnd?.();
        return;
      }
    } else if (elapsed > timeout) {
      stop();
      onTimeout?.();
      return;
    }
    raf = requestAnimationFrame(tick);
  }

  function stop() {
    if (stopped) return;
    stopped = true;
    if (raf) cancelAnimationFrame(raf);
    try {
      source.disconnect();
      ctx.close();
    } catch {
      // the context may already be closing; nothing here is worth failing a turn over
    }
  }

  raf = requestAnimationFrame(tick);
  return { stop };
}
