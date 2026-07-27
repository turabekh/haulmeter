// AI-CONTEXT: §6.2 typography — the claims the constitution makes about itself.
//
// These exist because two of those claims were untrue for the whole life of the
// project, and nothing in CI noticed:
//
// · §6.2 says the faces are "loaded as self-hosted variable fonts". Until the
//   evidence-pack work they were NAMED with a system fallback and no font file
//   shipped, so the app rendered in whatever the device had. The @font-face rules
//   now exist and these tests hold them there.
// · T-2 requires money and time to be Mono AND TABULAR with "zero layout shift
//   while counting". The CSS was always right; the guarantee was carried by the
//   fallback stack happening to be monospace, which is luck, not a spec. With Plex
//   Mono actually loading it holds by design — and now by test.
//
// What these deliberately do NOT claim to cover: xx-XL clipping. vitest runs in
// jsdom, which has no layout engine — getBoundingClientRect returns zeros — so no
// overflow assertion written here could ever fail. `pseudo-locale.test.js` says as
// much in its own docstring. That DoD line has never been mechanically enforced and
// this file does not pretend otherwise.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const tokens = readFileSync(resolve(here, "../src/core/tokens.scss"), "utf8");
const meter = readFileSync(resolve(here, "../src/core/components/TheMeter.vue"), "utf8");

// the five faces the §6.2 scale actually uses: Sans 400/500/600, Mono 400/600
const FACES = [
  ["IBM Plex Sans", "IBMPlexSans-Regular.woff2", 400],
  ["IBM Plex Sans", "IBMPlexSans-Medium.woff2", 500],
  ["IBM Plex Sans", "IBMPlexSans-SemiBold.woff2", 600],
  ["IBM Plex Mono", "IBMPlexMono-Regular.woff2", 400],
  ["IBM Plex Mono", "IBMPlexMono-SemiBold.woff2", 600],
];

describe("§6.2 — the faces are shipped, not merely named", () => {
  it("declares an @font-face for every weight the type scale uses", () => {
    for (const [family, file, weight] of FACES) {
      const block = tokens
        .split("@font-face")
        .find((b) => b.includes(file));
      expect(block, `no @font-face for ${file}`).toBeTruthy();
      expect(block).toContain(family);
      expect(block).toMatch(new RegExp(`font-weight:\\s*${weight}`));
    }
  });

  it("ships the font files the @font-face rules point at", async () => {
    const { existsSync } = await import("node:fs");
    for (const [, file] of FACES) {
      expect(existsSync(resolve(here, "../public/fonts", file)), `${file} missing`).toBe(true);
    }
  });

  it("carries the OFL licence beside them", async () => {
    const { existsSync } = await import("node:fs");
    expect(existsSync(resolve(here, "../public/fonts/LICENSE.txt"))).toBe(true);
  });

  it("names no family outside the two the constitution permits", () => {
    // §6.2: "no other families, ever". Gurmukhi is the one declared exception and
    // is NOT yet real — see the §23 correction; it is declared and never applied.
    const families = [...tokens.matchAll(/font-family:\s*([^;]+);/g)].map((m) => m[1]);
    for (const family of families) {
      expect(family).toMatch(/Plex|font-sans|font-mono|font-gurmukhi|Gurmukhi/);
    }
  });
});

describe("§6.2 T-2 — The Meter's figures are tabular", () => {
  it("sets Mono and tabular-nums on the figure, in tokens not literals", () => {
    const block = meter.slice(meter.indexOf(".meter__figure"));
    expect(block).toContain("font-family: var(--font-mono)");
    // the property that actually delivers "zero layout shift while counting"
    expect(block).toContain("font-variant-numeric: tabular-nums");
    // AI-CONTEXT: the figure is `min(--type-meter-size, --type-meter-fluid-max)` since
    // §23 entry 63. T-6 forbids truncating money and asks for scaling down instead, and
    // at 200% text the meter step outgrows a 360 dp card — the ceiling is what keeps the
    // hero figure inside it. BOTH operands are tokens, which is what this test is for.
    expect(block).toContain("var(--type-meter-size)");
    expect(block).toContain("var(--type-meter-fluid-max)");
    expect(block).not.toMatch(/font-size:\s*[^;]*\d+(px|rem|vw)/); // no literal, only tokens
  });

  it("uses no hardcoded size or family anywhere in the signature element", () => {
    expect(meter).not.toMatch(/font-family:\s*["']?(Helvetica|Arial|monospace)/);
    expect(meter).not.toMatch(/font-size:\s*\d+px/);
  });
});
