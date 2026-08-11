// AI-CONTEXT: the screens that make four finished things usable (D1, D5).
//
// The flag has been ignorable for its entire existence, which is how an admin-issued
// temporary password came to be a permanent one. A dismissible force is not a force.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import PasswordSurface from "../src/surfaces/PasswordSurface.vue";
import { routes, installAuthGuard } from "../src/router.js";
import { setToken, logout, mustChangePassword } from "../src/core/api.js";
import { useDriverState, DriverState, __resetStateForTests } from "../src/core/state.js";
import en from "../src/core/i18n/en.json";

function ok(body) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
    headers: { get: () => null },
  });
}

function fail(status, detail = null, retryAfter = null) {
  return Promise.resolve({
    ok: false,
    status,
    json: () => Promise.resolve({ detail }),
    headers: { get: (h) => (h === "Retry-After" ? retryAfter : null) },
  });
}

function mountSurface() {
  const r = createRouter({ history: createMemoryHistory(), routes });
  return mount(PasswordSurface, { global: { plugins: [r] } });
}

async function fill(w, current = "old-password", next = "a-better-password") {
  const inputs = w.findAll("input");
  await inputs[0].setValue(current);
  await inputs[1].setValue(next);
  await w.find("button.pw__cta").trigger("click");
  await flushPromises();
}

afterEach(() => {
  vi.unstubAllGlobals();
  mustChangePassword.value = false;
  __resetStateForTests();
  logout();
});

describe("the change-password screen", () => {
  it("changes the password and confirms it", async () => {
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn(() => ok({ changed: true, other_sessions_ended: 0 })));
    const w = mountSurface();

    await fill(w);

    expect(w.text()).toContain(en["pw.ok"]);
  });

  it("says the other devices were signed out — but only when some were", async () => {
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn(() => ok({ changed: true, other_sessions_ended: 2 })));
    const w = mountSurface();

    await fill(w);

    expect(w.text()).toContain(en["pw.others_out"]);
  });

  it("says nothing rather than saying zero", async () => {
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn(() => ok({ changed: true, other_sessions_ended: 0 })));
    const w = mountSurface();

    await fill(w);

    expect(w.text()).not.toContain(en["pw.others_out"]);
  });

  it("refuses a new password under the floor before asking the server", async () => {
    setToken("tok");
    const spy = vi.fn(() => ok({}));
    vi.stubGlobal("fetch", spy);
    const w = mountSurface();
    const inputs = w.findAll("input");

    await inputs[0].setValue("old-password");
    await inputs[1].setValue("sevench");

    expect(w.text()).toContain(en["auth.password_too_short"]);
    expect(w.find("button.pw__cta").attributes("disabled")).toBeDefined();
    const posts = spy.mock.calls.filter(([, o]) => o?.method === "POST");
    expect(posts).toHaveLength(0);
  });

  // --- the errors, each surfaced honestly and never as a false success ---
  it("says the current password was wrong on a 401", async () => {
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn(() => fail(401)));
    const w = mountSurface();

    await fill(w);

    expect(w.text()).toContain(en["pw.err_current"]);
    expect(w.text()).not.toContain(en["pw.ok"]);
  });

  it("says how long to wait on a 429", async () => {
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn(() => fail(429, null, "45")));
    const w = mountSurface();

    await fill(w);

    expect(w.text()).toContain("45");
    expect(w.text()).not.toContain(en["pw.ok"]);
  });

  it("says the network failed, and never claims success", async () => {
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    const w = mountSurface();

    await fill(w);

    expect(w.text()).toContain(en["pw.err_network"]);
    expect(w.text()).not.toContain(en["pw.ok"]);
  });

  // --- the forced framing ---
  it("explains itself when the change is forced", async () => {
    setToken("tok");
    mustChangePassword.value = true;
    vi.stubGlobal("fetch", vi.fn(() => ok({})));
    const w = mountSurface();
    await flushPromises();

    expect(w.text()).toContain(en["pw.forced_title"]);
    expect(w.text()).toContain(en["pw.forced_hint"]);
  });

  it("withdraws at speed, like every driver surface that claims to", async () => {
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn(() => ok({})));
    const w = mountSurface();
    useDriverState().setState(DriverState.DRIVING);
    await flushPromises();

    expect(w.findAll("input")).toHaveLength(0);
  });
});

// --- D5: the gate a deep link cannot route around ---
describe("the forced gate", () => {
  function guardedRouter() {
    const r = createRouter({ history: createMemoryHistory(), routes });
    installAuthGuard(r);
    return r;
  }

  it("sends a driver holding a temporary password to the change screen", async () => {
    setToken("tok");
    mustChangePassword.value = true;
    const r = guardedRouter();

    await r.push("/map");

    expect(r.currentRoute.value.name).toBe("password");
  });

  it("cannot be bypassed by a DEEP LINK to any other surface", async () => {
    setToken("tok");
    mustChangePassword.value = true;
    const r = guardedRouter();

    for (const path of ["/money", "/load", "/docs", "/more"]) {
      await r.push(path);
      expect(r.currentRoute.value.name, `deep link to ${path} escaped the gate`).toBe(
        "password",
      );
    }
  });

  it("lets the driver reach the change screen itself", async () => {
    setToken("tok");
    mustChangePassword.value = true;
    const r = guardedRouter();

    await r.push("/password");

    expect(r.currentRoute.value.name).toBe("password");
  });

  it("gets out of the way once the flag clears", async () => {
    setToken("tok");
    mustChangePassword.value = false;
    const r = guardedRouter();

    await r.push("/money");

    expect(r.currentRoute.value.name).toBe("money");
  });
});
