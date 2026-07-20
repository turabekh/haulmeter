// AI-CONTEXT: design-prd §12.5 — layout is designed at +40% length via the
// `xx-XL` pseudo-locale in CI. This stub verifies the pseudo catalog is
// generated for every EN key and inflates length ~+40% while leaving ICU
// {placeholders} intact. Wired to real screen-overflow assertions as surfaces
// land; for now it guarantees the generator itself is sound.
import { describe, it, expect } from "vitest";
import { messages } from "../src/core/i18n/index.js";
import { buildPseudoCatalog, pseudoInflate } from "../src/core/i18n/pseudo.js";

describe("pseudo-locale xx-XL (design-prd §12.5)", () => {
  const pseudo = buildPseudoCatalog(messages.en);

  it("covers every EN key", () => {
    expect(Object.keys(pseudo).sort()).toEqual(Object.keys(messages.en).sort());
  });

  it("inflates visible length by at least +40%", () => {
    for (const [key, value] of Object.entries(messages.en)) {
      const inflated = pseudo[key];
      expect(inflated.length, `${key} not inflated`).toBeGreaterThanOrEqual(
        Math.ceil(value.length * 1.4),
      );
    }
  });

  it("preserves ICU placeholders untouched", () => {
    const src = "Detention started · {rate}/h — {action}";
    const out = pseudoInflate(src);
    expect(out).toContain("{rate}");
    expect(out).toContain("{action}");
  });
});
