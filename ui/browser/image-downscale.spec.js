// AI-CONTEXT: the downscale, measured in a REAL browser, because nothing else can see it.
//
// `prepareImage` falls back to the original blob on every failure — a browser with no
// `OffscreenCanvas`, a worker that will not spawn, an image the decoder rejects. That is
// the right behaviour (a driver's photograph must reach the server even slowly) and it is
// also perfectly silent: happy-dom implements neither `OffscreenCanvas` nor
// `createImageBitmap`, so every unit test in `image-queue.test.js` exercised the
// PASSTHROUGH and would have gone green over a downscale that never once ran.
//
// This is the §23 entry 143 lesson applied to a second mechanism: the only check that can
// catch a PWA defect drives a real browser, because every other assertion about a
// manifest reads the manifest. The only check that can catch a downscale defect must
// actually decode and re-encode an image.
import { test, expect } from "@playwright/test";

// a 4000 × 3000 frame — the shape a phone camera actually produces, and 12 megapixels is
// the middle of the range for the mid-range Android LAW 0 designs for.
async function cameraFrame(page) {
  return page.evaluate(async () => {
    const canvas = document.createElement("canvas");
    canvas.width = 4000;
    canvas.height = 3000;
    const ctx = canvas.getContext("2d");
    // photographic noise rather than flat colour: a solid fill compresses to almost
    // nothing and would make any re-encode look like a triumph.
    const img = ctx.createImageData(4000, 3000);
    for (let i = 0; i < img.data.length; i += 4) {
      img.data[i] = (i * 7) % 256;
      img.data[i + 1] = (i * 13) % 256;
      img.data[i + 2] = (i * 29) % 256;
      img.data[i + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.95));
    return { size: blob.size, url: URL.createObjectURL(blob) };
  });
}

test("a camera frame is downscaled to 2048 px on the long edge, off the main thread", async ({
  page,
}) => {
  await page.goto("/map");

  const frame = await cameraFrame(page);
  expect(frame.size, "the fixture must be a realistically large photograph").toBeGreaterThan(
    1_000_000,
  );

  const result = await page.evaluate(async (url) => {
    const original = await (await fetch(url)).blob();
    const mod = await import("/src/core/image.js");
    const out = await mod.prepareImage(new File([original], "bol.jpg", { type: "image/jpeg" }));
    const bitmap = await createImageBitmap(out);
    return {
      before: original.size,
      after: out.size,
      width: bitmap.width,
      height: bitmap.height,
      type: out.type,
    };
  }, frame.url);

  // the geometry: the long edge is capped and the aspect ratio survives
  expect(result.width, "the long edge is capped at 2048").toBe(2048);
  expect(result.height, "and the aspect ratio is preserved").toBe(1536);
  expect(result.type).toBe("image/jpeg");

  // the point of the whole exercise. A 12 MP frame off a phone is several megabytes and
  // rode the wire as base64 at +33% on truck-stop LTE.
  expect(result.after, "the upload must be dramatically smaller").toBeLessThan(
    result.before / 4,
  );
});

test("a small scan and a PDF are passed through untouched", async ({ page }) => {
  await page.goto("/map");

  // AI-CONTEXT: asserted on the BYTES, not on object identity. The worker replies through
  // `postMessage`, which structured-clones — so a passed-through blob is necessarily a
  // different object with the same contents, and `===` would fail for a pipeline that is
  // behaving exactly as intended.
  const result = await page.evaluate(async () => {
    const mod = await import("/src/core/image.js");
    // compared byte by byte rather than hashed: `crypto.subtle` needs a secure context
    // and the dev server this runs against is plain http (§23 entry 92 is the same
    // constraint seen from the other side).
    const same = async (a, b) => {
      if (a.size !== b.size) return false;
      const [x, y] = [new Uint8Array(await a.arrayBuffer()), new Uint8Array(await b.arrayBuffer())];
      return x.every((v, i) => v === y[i]);
    };

    // below the floor: re-encoding a 40 KB scan costs quality and saves nothing
    const small = new File([new Uint8Array(40 * 1024).fill(3)], "scan.jpg", {
      type: "image/jpeg",
    });
    const smallOut = await mod.prepareImage(small);

    // a PDF is not an image (§23 entry 77) and a rate con is routinely filed as one
    const pdf = new File([new Uint8Array(900 * 1024).fill(9)], "ratecon.pdf", {
      type: "application/pdf",
    });
    const pdfOut = await mod.prepareImage(pdf);

    return {
      smallSame: await same(small, smallOut),
      pdfSame: await same(pdf, pdfOut),
      pdfType: pdfOut.type,
      smallType: smallOut.type,
    };
  });

  expect(result.smallSame, "a small image is returned byte-identical").toBe(true);
  expect(result.smallType).toBe("image/jpeg");
  expect(result.pdfSame, "a PDF is never decoded as an image").toBe(true);
  expect(result.pdfType).toBe("application/pdf");
});

// AI-CONTEXT: the check that would have caught the empty contact sheets.
//
// `media_url` returns an API-relative path and the surfaces put it in an `<img src>`. A
// browser resolves a root-relative src against the DOCUMENT'S origin, so the deployed app
// asked `haulmeter.online/media/…` — where Caddy's SPA `try_files` answered HTTP 200 with
// index.html, which the browser then tried to decode as an image. Nothing threw and
// nothing logged.
//
// Every unit test compared `src` to a STRING, and a string has no origin, so none of them
// could express the defect. This asks the only question that contains it: given the page
// the app is actually served from, where does the browser send the request?
test("an image src is fetched from the API, never from the page itself", async ({ page }) => {
  await page.goto("/map");

  const result = await page.evaluate(async () => {
    const { mediaUrl, API_BASE } = await import("/src/core/api.js");
    const path = "/media/evidence/abc?size=thumb&exp=1&sig=s";

    // resolved by the BROWSER, against the real document location
    const resolved = new URL(mediaUrl(path), location.href);
    const naive = new URL(path, location.href);
    return {
      resolvedHref: resolved.href,
      naiveHref: naive.href,
      pageOrigin: location.origin,
      apiBase: API_BASE,
      keepsSignature: resolved.searchParams.get("sig") === "s",
      reachesMedia: resolved.pathname.endsWith("/media/evidence/abc"),
    };
  });

  // the defect, in one line: the app must not ask its own SPA for a photograph
  expect(result.resolvedHref).not.toBe(result.naiveHref);
  expect(result.keepsSignature, "the signature must survive prefixing or every image 403s").toBe(
    true,
  );
  expect(result.reachesMedia).toBe(true);
  // dev serves the API on another origin; a deployment uses /api on the same one
  const sameOrigin = result.resolvedHref.startsWith(result.pageOrigin);
  expect(sameOrigin ? new URL(result.resolvedHref).pathname : result.resolvedHref).toContain(
    result.apiBase.replace(/^https?:\/\/[^/]+/, "") || "8008",
  );
});
