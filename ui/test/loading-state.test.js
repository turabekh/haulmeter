// AI-CONTEXT: §23 entry 131 — the loading state, and the end of the fixtures.
//
// This file is the burn-down for UI audit U-06, U-09, U-10, U-11 and U-12. All five are
// one defect: with no `loading` state a surface must render either data or no-data the
// instant it mounts, so `null` had to mean one of the two and this codebase chose DATA.
// `livePins.value ?? SAMPLE_PINS` put fabricated truck stops on every cold app open;
// five other surfaces did the same on failure, including a CDL that is not the driver's.
//
// Why the assertion is at the SOURCE and not on a rendered screen: §23 entry 81 removed
// one fixture on the argument that "an exported placeholder is one import away from
// being back on the screen a driver cannot verify", and this file is that argument
// applied to the other sixteen. `SAMPLE_FUEL_ANALYTICS` was the proof it needed — it was
// exported and imported by NOTHING, a fixture already halfway back to a screen.
//
// The burn-down was written and watched FAILING before any of it was true. A guard
// nobody has seen fail is the same species as the harness that could not fail
// (§23 entry 1197).
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { resolve, join } from "node:path";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import * as fixtures from "../src/core/fixtures.js";
import SkeletonCard from "../src/core/components/SkeletonCard.vue";
import SkeletonRow from "../src/core/components/SkeletonRow.vue";
import SkeletonPin from "../src/core/components/SkeletonPin.vue";
import { SKELETON_DELAY_MS } from "../src/core/skeleton.js";
import { DriverState, useDriverState, __resetStateForTests } from "../src/core/state.js";
import MapSurface from "../src/surfaces/MapSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const mapRouter = () => createRouter({ history: createMemoryHistory(), routes });

const root = resolve(__dirname, "..");
const read = (p) => readFileSync(resolve(root, p), "utf8");

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(vue|js)$/.test(name)) out.push(p);
  }
  return out;
}

