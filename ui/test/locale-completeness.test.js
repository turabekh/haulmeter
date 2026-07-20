// AI-CONTEXT: design-prd §12.5 — "the six locales ship together; a string
// without all six translations fails CI." This stub enforces key-set parity
// across all launch locales against EN as the source of truth. Grows
// automatically as strings are added to en.json.
import { describe, it, expect } from "vitest";
import { messages, LAUNCH_LOCALES } from "../src/core/i18n/index.js";

const enKeys = Object.keys(messages.en).sort();

describe("locale completeness (design-prd §12.5)", () => {
  it("registers exactly the six launch locales", () => {
    expect(Object.keys(messages).sort()).toEqual([...LAUNCH_LOCALES].sort());
  });

  for (const locale of LAUNCH_LOCALES) {
    it(`${locale} has every EN key with a non-empty value`, () => {
      const catalog = messages[locale];
      expect(catalog, `${locale} catalog missing`).toBeDefined();
      expect(Object.keys(catalog).sort()).toEqual(enKeys);
      for (const key of enKeys) {
        expect(
          typeof catalog[key] === "string" && catalog[key].trim().length > 0,
          `${locale}:${key} is empty or missing`,
        ).toBe(true);
      }
    });
  }
});
