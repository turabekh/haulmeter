// AI-CONTEXT: the test that was missing, and the reason the old ones could not have
// caught this.
//
// `media_url` returns an API-RELATIVE path: `/media/evidence/<id>?…`. The surfaces put it
// straight into an `<img src>`, and a browser resolves a root-relative `src` against the
// DOCUMENT'S ORIGIN, not against whatever base the JSON came from. So the deployed app
// asked `haulmeter.online/media/…`, where Caddy's SPA `try_files` answered
// **HTTP 200 with index.html** — not a 404, a 200, `content-type: text/html` — which the
// browser then tried to decode as an image. Nothing threw, nothing logged, no error state
// rendered, and every contact sheet in the product was silently empty. Locally it failed
// identically because the page is 9008 and the API is 8008.
//
// WHY THE EXISTING TESTS WENT GREEN OVER IT. They asserted
// `img.attributes("src") === "/media/evidence/p1?…"` — a string comparison. A string has
// no origin, so no amount of string assertion can express "and the browser will fetch
// this from the API". These tests resolve it the way a browser does, with `new URL(src,
// pageOrigin)`, which is the only form of the question that has the defect in it.
//
// This is §23 entry 92 ("whose localhost?") arriving from a third direction: a URL that
// is correct in the process that MINTS it and wrong in the process that FETCHES it.
import { describe, it, expect } from "vitest";
import { mediaUrl, API_BASE } from "../src/core/api.js";

const THUMB = "/media/evidence/2f6c-1?size=thumb&exp=99&sig=abc";

describe("an image URL is fetched from the API, not from the page", () => {
  it("does not leave an API path to be resolved against the page origin", () => {
    // the defect, stated as the browser experiences it
    const naive = new URL(THUMB, "https://haulmeter.online/load/l-1/record");
    expect(naive.href).toBe("https://haulmeter.online/media/evidence/2f6c-1?size=thumb&exp=99&sig=abc");
    expect(naive.pathname.startsWith("/api/")).toBe(false);
  });

  it("carries the API base, in whichever shape the environment uses", () => {
    // AI-CONTEXT: asserted against `API_BASE` rather than against a hardcoded origin,
    // because the two deployments differ in KIND and both must work. In dev it is an
    // absolute `http://localhost:8008`, so the image is fetched from another origin
    // entirely; in a deployment it is the root-relative `/api`, same origin, and Caddy
    // strips the prefix before the router sees `/media/…`. Pinning either one here would
    // make this test pass in one environment and lie about the other, which is the exact
    // shape of the bug it exists to catch.
    const page = "https://haulmeter.online/load/l-1/record";
    const resolved = new URL(mediaUrl(THUMB), page);

    expect(resolved.href).toBe(new URL(`${API_BASE}${THUMB}`, page).href);
    expect(resolved.pathname.endsWith("/media/evidence/2f6c-1")).toBe(true);
    // the signature has to survive the prefixing intact or every image 403s
    expect(resolved.searchParams.get("sig")).toBe("abc");
    expect(resolved.searchParams.get("size")).toBe("thumb");
  });

  it("sends the request somewhere other than the page itself", () => {
    // the one-line statement of the bug: the image must not be fetched from the SPA
    const page = "https://haulmeter.online/load/l-1/record";
    const resolved = new URL(mediaUrl(THUMB), page);
    const naive = new URL(THUMB, page);

    expect(resolved.href).not.toBe(naive.href);
  });

  it("leaves an absolute URL alone", () => {
    // a presigned object-store URL, if this ever terminates at MinIO instead
    const absolute = "https://cdn.example/img.jpg?sig=x";
    expect(mediaUrl(absolute)).toBe(absolute);
  });

  it("returns null for nothing, so `v-if` still hides the element", () => {
    expect(mediaUrl(null)).toBeNull();
    expect(mediaUrl("")).toBeNull();
  });
});