describe("§23 entry 131 — the fixtures are gone", () => {
  it("exports no fixture of any kind", () => {
    // by NAME at the source, because the next person needing placeholder data will
    // reach for this same drawer. The proposal's open question was answered "no
    // fixtures for /dev", which is what keeps this a name assertion rather than a
    // path-based one.
    expect(read("src/core/fixtures.js")).not.toMatch(
      /^export\s+(const|function|let|var|class)\s+(SAMPLE_|sample[A-Z])/m,
    );
  });

  it("exports nothing at all — the module surface is empty", () => {
    // stronger than the name check and the reason is the orphan: SAMPLE_FUEL_ANALYTICS
    // was exported and imported by nothing, so a rename would have satisfied a
    // name-shaped assertion while leaving the drawer full.
    const exported = Object.keys(fixtures).filter((k) => k !== "default");
    expect(exported).toEqual([]);
  });

  it("is imported by no file in the app — portals included", () => {
    // the §18 portals go too (entry 131). Their fixtures are not a driver reading a
    // CDL that is not theirs, but "one import away" is a fact about the drawer, not
    // about which screen happens to open it today.
    const offenders = walk(resolve(root, "src"))
      .filter((p) => !p.endsWith(join("core", "fixtures.js")))
      .filter((p) => /from\s+["'][^"']*core\/fixtures\.js["']|from\s+["']\.\.?\/fixtures\.js["']/.test(readFileSync(p, "utf8")))
      .map((p) => p.slice(root.length + 1));
    expect(offenders).toEqual([]);
  });
});

const SHAPES = [
  ["SkeletonCard", SkeletonCard, ".skel__card"],
  ["SkeletonRow", SkeletonRow, ".skel__row"],
  ["SkeletonPin", SkeletonPin, ".skel__pin"],
];

describe("the skeleton primitive — three shapes, one gate", () => {
  beforeEach(() => {
    __resetStateForTests();
    vi.useFakeTimers();
  });

  for (const [name, Shape, unit] of SHAPES) {
    it(`${name} renders nothing until the delay has passed`, async () => {
      // a skeleton that flashes is worse than a brief blank: a fast local response
      // must never show one. The blank is the CORRECT render before 200 ms, not a bug.
      const w = mount(Shape);
      expect(w.findAll(unit)).toHaveLength(0);
      vi.advanceTimersByTime(SKELETON_DELAY_MS);
      await w.vm.$nextTick();
      expect(w.findAll(unit).length).toBeGreaterThan(0);
    });

    it(`${name} renders nothing at all while DRIVING`, async () => {
      // SM-3: at speed the surface withdraws and says so with `driving.paused`. A
      // skeleton is a promise content is coming, which is a reason to keep looking.
      useDriverState().setState(DriverState.DRIVING);
      const w = mount(Shape);
      vi.advanceTimersByTime(SKELETON_DELAY_MS * 5);
      await w.vm.$nextTick();
      expect(w.findAll(unit)).toHaveLength(0);
    });

    it(`${name} renders the count it is asked for, not a fixed three`, async () => {
      const w = mount(Shape, { props: { count: 5 } });
      vi.advanceTimersByTime(SKELETON_DELAY_MS);
      await w.vm.$nextTick();
      expect(w.findAll(unit)).toHaveLength(5);
    });

    it(`${name} says nothing to a screen reader and carries no text`, async () => {
      // aria-hidden is deliberate: "rectangle, rectangle" is noise, not access. It
      // also keeps the layout harness's type-floor check honest — that check skips
      // text-free elements, and a skeleton has no business carrying copy.
      const w = mount(Shape, { props: { count: 2 } });
      vi.advanceTimersByTime(SKELETON_DELAY_MS);
      await w.vm.$nextTick();
      expect(w.find("[aria-hidden='true']").exists()).toBe(true);
      expect(w.text()).toBe("");
    });
  }
});

describe("§6.4 — the skeleton does not animate, and cannot start", () => {
  // the industry default is a looping shimmer, forbidden TWICE over: as looping
  // ambient motion, and because it would compete with The Meter for the one living
  // element on a screen. This is asserted at the source rather than trusted, because
  // "add a subtle shimmer" is the single most likely edit anyone will make here.
  for (const [name] of SHAPES) {
    it(`${name} declares no animation, no keyframes, no transition`, () => {
      const src = read(`src/core/components/${name}.vue`);
      expect(src).not.toMatch(/@keyframes/);
      expect(src).not.toMatch(/\banimation(-[a-z]+)?\s*:/);
      expect(src).not.toMatch(/\btransition(-[a-z]+)?\s*:/);
    });
  }

  it("needs no prefers-reduced-motion branch, because there is no motion", () => {
    for (const [name] of SHAPES) {
      expect(read(`src/core/components/${name}.vue`)).not.toMatch(/prefers-reduced-motion/);
    }
  });
});

describe("SkeletonPin's fill is legible over a basemap, in both themes", () => {
  // AI-CONTEXT: this guards a defect that reached a screenshot (§23 entry 131).
  //
  // SkeletonPin first filled with `--line-1`, matching the other two shapes. On a CARD
  // that is correct. On a MAP it is invisible: dark `--line-1` is #2A3644 against a
  // night basemap of about the same value, so six pucks rendered, `visibility: visible`,
  // counted by the layout harness — and a human looking at the screen saw an empty map.
  // Every automated check passed. It was found by throttling the network and looking.
  //
  // So the assertion is on the TOKEN CHOICE, which is the thing that was wrong, and it
  // names its reason: `--on-accent` is theme-invariant white, and §23 entry 130 recorded
  // that invariance as load-bearing for pins specifically. An ink or line token here is
  // the bug returning.
  it("fills with the theme-invariant white, never an ink or line step", () => {
    const src = read("src/core/components/SkeletonPin.vue");
    const fill = src.match(/\.skel__puck\s*\{[^}]*background:\s*var\((--[a-z0-9-]+)\)/);
    expect(fill, "SkeletonPin must declare a background on .skel__puck").toBeTruthy();
    expect(fill[1]).toBe("--on-accent");
  });

  it("keeps that fill identical in both themes, which is why it works on either basemap", () => {
    // if a later session gives `--on-accent` a different light-theme value, the
    // night/day basemap argument above quietly stops holding. tokens.scss declares it
    // TWICE — once in the dark root and once in the light mixin — with the same value,
    // so the check is that the values AGREE, not that the second declaration is absent.
    // The first version of this test asserted absence and failed correctly.
    const tokens = read("src/core/tokens.scss");
    const declared = [...tokens.matchAll(/--on-accent:\s*([^;]+);/g)].map((m) => m[1].trim());
    expect(declared.length).toBeGreaterThan(1); // both themes name it
    expect(new Set(declared).size).toBe(1); // and they name the same colour
  });

  it("carries no status colour — a loading pin asserts no availability (§11.1)", () => {
    const src = read("src/core/components/SkeletonPin.vue");
    for (const status of ["--marker-500", "--ledger-500", "--alert-500", "--pin-color"]) {
      expect(src).not.toContain(status);
    }
  });
});

describe("the skeleton adds nothing to the token system", () => {
  it("references only custom properties tokens.scss already defines", () => {
    // §22.2: a new token is a never-improvise category. This is the mechanical half of
    // that promise — token-discipline.test.js catches colour LITERALS, and this catches
    // the other way to invent a value: referencing a `--name` nothing defines, which
    // renders as nothing and fails silently.
    const tokens = read("src/core/tokens.scss");
    const defined = new Set([...tokens.matchAll(/^\s*(--[a-z0-9-]+):/gm)].map((m) => m[1]));
    const used = new Set();
    for (const [name] of SHAPES) {
      for (const m of read(`src/core/components/${name}.vue`).matchAll(/var\((--[a-z0-9-]+)/g)) {
        used.add(m[1]);
      }
    }
    expect([...used].filter((v) => !defined.has(v))).toEqual([]);
    expect(used.size).toBeGreaterThan(0); // the assertion must have something to check
  });
});

// AI-CONTEXT: the map's four states, tested by MOUNTING the surface rather than by
// grepping it. `corridor.test.js` asserts on source for its half, and source
// assertions are the right tool for "the fixture cannot come back" — but they cannot
// tell you the states actually render, and the whole finding here was a state nobody
// had ever seen. So this drives the real component with a stubbed transport.
describe("U-10 — the map declares four states and invents no facility", () => {
  const PIN = {
    facility_id: "f-1",
    name: "Love's Travel Stop #212",
    facility_type: "truck_stop",
    lat: 32.78,
    lon: -96.8,
    status: null,
    badges: [],
    freshness: null,
  };

  let realFetch;
  beforeEach(() => {
    __resetStateForTests();
    realFetch = globalThis.fetch;
    setToken("test-token");
  });
  afterEach(() => {
    globalThis.fetch = realFetch;
    logout();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function stubOverlay(handler) {
    vi.stubGlobal(
      "fetch",
      vi.fn((url) => {
        if (String(url).includes("/map/overlay")) return handler();
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }),
    );
  }

  function map() {
    return mount(MapSurface, { global: { plugins: [mapRouter()] } });
  }

  it("renders skeleton pucks and NOT a fabricated facility while the overlay is in flight", async () => {
    // this is the defect: `livePins ?? SAMPLE_PINS` put real-looking truck stops here
    // on every cold open, and a driver could route to one.
    stubOverlay(() => new Promise(() => {})); // never resolves — the cold-start window
    const w = map();
    await flushPromises();
    vi.useFakeTimers();
    vi.advanceTimersByTime(SKELETON_DELAY_MS);
    vi.useRealTimers();
    await flushPromises();

    expect(w.findAll(".skel__pin").length).toBeGreaterThan(0);
    expect(w.findAll(".pin")).toHaveLength(0);
    expect(w.text()).not.toContain("Love's");
  });

  it("renders the pins once they arrive, and drops the skeleton", async () => {
    stubOverlay(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ pins: [PIN], clusters: [] }) }));
    const w = map();
    await flushPromises();
    expect(w.findAll(".pin").length).toBeGreaterThan(0);
    expect(w.findAll(".skel__pin")).toHaveLength(0);
  });

  it("says it could not load, with a retry, when the server refuses — and shows no pins", async () => {
    stubOverlay(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }));
    const w = map();
    await flushPromises();

    expect(w.find(".map__failed").exists()).toBe(true);
    expect(w.text()).toContain(en["map.load_failed"]);
    expect(w.find(".map__retry").exists()).toBe(true);
    expect(w.findAll(".pin")).toHaveLength(0);
  });

  it("tells a driver in a dead zone to check signal, not that the server broke", async () => {
    // §15.1: offline is a MODE. The two sentences send a driver to different fixes, and
    // `fetchOverlay` bypasses apiGet — so this is the case a single-signal classifier
    // would have got wrong (see load-state.js).
    stubOverlay(() => Promise.reject(new TypeError("Failed to fetch")));
    const w = map();
    await flushPromises();

    expect(w.text()).toContain(en["system.load_offline"]);
    expect(w.text()).not.toContain(en["map.load_failed"]);
  });

  it("keeps the pins it has when a pan supersedes an in-flight fetch", async () => {
    // THE TRAP. Every pan aborts the previous overlay request. If an abort were treated
    // as a failure the map would flash its error banner on every drag, and if it were
    // treated as `loading` it would flash skeleton pucks over live pins.
    let call = 0;
    stubOverlay(() => {
      call += 1;
      if (call === 1) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ pins: [PIN], clusters: [] }) });
      }
      const abort = new Error("aborted");
      abort.name = "AbortError";
      return Promise.reject(abort);
    });

    const w = map();
    await flushPromises();
    expect(w.findAll(".pin").length).toBeGreaterThan(0);

    w.vm.loadOverlay({ min_lat: 1, min_lon: 2, max_lat: 3, max_lon: 4 });
    await flushPromises();

    expect(w.findAll(".pin").length).toBeGreaterThan(0); // pins survived
    expect(w.find(".map__failed").exists()).toBe(false); // no error banner
    expect(w.findAll(".skel__pin")).toHaveLength(0); // and no skeleton
  });
});
