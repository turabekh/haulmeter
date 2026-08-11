// AI-CONTEXT: D2 — signing out tells the server, and never depends on it.
//
// There was no logout route at all, so clearing localStorage left the bearer valid for the
// rest of its 30-day TTL. The call is fire-and-forget on purpose: a driver signing out in
// a dead zone must still be signed out on this device, and a sign-out button that hangs or
// refuses on a bad connection is worse than a token that dies at TTL.
import { describe, it, expect, vi, afterEach } from "vitest";
import { setToken, logout, activeStopId } from "../src/core/api.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

function calls(spy) {
  return spy.mock.calls.map(([url, opts]) => ({ url: String(url), method: opts?.method }));
}

describe("signing out", () => {
  it("tells the server, with the token still attached", () => {
    setToken("tok-1");
    const spy = vi.fn(() => Promise.resolve({ ok: true, status: 204 }));
    vi.stubGlobal("fetch", spy);

    logout();

    const post = calls(spy).find((c) => c.url.includes("/auth/logout"));
    expect(post).toBeTruthy();
    expect(post.method).toBe("POST");
    // the Authorization header is what the route resolves — it must be sent BEFORE the
    // local token is cleared, which is why the call leads
    expect(spy.mock.calls[0][1].headers.Authorization).toBe("Bearer tok-1");
  });

  it("completes the local sign-out when the endpoint 500s", async () => {
    setToken("tok-2");
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: false, status: 500 })));

    logout();
    await Promise.resolve();

    expect(localStorage.getItem("longhaul.session")).toBe(null);
  });

  it("completes the local sign-out when the device is offline", async () => {
    setToken("tok-3");
    // a rejected fetch is what an offline device produces — and it must not surface as an
    // unhandled rejection on the way out
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Failed to fetch"))));

    logout();
    await Promise.resolve();

    expect(localStorage.getItem("longhaul.session")).toBe(null);
  });

  it("does not await the call — sign-out is synchronous from the caller's view", () => {
    setToken("tok-4");
    // a fetch that never settles: if `logout()` waited on it, nothing below would run
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));

    const returned = logout();

    expect(returned).toBeUndefined();
    expect(localStorage.getItem("longhaul.session")).toBe(null);
  });

  it("still sweeps the module-scope refs the previous driver left behind", () => {
    // the subtle half the review found correct — a regression here renders the last
    // driver's stop to the next one, and no storage-level assertion would see it
    setToken("tok-5");
    activeStopId.value = "stop-1";
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: true, status: 204 })));

    logout();

    expect(activeStopId.value).toBe(null);
  });

  it("makes no call when there is no session to end", () => {
    logout(); // already signed out
    const spy = vi.fn();
    vi.stubGlobal("fetch", spy);

    logout();

    expect(spy).not.toHaveBeenCalled();
  });
});
