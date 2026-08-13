/* AI-CONTEXT: the downscale, in a Worker, because the main thread is where the lag was.
 *
 * A modern phone camera writes 3–8 MB per frame. Every upload path in this product read
 * that with a `FileReader` on the MAIN THREAD, base64'd it (+33%) and handed the string
 * to `JSON.stringify` — so the UI froze for the whole of it, on the screen where a driver
 * is standing at a dock trying to photograph a BOL.
 *
 * `createImageBitmap` + `OffscreenCanvas` both exist in a worker and neither touches the
 * DOM, so the decode, the resize and the re-encode all happen off the thread that draws.
 *
 * 2048 px on the long edge at q0.85 is the owner's decision, and the reason it is not
 * smaller is legibility rather than fidelity: these images are EVIDENCE. A BOL goes to a
 * broker to support a detention claim and a CDL is produced to a DOT officer, so the
 * floor is "the text is still readable", not "it still looks like a photograph". A 2048 px
 * long edge holds ~10 px of glyph height for body text on a US Letter page photographed
 * to fill the frame, which survives the re-encode.
 *
 * It never UPSCALES and it never re-encodes something already small — a 200 KB scan that
 * came off a flatbed would only get worse by being decoded and re-compressed. */

const MAX_EDGE = 2048;
const QUALITY = 0.85;

// below this, a re-encode costs quality and saves nothing worth having
const FLOOR_BYTES = 512 * 1024;

export async function downscale(blob, { maxEdge = MAX_EDGE, quality = QUALITY } = {}) {
  if (!blob || !String(blob.type || "").startsWith("image/")) return blob;
  if (blob.size <= FLOOR_BYTES) return blob;

  let bitmap;
  try {
    bitmap = await createImageBitmap(blob);
  } catch {
    return blob; // an image this browser cannot decode still deserves to be uploaded
  }

  const { width, height } = bitmap;
  const longest = Math.max(width, height);
  if (!longest) {
    bitmap.close?.();
    return blob;
  }

  const scale = Math.min(1, maxEdge / longest);
  const w = Math.max(1, Math.round(width * scale));
  const h = Math.max(1, Math.round(height * scale));

  try {
    const canvas = new OffscreenCanvas(w, h);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(bitmap, 0, 0, w, h);
    // JPEG regardless of what came in: these are photographs of paper, and a PNG
    // screenshot of a rate con re-encodes to a fraction of its size with no loss a
    // reader would see. The server records the content type it is given.
    const out = await canvas.convertToBlob({ type: "image/jpeg", quality });
    // a re-encode that made it BIGGER is a re-encode worth discarding
    return out && out.size < blob.size ? out : blob;
  } catch {
    return blob;
  } finally {
    bitmap.close?.();
  }
}

// the worker entry. Guarded so this module can also be imported directly on the main
// thread, which is the fallback when `Worker` or module workers are unavailable.
if (typeof self !== "undefined" && typeof self.postMessage === "function" && !self.document) {
  self.onmessage = async (event) => {
    const { id, blob, options } = event.data || {};
    try {
      const result = await downscale(blob, options || {});
      self.postMessage({ id, blob: result });
    } catch {
      self.postMessage({ id, blob });
    }
  };
}
