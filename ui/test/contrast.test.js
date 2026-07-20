// AI-CONTEXT: design-prd §16 — contrast verified in BOTH themes in CI. Parses the
// authoritative tokens.scss (dark from the $ SCSS vars, light from the
// @mixin longhaul-light block) and asserts WCAG ratios: critical text (text-1)
// ≥7:1 (AAA), secondary text (text-2) ≥4.5:1, muted (text-3) ≥3:1, the
// interactive accent (shield) ≥3:1 as a UI element. If a token edit regresses
// contrast in either theme, this fails like a red test.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it, expect } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const scss = readFileSync(join(here, "../src/core/tokens.scss"), "utf8");

function darkVar(name) {
  const m = scss.match(new RegExp(`\\$${name}:\\s*(#[0-9A-Fa-f]{6})`));
  return m && m[1];
}

const lightBlock = scss.slice(
  scss.indexOf("@mixin longhaul-light"),
  scss.indexOf("}", scss.indexOf("@mixin longhaul-light")),
);
function lightVar(name) {
  const m = lightBlock.match(new RegExp(`--${name}:\\s*(#[0-9A-Fa-f]{6})`));
  return m && m[1];
}

function luminance(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const f = (x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4);
  const [r, g, b] = c.map(f);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

const THEMES = {
  dark: {
    ink: ["ink-0", "ink-1", "ink-2"].map(darkVar),
    text1: darkVar("text-1"),
    text2: darkVar("text-2"),
    text3: darkVar("text-3"),
    shield: darkVar("shield-500"),
  },
  light: {
    ink: ["ink-0", "ink-1", "ink-2"].map(lightVar),
    text1: lightVar("text-1"),
    text2: lightVar("text-2"),
    text3: lightVar("text-3"),
    shield: lightVar("shield-500"),
  },
};

describe("token contrast (design-prd §16, both themes)", () => {
  for (const [theme, p] of Object.entries(THEMES)) {
    it(`${theme}: all color tokens parsed`, () => {
      expect(p.ink.every(Boolean)).toBe(true);
      expect(p.text1 && p.text2 && p.text3 && p.shield).toBeTruthy();
    });

    for (const [i, bg] of ["ink-0", "ink-1", "ink-2"].entries()) {
      it(`${theme}: text-1 ≥7:1 on ${bg} (AAA critical)`, () => {
        expect(ratio(p.text1, p.ink[i])).toBeGreaterThanOrEqual(7);
      });
      it(`${theme}: text-2 ≥4.5:1 on ${bg}`, () => {
        expect(ratio(p.text2, p.ink[i])).toBeGreaterThanOrEqual(4.5);
      });
      it(`${theme}: text-3 ≥3:1 on ${bg} (muted)`, () => {
        expect(ratio(p.text3, p.ink[i])).toBeGreaterThanOrEqual(3);
      });
    }

    it(`${theme}: interactive accent shield ≥3:1 on ink-0`, () => {
      expect(ratio(p.shield, p.ink[0])).toBeGreaterThanOrEqual(3);
    });
  }
});
