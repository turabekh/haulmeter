// AI-CONTEXT: one dock, one figure, one format — on every surface that answers the
// question (§23 R3).
//
// The load-confirm step and the facility page were describing the same dock two different
// ways: a raw pair from `/intel/pre-acceptance`, where the server applies the sample
// floor, and `Math.round(exceed_rate * 100)%` from `/intel/detention-risk` with a second
// `MIN_RATE_SAMPLE` in JS. A driver who opened a dock's page and then met the same dock
// on the load they were about to accept read two different numbers about it.
//
// The convergence is STRUCTURAL — both surfaces render `DwellIntel` — so this file is a
// backstop rather than the guarantee. A test that only compared rendered strings would go
// green again the moment someone re-inlined the markup with a "temporary" tweak; asserting
// the component is what makes the drift impossible rather than merely noticed.
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import DwellIntel from "../src/core/components/DwellIntel.vue";
import en from "../src/core/i18n/en.json";

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..", "src");
const SURFACES = [
  "surfaces/FacilityProfileSurface.vue",
  "core/components/RateConImportSheet.vue",
];

// what the server sends for one real dock, once
const INTEL = {
  risk: { exceeded: 9, sample_size: 21, free_time_minutes: 120 },
  best_hour: { hour: 6, median_seconds: 4200, sample_size: 8 },
  min_sample: 5,
};

describe("the raw pair renders identically wherever it appears", () => {
  it("is the same component on both surfaces, and neither owns a copy", () => {
    // the structural guarantee, checked against the SOURCE. Re-inlining the markup on
    // either surface fails here — two copies is exactly how they drifted the first time,
    // and a test comparing only rendered strings would go green again the moment someone
    // pasted the markup back with a "temporary" tweak.
    for (const file of SURFACES) {
      const src = readFileSync(resolve(SRC, file), "utf8");
      expect(src, `${file} must render the shared component`).toContain("<DwellIntel");
      expect(src, `${file} must not re-inline the pair`).not.toMatch(/exceeded\s*}}\s*\//);
      // a DECLARATION, not a mention — the comment recording why the floor moved is
      // worth keeping, and a test that forbids naming the history would delete it
      expect(src, `${file} must not hold its own sample floor`).not.toMatch(
        /const\s+MIN_RATE_SAMPLE/,
      );
    }
  });

  it("states the pair, its threshold and its basis — and never a percentage", () => {
    const w = mount(DwellIntel, { props: { intel: INTEL } });

    const text = w.text();
    expect(text).toContain("9 / 21");
    expect(text).toContain("120"); // the free time the pair was counted against
    expect(text).toContain(en["profile.stops_basis"]);
    expect(text).not.toContain("%");
    // a fraction rendered as a percentage loses its own sample size — entry 153
    expect(text).not.toContain("43");
  });

  it("renders each half independently", () => {
    const risk_only = mount(DwellIntel, { props: { intel: { ...INTEL, best_hour: null } } });
    const hour_only = mount(DwellIntel, { props: { intel: { ...INTEL, risk: null } } });

    expect(risk_only.findAll(".intel")).toHaveLength(1);
    expect(hour_only.findAll(".intel")).toHaveLength(1);
    expect(risk_only.text()).toContain("9 / 21");
    expect(hour_only.text()).toContain("06:00");
  });

  it("renders nothing at all when the server withheld both", () => {
    // below the floor the server sends null and the surface says nothing. Not a greyed
    // figure, not a hedged one — there is deliberately nothing here to soften.
    const w = mount(DwellIntel, { props: { intel: { risk: null, best_hour: null, min_sample: 5 } } });

    expect(w.findAll(".intel")).toHaveLength(0);
    expect(w.text().trim()).toBe("");
  });

  it("survives an intel payload that never arrived", () => {
    // an offline or failed fetch leaves null; the component must not be the thing that
    // breaks the page around it
    expect(mount(DwellIntel, { props: { intel: null } }).text().trim()).toBe("");
  });

  it("holds no sample floor of its own", () => {
    // the floor is the server's, and a second copy is how a rule stops being one. Given a
    // figure under the floor, the component still renders it — deciding otherwise here
    // would be the second enforcement.
    const w = mount(DwellIntel, {
      props: { intel: { risk: { exceeded: 2, sample_size: 3, free_time_minutes: 120 }, best_hour: null } },
    });

    expect(w.text()).toContain("2 / 3");
  });
});
