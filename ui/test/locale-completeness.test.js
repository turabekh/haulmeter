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

// AI-CONTEXT: parity above proves the six catalogues AGREE. It cannot prove they are
// RIGHT, and that gap shipped a defect: `load.doc.cargo_condition` is a capture-checklist
// row for every stop type and had a label in none of the six, so drivers read the raw key
// on the Load tab. Six identical holes look complete to a test that only compares
// catalogues to each other — the same shape as a label asserted against the table it
// rendered from, which the handoffs keep finding.
//
// This half checks the catalogue against the keys the APP ASKS FOR. Static `t("literal")`
// calls are checked exhaustively here; the ~45 dynamic `t(`ns.${...}`)` families cannot be
// resolved statically (their vocabularies live in Python), so those are caught at render
// time instead — `t()` throws on an unknown key under test, see core/i18n.js.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..", "src");

function sourceFiles(dir) {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(vue|js)$/.test(entry) ? [path] : [];
  });
}

function staticKeys() {
  const found = new Map();
  for (const file of sourceFiles(SRC)) {
    const text = readFileSync(file, "utf8");
    // t("a.b") / t('a.b') — a dotted key, which is what every message key looks like.
    // Deliberately narrow: a false positive here would fail CI over a call that is not
    // a translation at all.
    for (const m of text.matchAll(/\bt\(\s*["']([a-z][\w]*(?:\.[\w]+)+)["']/g)) {
      if (!found.has(m[1])) found.set(m[1], file.replace(SRC, "src"));
    }
  }
  return found;
}

describe("the catalogue answers what the app asks (design-prd §12.5)", () => {
  it("finds the static keys at all (the scan itself must not silently match nothing)", () => {
    expect(staticKeys().size).toBeGreaterThan(300);
  });

  it("has every statically-referenced key in EN", () => {
    const missing = [...staticKeys()]
      .filter(([key]) => !Object.hasOwn(messages.en, key))
      .map(([key, file]) => `${key} (${file})`);
    expect(missing, `keys the app renders that no catalogue has:\n${missing.join("\n")}`)
      .toEqual([]);
  });
});
