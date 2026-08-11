// AI-CONTEXT: D8 — the driver can see and close the links they handed out.
//
// Extend and revoke have existed and been tested since sharing shipped, and nothing could
// LIST what there was to extend or revoke — so the controls were reachable only by someone
// already holding a share id, which no screen ever showed. A driver could send a broker a
// link to their own evidence and then have no way to see that they had.
//
// The opens caveat is the other half: a link open is a URL being fetched, and mail-security
// scanners fetch URLs (finding F4-1). The number is honest; the screen says what it is.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import ClaimSurface from "../src/surfaces/ClaimSurface.vue";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout, setActiveStop } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

const CLAIM = {
  claim_id: "c-1",
  load_id: "load-1",
  evidence_log_ref: "log-1",
  amount_cents: 15000,
  detention_seconds: 7200,
  free_time_minutes: 120,
  rate_cents_per_hour: 7500,
  state: "invoiced",
  mode: "invoice",
  facility: "Dock 4",
  counterparty: "Acme",
  counterparty_email: "ap@acme.example",
  notice_sent: true,
  notice_delivery: "sent",
  filed: true,
  chain_valid: true,
  record_count: 3,
  artifact_count: 1,
  timeline: [],
};

const ACTIVE_SHARE = {
  share_id: "s-1",
  created_at: "2026-08-01T10:00:00Z",
  expires_at: "2027-02-01T10:00:00Z",
  revoked: false,
  revoked_at: null,
  recipient: "ap@acme.example",
  opened_count: 3,
  last_opened_at: "2026-08-02T10:00:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
  logout();
});

async function mountClaim(shareSequence) {
  setToken("tok");
  let n = 0;
  const calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url, opts) => {
      const u = String(url);
      calls.push({ url: u, method: opts?.method });
      if (u.includes("/protection/share?log_ref=")) {
        return jsonOk(shareSequence[Math.min(n++, shareSequence.length - 1)]);
      }
      if (u.includes("/protection/share/")) return jsonOk({ revoked: true });
      if (u.includes("/claim")) return jsonOk(CLAIM);
      return jsonOk({});
    }),
  );
  const r = createRouter({ history: createMemoryHistory(), routes });
  r.push("/claim/stop-1");
  await r.isReady();
  const w = mount(ClaimSurface, { global: { plugins: [r] } });
  await flushPromises();
  return { w, calls };
}

describe("the shares list", () => {
  it("lists a link with its expiry and open count", async () => {
    const { w } = await mountClaim([[ACTIVE_SHARE]]);

    expect(w.text()).toContain(en["claim.shares"]);
    expect(w.text()).toContain(en["claim.share_active"]);
    expect(w.text()).toContain("2027-02-01");
    expect(w.text()).toContain("3");
  });

  it("says the open count may be a scanner, not a person", async () => {
    const { w } = await mountClaim([[ACTIVE_SHARE]]);

    expect(w.text()).toContain(en["claim.share_opens_caveat"]);
  });

  it("states the absence rather than showing an empty list", async () => {
    const { w } = await mountClaim([[]]);

    expect(w.text()).toContain(en["claim.shares_none"]);
    expect(w.findAll("li.share")).toHaveLength(0);
  });

  it("revokes a link and shows it as revoked rather than hiding it", async () => {
    const revoked = { ...ACTIVE_SHARE, revoked: true, revoked_at: "2026-08-03T10:00:00Z" };
    const { w, calls } = await mountClaim([[ACTIVE_SHARE], [revoked]]);

    await w.findAll("button.share__act").find((b) => b.text() === en["claim.share_revoke"]).trigger("click");
    await flushPromises();

    expect(calls.some((c) => c.method === "DELETE")).toBe(true);
    // revocation is a fact about a document that was sent, not an undo
    expect(w.text()).toContain(en["claim.share_revoked"]);
    expect(w.findAll("li.share")).toHaveLength(1);
    expect(w.findAll("button.share__act")).toHaveLength(0);
  });

  it("extends a link and shows the new expiry", async () => {
    const extended = { ...ACTIVE_SHARE, expires_at: "2027-08-01T10:00:00Z" };
    const { w, calls } = await mountClaim([[ACTIVE_SHARE], [extended]]);

    await w.findAll("button.share__act").find((b) => b.text() === en["claim.share_extend"]).trigger("click");
    await flushPromises();

    expect(calls.some((c) => c.method === "POST" && c.url.includes("/extend"))).toBe(true);
    expect(w.text()).toContain("2027-08-01");
  });
});

// --- the failed-state framing ---
const METER = {
  stop_id: "stop-1",
  load_id: "load-1",
  facility_name: "Dock 4",
  counterparty: "Acme",
  counterparty_email: "ap@acme.example",
  appointment: null,
  arrived: true,
  free_time_minutes: 120,
  rate_cents_per_hour: 7500,
  phase: "accruing",
  free_time_remaining_seconds: 0,
  detention_seconds: 3600,
  detention_cents: 7500,
  notice_sent: false,
  photos_captured: 4,
  photos_required: 4,
  bol_captured: true,
  filed: false,
};

async function mountLoad(delivery) {
  setToken("tok");
  setActiveStop("stop-1");
  vi.stubGlobal(
    "fetch",
    vi.fn((url) =>
      String(url).includes("/meter")
        ? jsonOk({ ...METER, notice_delivery: delivery })
        : jsonOk({}),
    ),
  );
  const w = mount(LoadSurface, {
    global: { plugins: [createRouter({ history: createMemoryHistory(), routes })] },
  });
  await flushPromises();
  return w;
}

describe("the notice control after a permanent failure", () => {
  it("says Send again, not Send notice", async () => {
    // the control was always OFFERED here — `notice_sent` is false, so the ladder reached
    // the notice rung — but it read as though nothing had been tried
    const w = await mountLoad("failed");

    const cta = w.findAll("button.cta").map((b) => b.text());
    expect(cta).toContain(en["load.cta.notice_again"]);
    expect(cta).not.toContain(en["load.cta.notice"]);
  });

  it("keeps the plain wording while a retry is still queued", async () => {
    // `retrying` means the sweep owns that row; tapping produces no new message, so
    // inviting a resend would be the misleading option here
    const w = await mountLoad("retrying");

    expect(w.findAll("button.cta").map((b) => b.text())).toContain(en["load.cta.notice"]);
  });

  it("says Send notice on a stop nobody has tried yet", async () => {
    const w = await mountLoad("not_sent");

    expect(w.findAll("button.cta").map((b) => b.text())).toContain(en["load.cta.notice"]);
  });
});
