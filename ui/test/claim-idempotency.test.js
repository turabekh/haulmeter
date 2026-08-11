// AI-CONTEXT: finding F2 on the screen — a second tap on "Generate claim".
//
// The server now answers a repeat filing with 409 and the FIRST filing's claim, because
// a retry after a success is not an error the driver caused. `generateClaim` used to
// throw on any non-2xx, and `onGenerateClaim`'s catch is the offline path — so a 409 was
// swallowed as "we are offline", the tab went on reading "not filed", and the Meter kept
// running on money that was already invoiced. The driver's next move from that screen is
// to tap Generate claim again.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout, setActiveStop, generateClaim } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const ALREADY_FILED = {
  error: "already_filed",
  claim_id: "claim-1",
  state: "invoiced",
  amount_cents: 15000,
  receivable_ref: "rec-1",
};

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

function conflict(detail) {
  return Promise.resolve({
    ok: false,
    status: 409,
    json: () => Promise.resolve({ detail }),
  });
}

const METER = {
  stop_id: "stop-1",
  facility_name: "Dock 4",
  counterparty: "Acme",
  appointment: null,
  arrived: true,
  free_time_minutes: 120,
  rate_cents_per_hour: 7500,
  phase: "accruing",
  free_time_remaining_seconds: 0,
  detention_seconds: 7200,
  detention_cents: 15000,
  notice_sent: true,
  photos_captured: 4,
  photos_required: 4,
  bol_captured: true,
  filed: false,
};

afterEach(() => {
  vi.unstubAllGlobals();
  logout();
});

describe("a repeat filing", () => {
  it("comes back as the first filing's claim, not as a thrown error", async () => {
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn(() => conflict(ALREADY_FILED)));

    const result = await generateClaim("stop-1");

    expect(result.already_filed).toBe(true);
    expect(result.amount_cents).toBe(15000);
    expect(result.receivable_ref).toBe("rec-1");
  });

  it("still throws for a failure that is NOT an already-filed conflict", async () => {
    setToken("tok");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) })),
    );

    await expect(generateClaim("stop-1")).rejects.toThrow();
  });

  it("freezes the Meter on the filed amount instead of reading as offline", async () => {
    setToken("tok");
    setActiveStop("stop-1");
    vi.stubGlobal(
      "fetch",
      vi.fn((url, opts) => {
        const u = String(url);
        if (u.includes("/load/stop-1/claim") && opts?.method === "POST") {
          return conflict(ALREADY_FILED);
        }
        if (u.includes("/load/stop-1/meter")) return jsonOk(METER);
        return jsonOk({});
      }),
    );
    const w = mount(LoadSurface, {
      global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] },
    });
    await flushPromises();

    const cta = w.findAll("button.cta").find((b) => b.text() === en["load.cta.claim"]);
    expect(cta).toBeTruthy();
    await cta.trigger("click");
    await flushPromises();

    expect(w.text()).toContain(en["load.filed_frozen"]);
    expect(w.text()).toContain("$150");
  });
});
