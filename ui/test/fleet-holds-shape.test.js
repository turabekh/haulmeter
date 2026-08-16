/**
 * AI-CONTEXT: the render error the suite could not see (TRAPS §2 entry 16, §15).
 *
 * `make ci` exited 1 for several sessions while every one of 1020 assertions passed. The
 * cause was a TypeError thrown inside `FleetWorkspaceSurface`'s render — `holds.holds` was
 * undefined and `.length` threw — surfacing only as a vitest "unhandled rejection" that no
 * assertion in the project could observe. A permanently-red gate with a green suite is
 * worse than either alone: it trains everyone to read the red as noise.
 *
 * THE STRUCTURAL FIX IS `_renderErrors` BELOW, not the individual cases. A render error in
 * Vue is delivered to the app's `errorHandler`, and if nothing installs one it becomes an
 * unhandled rejection — invisible to `expect`. Installing one and asserting it stayed
 * empty is what makes this class of failure ASSERTABLE at all. Every test here would still
 * pass on the broken surface without it, which is exactly how the defect survived.
 *
 * The shape itself is TRAPS §15 one surface over: "a stub returning `{}` where the endpoint
 * returns `null` can crash a render". `/vendors/service-center/{id}` taught this; the fleet
 * holds panel repeated it, and the wrong-shaped stub that hid it is entry 16's pattern —
 * the test passed because nothing read the value.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

import FleetWorkspaceSurface from "../src/surfaces/FleetWorkspaceSurface.vue";
import { logout, setActiveFleet, setToken } from "../src/core/api.js";

const REPORT = {
  driver_count: 1,
  recovered_cents: 0,
  owed_cents: 0,
  fuel_saved_cents: 0,
  members: [
    { driver_account_id: "acc-owner-1234", recovered_cents: 0, owed_cents: 0, fuel_saved_cents: 0 },
  ],
};
const CLAIMS = { owed_cents: 0, recovered_cents: 0, by_counterparty: {} };

function jsonOk(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

/** AI-CONTEXT: every fetch the workspace makes, with the holds payload under test. */
function stubFleet(holdsBody) {
  return vi.fn().mockImplementation((url) => {
    const u = String(url);
    if (u.endsWith("/fleet/mine")) return jsonOk([{ fleet_id: "fl-1", name: "Acme", role: "owner" }]);
    if (u.includes("/holds")) return holdsBody;
    if (u.includes("/report")) return jsonOk(REPORT);
    if (u.includes("/claims")) return jsonOk(CLAIMS);
    return jsonOk({});
  });
}

let renderErrors;

/**
 * AI-CONTEXT: the whole point of this file. Without an errorHandler, a render error is an
 * unhandled rejection: the process notices, `expect` does not, and the suite reports
 * green while the screen is broken.
 */
function mountWorkspace() {
  return mount(FleetWorkspaceSurface, {
    global: {
      config: {
        errorHandler(err) {
          renderErrors.push(err);
        },
      },
    },
  });
}

beforeEach(() => {
  renderErrors = [];
  setToken("tok-fleet");
  setActiveFleet("fl-1");
});

afterEach(() => {
  vi.unstubAllGlobals();
  setActiveFleet(null);
  logout();
});

