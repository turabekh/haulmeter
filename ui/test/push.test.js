/* AI-CONTEXT: Web Push enrolment rules (§23 entry 111).
 *
 * These assert the things that are invisible on a screenshot and permanent when wrong.
 * The browser's permission prompt is ONE-SHOT — a "no" is final for the origin — so
 * "we never ask without a tap" is not a preference, it is the difference between a
 * driver who can be reached and one who never can be again.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  pushSupported,
  permissionState,
  urlBase64ToUint8Array,
  enable,
  disable,
} from "../src/core/push.js";

const KEY = "BF4z4FWmN9IKSEtd9rWZ6Jh6IRwhtbAO1i_RA7OjN9Y-xXKJ6A2bBHN-Cf_jltcCL-u3lk42twhaXyriPezUy-Q";

function subscription(endpoint = "https://push.example/abc") {
  return {
    toJSON: () => ({ endpoint, keys: { p256dh: "p256", auth: "auth" } }),
    unsubscribe: vi.fn().mockResolvedValue(true),
  };
}

function stubBrowser({ permission = "default", secure = true, existing = null } = {}) {
  const requestPermission = vi.fn().mockResolvedValue(permission);
  const subscribe = vi.fn().mockResolvedValue(subscription());
  vi.stubGlobal("isSecureContext", secure);
  vi.stubGlobal("Notification", { permission, requestPermission });
  vi.stubGlobal("PushManager", function PushManager() {});
  vi.stubGlobal("navigator", {
    serviceWorker: {
      register: vi.fn().mockResolvedValue({ pushManager: { subscribe } }),
      getRegistration: vi.fn().mockResolvedValue({
        pushManager: {
          subscribe,
          getSubscription: vi.fn().mockResolvedValue(existing),
        },
      }),
    },
  });
  vi.stubGlobal("atob", (s) => Buffer.from(s, "base64").toString("binary"));
  return { requestPermission, subscribe };
}

describe("push enrolment (§23 entry 111)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("treats a non-secure page as unsupported, like the mic before it (§23 entry 91)", () => {
    stubBrowser({ secure: false });
    // the constructors EXIST over plain http and then refuse to work — testing for
    // their presence is the bug entry 91 recorded; isSecureContext is the real answer
    expect(pushSupported()).toBe(false);
  });

  it("is supported on a secure page with the APIs present", () => {
    stubBrowser();
    expect(pushSupported()).toBe(true);
    expect(permissionState()).toBe("default");
  });

  it("NEVER requests permission without an explicit call", async () => {
    const { requestPermission } = stubBrowser();
    // merely importing and asking about state must not spend the one-shot prompt
    pushSupported();
    permissionState();
    expect(requestPermission).not.toHaveBeenCalled();
  });

  it("does not prompt when the server has no VAPID key configured", async () => {
    const { requestPermission } = stubBrowser();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ enabled: false, public_key: "" }),
    }));

    const result = await enable();

    expect(result).toEqual({ ok: false, reason: "unconfigured" });
    // the prompt is one-shot: spending it on a server that cannot send is unforgivable
    expect(requestPermission).not.toHaveBeenCalled();
  });

  it("subscribes and registers the endpoint when the driver accepts", async () => {
    const { subscribe } = stubBrowser({ permission: "granted" });
    const calls = [];
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url, opts) => {
      calls.push(`${opts?.method || "GET"} ${String(url)}`);
      return Promise.resolve({ ok: true, json: async () => ({ enabled: true, public_key: KEY }) });
    }));

    const result = await enable();

    expect(result.ok).toBe(true);
    expect(subscribe).toHaveBeenCalledWith(
      expect.objectContaining({ userVisibleOnly: true }),
    );
    expect(calls.some((c) => c.includes("POST") && c.includes("/notifications/push/subscribe"))).toBe(true);
  });

  it("reports a refusal as denied rather than an error", async () => {
    stubBrowser({ permission: "denied" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ enabled: true, public_key: KEY }),
    }));

    expect(await enable()).toEqual({ ok: false, reason: "denied" });
  });

  it("unsubscribes the browser even if telling the server fails", async () => {
    const existing = subscription();
    stubBrowser({ permission: "granted", existing });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    const result = await disable();

    // a driver who turned alerts off has to actually stop hearing them
    expect(existing.unsubscribe).toHaveBeenCalled();
    expect(result.ok).toBe(true);
  });

  it("decodes the application server key to the 65-byte EC point", () => {
    vi.stubGlobal("atob", (s) => Buffer.from(s, "base64").toString("binary"));
    const bytes = urlBase64ToUint8Array(KEY);
    // a wrong conversion surfaces as an opaque DOMException with no message
    expect(bytes).toBeInstanceOf(Uint8Array);
    expect(bytes.length).toBe(65);
    expect(bytes[0]).toBe(4); // uncompressed point marker
  });
});
