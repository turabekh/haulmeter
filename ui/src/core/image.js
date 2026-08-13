/* AI-CONTEXT: the capture sites' one entry point for "make this uploadable", and it is
 * deliberately incapable of failing.
 *
 * Every branch here falls back to the ORIGINAL blob. A driver photographing a BOL at a
 * dock is the case this product exists for, and a browser without `OffscreenCanvas`, a
 * worker that will not spawn, or an image the decoder does not recognise must all end
 * with the capture being uploaded at full size — slowly, which is the old behaviour —
 * rather than with the capture being lost. Speed is the feature; the photograph is the
 * product.
 *
 * Three tiers, best first:
 *   1. a module Worker — decode, resize and re-encode entirely off the main thread
 *   2. the same code inline — still async, still avoids the base64 string, but the
 *      resize competes with rendering. happy-dom and older Safari land here
 *   3. the original blob, untouched
 *
 * The worker is created ONCE and reused. Spawning one per photo would pay the module
 * fetch and instantiation on every shot in a six-photo condition capture. */

import { downscale } from "./image-worker.js";

let _worker = null;
let _workerBroken = false;
let _seq = 0;
const _pending = new Map();

function getWorker() {
  if (_workerBroken) return null;
  if (_worker) return _worker;
  if (typeof Worker === "undefined") {
    _workerBroken = true;
    return null;
  }
  try {
    _worker = new Worker(new URL("./image-worker.js", import.meta.url), { type: "module" });
    _worker.onmessage = (event) => {
      const { id, blob } = event.data || {};
      const resolve = _pending.get(id);
      if (resolve) {
        _pending.delete(id);
        resolve(blob);
      }
    };
    // a worker that dies mid-flight must not leave a capture waiting forever: every
    // caller in flight is resolved with what it started with, and we stop trying.
    _worker.onerror = () => {
      _workerBroken = true;
      _worker = null;
      for (const [, resolve] of _pending) resolve(null);
      _pending.clear();
    };
    return _worker;
  } catch {
    _workerBroken = true;
    return null;
  }
}

function viaWorker(worker, blob, options) {
  return new Promise((resolve) => {
    const id = ++_seq;
    _pending.set(id, resolve);
    try {
      worker.postMessage({ id, blob, options });
    } catch {
      _pending.delete(id);
      resolve(null);
    }
  });
}

export async function prepareImage(file, options = {}) {
  if (!file) return file;
  // a PDF is not an image (§23 entry 77) and a rate con is often filed as one
  if (!String(file.type || "").startsWith("image/")) return file;

  const worker = getWorker();
  if (worker) {
    const out = await viaWorker(worker, file, options);
    if (out) return out;
  }
  try {
    return await downscale(file, options);
  } catch {
    return file;
  }
}

export function __resetImagePipelineForTests() {
  try {
    _worker?.terminate();
  } catch {
    /* nothing to terminate */
  }
  _worker = null;
  _workerBroken = false;
  _pending.clear();
}