describe("FleetWorkspaceSurface — a holds payload of an unexpected shape", () => {
  it("does not throw in render when the payload carries no holds array", async () => {
    // AI-CONTEXT: the exact body the fleet test's catch-all `jsonOk({})` was feeding it
    vi.stubGlobal("fetch", stubFleet(jsonOk({})));

    const w = mountWorkspace();
    await flushPromises();

    expect(renderErrors).toEqual([]);
    w.unmount();
  });

  it("still renders the money the workspace DID load", async () => {
    /**
     * AI-CONTEXT: the surface's own rule, in its docstring: holds "fails SOFT and separately from the
     * workspace... a fleet whose overlay flag is off gets a 404 which must not blank a
     * workspace whose money figures loaded perfectly." A malformed payload has to obey the
     * same rule as a 404 — the render error broke it, taking the KPIs down with the panel.
     */
    vi.stubGlobal("fetch", stubFleet(jsonOk({})));

    const w = mountWorkspace();
    await flushPromises();

    expect(renderErrors).toEqual([]);
    expect(w.find(".kpi").exists()).toBe(true);
    w.unmount();
  });

  it("hides the panel rather than rendering half of it", async () => {
    /**
     * AI-CONTEXT: a payload that is not a holds payload is treated as absent, exactly like the 404 the
     * catch already handles. Rendering the panel with an empty state would assert
     * "no claims are held" — a claim about a fleet's money, made from a response we could
     * not read.
     */
    vi.stubGlobal("fetch", stubFleet(jsonOk({})));

    const w = mountWorkspace();
    await flushPromises();

    // AI-CONTEXT: the `renderErrors` assertion is NOT redundant here, and leaving it out
    // was a bug in this test. On the BROKEN surface the panel is also absent — because
    // the render threw before reaching it — so `.holds` being missing passed either way.
    // A test that cannot tell "hidden deliberately" from "crashed before it got there" is
    // asserting nothing about the fix. This pair distinguishes them.
    expect(renderErrors).toEqual([]);
    expect(w.find(".holds").exists()).toBe(false);
    // AI-CONTEXT: and the rest of the workspace is untouched — the fail-soft rule
    expect(w.find(".kpi").exists()).toBe(true);
    w.unmount();
  });

  it("renders the panel normally when the payload IS well formed", async () => {
    // AI-CONTEXT: the guard must not have made the panel unreachable — this is the shape
    // the real endpoint returns (api/app/api/m14_recovery.py: holds, can_send, send_blocked_by)
    vi.stubGlobal(
      "fetch",
      stubFleet(jsonOk({ holds: [], can_send: true, send_blocked_by: null })),
    );

    const w = mountWorkspace();
    await flushPromises();

    expect(renderErrors).toEqual([]);
    expect(w.find(".holds").exists()).toBe(true);
    expect(w.find(".holds__empty").exists()).toBe(true);
    w.unmount();
  });

  /**
   * AI-CONTEXT: two non-array values, because they break the surface DIFFERENTLY and a
   * single case would have proved less than it looked.
   *
   * `null` reproduces the original class exactly: `holds.holds.length` on undefined-ish
   * throws a TypeError in render.
   *
   * A STRING does not. `"none".length` is 4, so nothing throws there — instead Vue's
   * `v-for` iterates the string's characters, every `h.hold_id` is undefined, and the
   * i18n lookup for `fleet.basis.undefined` throws a missing-key error. Same visible
   * symptom, entirely different path, and it renders four bogus rows on the way.
   *
   * Both assert `.holds` is ABSENT as well as `renderErrors` empty. Without the DOM
   * assertion a test could pass merely because nothing threw, which for the string case
   * would still mean four fabricated rows about a fleet's held claims.
   */
  it.each([
    ["null", null],
    ["a string", "none"],
    ["a number", 42],
  ])("survives a holds value that is %s", async (_label, value) => {
    vi.stubGlobal("fetch", stubFleet(jsonOk({ holds: value, can_send: true })));

    const w = mountWorkspace();
    await flushPromises();

    expect(renderErrors).toEqual([]);
    expect(w.find(".holds").exists()).toBe(false);
    expect(w.find(".kpi").exists()).toBe(true);
    w.unmount();
  });

  it("treats a null payload as absent, as the 404 path already does", async () => {
    vi.stubGlobal("fetch", stubFleet(jsonOk(null)));

    const w = mountWorkspace();
    await flushPromises();

    expect(renderErrors).toEqual([]);
    expect(w.find(".holds").exists()).toBe(false);
    w.unmount();
  });
});
