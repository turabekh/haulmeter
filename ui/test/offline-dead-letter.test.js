// AI-CONTEXT: U-07 and U-08 — the offline queue lost writes and said "synced".
//
// `flushQueue` never consulted `resp.ok`, so a 401, a 422 and a 500 were each
// indistinguishable from a success: the item was shifted off the queue, pendingWrites
// fell to zero, and the status strip — the only surface that reports sync state at all —
// went quiet. The driver was shown synced over evidence that no longer existed.
//
// The case this product exists to serve: a BOL photographed at a dock with no signal,
// replayed two hours later against a session that expired overnight. That evidence is
// what a detention claim is made of. §15.4 requires a failed money-moving action to be
// "explicit and persistent until resolved"; this was silent and permanent.
//
// These tests assert the three outcomes separately, because collapsing them is the
// defect: a network throw keeps the queue, a 5xx retries, a 4xx dead-letters.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  setToken,
  logout,
  flushQueue,
  queueForTests,
  pendingWrites,
  failedWrites,
  listFailedWrites,
} from "../src/core/api.js";

function respond(status) {
  return vi.fn(() => Promise.resolve({ ok: status < 400, status, json: () => ({}) }));
}

beforeEach(() => {
  localStorage.clear();
  setToken("tok");
});

afterEach(() => {
  logout();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("a write the server refuses (U-07)", () => {
  it("is dead-lettered, not dropped — the driver is never told it synced", async () => {
    queueForTests([{ path: "/protection/evidence", body: { doc: "bol" }, opId: "op-1" }]);
    vi.stubGlobal("fetch", respond(401));

    await flushQueue();

    expect(pendingWrites.value, "it must leave the pending queue").toBe(0);
    expect(failedWrites.value, "...and land somewhere the driver can be told about").toBe(1);
  });

  it("keeps the whole write, so it stays replayable exactly once", async () => {
    // the opId is F12's idempotency key. Reduce this to a message and a future retry
    // surface can no longer replay it safely — that option has to survive the failure.
    queueForTests([{ path: "/protection/evidence", body: { doc: "bol" }, opId: "op-1" }]);
    vi.stubGlobal("fetch", respond(422));

    await flushQueue();

    const [dead] = listFailedWrites();
    expect(dead.path).toBe("/protection/evidence");
    expect(dead.body).toEqual({ doc: "bol" });
    expect(dead.opId).toBe("op-1");
    expect(dead.reason).toBe("http_422");
    expect(dead.failed_at).toBeTruthy();
  });

  it("does not block the writes behind it", async () => {
    queueForTests([
      { path: "/a", body: {}, opId: "op-1" },
      { path: "/b", body: {}, opId: "op-2" },
    ]);
    let call = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        call += 1;
        const status = call === 1 ? 422 : 200;
        return Promise.resolve({ ok: status < 400, status, json: () => ({}) });
      }),
    );

    await flushQueue();

    expect(pendingWrites.value).toBe(0);
    expect(failedWrites.value).toBe(1);
    expect(listFailedWrites()[0].path).toBe("/a");
  });
});

describe("a write the server could not take right now (U-08)", () => {
  it("survives a 500 — the box being briefly unwell must not destroy evidence", async () => {
    queueForTests([{ path: "/protection/evidence", body: { doc: "bol" }, opId: "op-1" }]);
    vi.stubGlobal("fetch", respond(500));

    await flushQueue();

    expect(pendingWrites.value, "still queued for the next attempt").toBe(1);
    expect(failedWrites.value, "a restart window is not a permanent rejection").toBe(0);
  });

  it("survives a 429 the same way", async () => {
    queueForTests([{ path: "/a", body: {}, opId: "op-1" }]);
    vi.stubGlobal("fetch", respond(429));
    await flushQueue();
    expect(pendingWrites.value).toBe(1);
    expect(failedWrites.value).toBe(0);
  });

  it("succeeds on a later attempt and leaves nothing behind", async () => {
    queueForTests([{ path: "/a", body: {}, opId: "op-1" }]);
    vi.stubGlobal("fetch", respond(500));
    await flushQueue();
    expect(pendingWrites.value).toBe(1);

    vi.stubGlobal("fetch", respond(200));
    await flushQueue();
    expect(pendingWrites.value).toBe(0);
    expect(failedWrites.value).toBe(0);
  });

  it("gives up after a bounded number of attempts rather than blocking the queue forever", async () => {
    // head-of-line protection: one write the server keeps 500ing would otherwise stop
    // every write behind it from ever reaching the server
    queueForTests([{ path: "/a", body: {}, opId: "op-1" }]);
    vi.stubGlobal("fetch", respond(503));

    for (let i = 0; i < 6; i += 1) await flushQueue();

    expect(pendingWrites.value).toBe(0);
    expect(failedWrites.value).toBe(1);
    expect(listFailedWrites()[0].reason).toContain("503");
  });
});

describe("a dead zone is still not a failure (§15.1)", () => {
  it("keeps the queue intact when the network throws", async () => {
    queueForTests([{ path: "/a", body: {}, opId: "op-1" }]);
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("offline"))),
    );

    await flushQueue();

    expect(pendingWrites.value).toBe(1);
    expect(failedWrites.value, "offline is a mode, not an error").toBe(0);
  });
});

describe("failed writes belong to one driver (U-02)", () => {
  it("does not survive a logout into the next driver's session", async () => {
    queueForTests([{ path: "/a", body: {}, opId: "op-1" }]);
    vi.stubGlobal("fetch", respond(422));
    await flushQueue();
    expect(failedWrites.value).toBe(1);

    logout();

    expect(failedWrites.value).toBe(0);
    expect(listFailedWrites()).toEqual([]);
  });
});

// The count is only a fix if the driver sees it. The strip is the ONLY surface in the
// app that reports sync state, which is why the silent drop was invisible for so long.
describe("the status strip says so (§15.4)", () => {
  it("renders the failed count, distinct from the pending one", async () => {
    const { mount } = await import("@vue/test-utils");
    const StatusStrip = (await import("../src/core/components/StatusStrip.vue")).default;
    const w = mount(StatusStrip, { props: { online: true, pending: 0, failed: 2 } });
    expect(w.find(".strip__failed").exists()).toBe(true);
    expect(w.find(".strip__failed").text()).toContain("2");
    expect(w.find(".strip__pending").exists(), "a refused write is NOT pending").toBe(false);
  });

  it("shows no failed count when nothing has failed", async () => {
    const { mount } = await import("@vue/test-utils");
    const StatusStrip = (await import("../src/core/components/StatusStrip.vue")).default;
    const w = mount(StatusStrip, { props: { online: true, pending: 0, failed: 0 } });
    // the strip itself is always present since entry 230 (it carries the bell); what
    // entry 89 was protecting is that its CONDITIONAL rows stay absent, and a refused
    // write must never be implied by chrome that is there for another reason
    expect(w.find(".strip").exists()).toBe(true);
    expect(w.find(".strip__failed").exists(), "no refused write, no count").toBe(false);
  });

  it("carries a label rather than a bare number (C-1: never colour alone)", async () => {
    const { mount } = await import("@vue/test-utils");
    const StatusStrip = (await import("../src/core/components/StatusStrip.vue")).default;
    const en = (await import("../src/core/i18n/en.json")).default;
    const w = mount(StatusStrip, { props: { online: true, pending: 0, failed: 1 } });
    expect(w.find(".strip__failed").attributes("aria-label")).toBe(en["system.failed"]);
  });
});
