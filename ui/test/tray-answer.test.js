// AI-CONTEXT: the seam between the app and the service worker — the one nothing tested.
//
// §23 entry 112 built the tray answer so a driver can say how full a lot is from a
// LOCKED phone, without opening the app. That path crosses two files that never meet in
// any other test: `core/api.js` WRITES the session token to IndexedDB and
// `public/sw.js` READS it back, because a worker cannot reach localStorage.
//
// It was inert. `mirrorTokenToIdb`'s only caller was `setToken`, which is used by nine
// TEST files and by no production code — the real sign-in goes through `_adopt`, which
// mirrored nothing. So `readToken` resolved null for every driver, `reportLotStatus`
// returned false, and every tray tap fell through to opening the app. Nothing looked
// broken, because opening the app is a deliberate fallback.
//
// Two things hid it, and both are worth remembering:
// · happy-dom implements NO IndexedDB, so `mirrorTokenToIdb`'s own
//   `typeof indexedDB === "undefined"` guard made it a no-op in every existing test.
//   That is why `fake-indexeddb` is here — a hand-rolled double could be wrong in the
//   same shape as the code and prove nothing.
// · the tests that did touch it called `setToken`, exercising a path production never
//   takes. HANDOFF-104 §4 is the same defect one layer down.
//
// So these tests drive the REAL `public/sw.js` source rather than a copy of its rules —
// sw.js's own argument for deciding nothing is that a vocabulary duplicated somewhere
// else goes stale, and a test is somewhere else.
import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { login, logout } from "../src/core/api.js";
import { __resetIdbForTests } from "../src/core/idb.js";

// read from the vitest root (ui/) rather than import.meta.url: test modules are served
// by vite over http, so import.meta.url is not a file URL here
const SW_RAW = readFileSync(resolve(process.cwd(), "src/sw.js"), "utf8");

// AI-CONTEXT: this file MOVED and became a module (§23 entry 143).
//
// It lived in `public/` and the note here said "sw.js is not a module and must not
// become one: it has no build step, and the browser runs this exact file". Both halves
// changed when the offline shell landed: it is now `src/sw.js`, a bundler ENTRY that
// vite-plugin-pwa compiles in `injectManifest` mode, and the browser runs the built
// output rather than this source.
//
// What has NOT changed is what these tests are about — the push rendering, the
// lock-screen lot report and the deep-link focus rule are the same hand-written code,
// which is the entire reason `injectManifest` was chosen over a generated worker. So
// the two lines the bundler provides are compiled away here rather than stubbed at
// runtime: an `import` cannot appear inside `new Function`, and precaching is asserted
// against the vite config and the real build in `pwa.test.js`, where it belongs.
const SW_SOURCE = SW_RAW
  .replace(/^import .*$/gm, "")
  .replace(/precacheAndRoute\([^)]*\);/g, "")
  .replace(/registerRoute\(\s*new NavigationRoute\([\s\S]*?\)\s*,?\s*\);/g, "");
function loadServiceWorker(fetchImpl) {
  const listeners = {};
  const self = {
    addEventListener: (type, fn) => {
      listeners[type] = fn;
    },
    skipWaiting: vi.fn(),
    registration: { showNotification: vi.fn(() => Promise.resolve()) },
    clients: {
      claim: vi.fn(() => Promise.resolve()),
      matchAll: vi.fn(() => Promise.resolve([])),
      openWindow: vi.fn(() => Promise.resolve()),
    },
  };
  const factory = new Function(
    "self",
    "indexedDB",
    "fetch",
    `${SW_SOURCE}\nreturn { readToken, reportLotStatus };`,
  );
  return { self, listeners, ...factory(self, globalThis.indexedDB, fetchImpl) };
}

function clickEvent(action, deepLink) {
  const waits = [];
  return {
    action,
    notification: { close: vi.fn(), data: deepLink === null ? null : { deep_link: deepLink } },
    waitUntil: (p) => waits.push(p),
    settled: () => Promise.all(waits),
  };
}

function pushEvent(payload) {
  const waits = [];
  return {
    data: payload === undefined ? null : { json: () => payload },
    waitUntil: (p) => waits.push(p),
    settled: () => Promise.all(waits),
  };
}

// the mirror is fire-and-forget by design — a driver signs in whether or not IDB works —
// so the assertion polls rather than assuming a particular number of ticks.
async function eventually(read, tries = 50) {
  for (let i = 0; i < tries; i += 1) {
    const value = await read();
    if (value) return value;
    await new Promise((r) => setTimeout(r, 0));
  }
  return read();
}

function okLogin(token = "tok-tray") {
  return vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ token, account_id: "acc-1" }),
    }),
  );
}

beforeEach(() => {
  // a fresh IDB per test: `haulmeter` is a real database here and a token left behind
  // would let the no-token case pass for the wrong reason
  globalThis.indexedDB = new IDBFactory();
  // AI-CONTEXT: and the app's cached HANDLE has to go with it. `core/idb.js` opens the
  // database once and keeps it — one open per sign-in instead of one per write, which is
  // what makes the blob queue cheap — so a swapped factory leaves the app writing into a
  // database nothing can read. Without this the mirror lands in the previous test's
  // database and `readToken` correctly reports no token.
  __resetIdbForTests();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("the app writes the token where the service worker reads it", () => {
  it("login() puts the session token in haulmeter/kv/token", async () => {
    globalThis.fetch = okLogin("tok-seam");
    await login("driver@example.com", "pw");

    const { readToken } = loadServiceWorker(vi.fn());
    expect(
      await eventually(readToken),
      "sw.js cannot answer a tray tap without the token the app is supposed to mirror",
    ).toBe("tok-seam");
  });

  it("logout() removes it, so a signed-out phone cannot post as the last driver", async () => {
    globalThis.fetch = okLogin("tok-gone");
    await login("driver@example.com", "pw");
    const { readToken } = loadServiceWorker(vi.fn());
    expect(await eventually(readToken)).toBe("tok-gone");

    logout();
    for (let i = 0; i < 5; i += 1) await new Promise((r) => setTimeout(r, 0));
    expect(await readToken()).toBeNull();
  });
});

describe("answering from the tray (§23 entry 112)", () => {
  it("posts the report and opens nothing", async () => {
    globalThis.fetch = okLogin("tok-answer");
    await login("driver@example.com", "pw");

    const swFetch = vi.fn(() => Promise.resolve({ ok: true }));
    const sw = loadServiceWorker(swFetch);
    await eventually(sw.readToken);

    const event = clickEvent("lot:some", "/facility/fac-42");
    sw.listeners.notificationclick(event);
    await event.settled();

    expect(event.notification.close).toHaveBeenCalled();
    expect(swFetch).toHaveBeenCalledTimes(1);
    const [url, init] = swFetch.mock.calls[0];
    expect(url).toBe("/api/map/report");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer tok-answer");
    // the exact shape of ReportIn in api/app/api/m01_map.py — a wrong signal_type is a
    // 422 the driver never sees, because nothing here is on screen
    expect(JSON.parse(init.body)).toEqual({
      facility_id: "fac-42",
      signal_type: "parking_fullness",
      value: { status: "some" },
    });
    expect(
      sw.self.clients.openWindow,
      "answering from the lock screen must not drag the app open",
    ).not.toHaveBeenCalled();
  });

  it("maps all three actions onto PARKING_STATUS's own values", async () => {
    globalThis.fetch = okLogin("tok-vocab");
    await login("driver@example.com", "pw");
    const swFetch = vi.fn(() => Promise.resolve({ ok: true }));
    const sw = loadServiceWorker(swFetch);
    await eventually(sw.readToken);

    for (const [action, status] of [
      ["lot:empty", "empty"],
      ["lot:some", "some"],
      ["lot:full", "full"],
    ]) {
      expect(await sw.reportLotStatus(action, "/facility/fac-9")).toBe(true);
      const last = swFetch.mock.calls.at(-1)[1];
      expect(JSON.parse(last.body).value).toEqual({ status });
    }
  });

  it("falls back to opening the facility when there is no token, and posts nothing", async () => {
    const swFetch = vi.fn(() => Promise.resolve({ ok: true }));
    const sw = loadServiceWorker(swFetch);

    const event = clickEvent("lot:full", "/facility/fac-7");
    sw.listeners.notificationclick(event);
    await event.settled();

    // §11.7: the driver must not be left believing they answered. Nothing was sent, so
    // the app opens at the facility where the same question is still a chip.
    expect(swFetch).not.toHaveBeenCalled();
    expect(sw.self.clients.openWindow).toHaveBeenCalledWith("/facility/fac-7");
  });

  it("falls back when the post fails, rather than swallowing the answer", async () => {
    globalThis.fetch = okLogin("tok-offline");
    await login("driver@example.com", "pw");
    const swFetch = vi.fn(() => Promise.reject(new Error("offline")));
    const sw = loadServiceWorker(swFetch);
    await eventually(sw.readToken);

    const event = clickEvent("lot:empty", "/facility/fac-3");
    sw.listeners.notificationclick(event);
    await event.settled();

    expect(swFetch).toHaveBeenCalledTimes(1);
    expect(sw.self.clients.openWindow).toHaveBeenCalledWith("/facility/fac-3");
  });
});

describe("the tray buttons themselves", () => {
  it("renders the actions the server sent and invents none", async () => {
    const sw = loadServiceWorker(vi.fn());
    const actions = [
      { action: "lot:empty", title: "Empty" },
      { action: "lot:some", title: "Some" },
      { action: "lot:full", title: "Full" },
    ];
    const event = pushEvent({
      title: "How's the lot at Love's 402?",
      body: "One tap helps the next driver find a spot.",
      deep_link: "/facility/fac-42",
      actions,
    });
    sw.listeners.push(event);
    await event.settled();

    const [title, options] = sw.self.registration.showNotification.mock.calls[0];
    expect(title).toBe("How's the lot at Love's 402?");
    expect(options.actions).toEqual(actions);
    expect(options.data).toEqual({ deep_link: "/facility/fac-42" });
  });

  it("sends no actions when the server sent none, and never three empty buttons", async () => {
    const sw = loadServiceWorker(vi.fn());
    const event = pushEvent({ title: "Detention started · $75/h", deep_link: "/load/abc" });
    sw.listeners.push(event);
    await event.settled();

    expect(sw.self.registration.showNotification.mock.calls[0][1].actions).toBeUndefined();
  });

  it("caps at three, because a fourth is a button no phone will draw", async () => {
    const sw = loadServiceWorker(vi.fn());
    const event = pushEvent({
      title: "t",
      actions: [1, 2, 3, 4].map((n) => ({ action: `a${n}`, title: `${n}` })),
    });
    sw.listeners.push(event);
    await event.settled();

    expect(sw.self.registration.showNotification.mock.calls[0][1].actions).toHaveLength(3);
  });

  it("a plain tap reuses an open tab instead of stacking another copy of the app", async () => {
    const sw = loadServiceWorker(vi.fn());
    const client = { focus: vi.fn(() => Promise.resolve()), navigate: vi.fn() };
    sw.self.clients.matchAll = vi.fn(() => Promise.resolve([client]));

    const event = clickEvent(undefined, "/load/abc/evidence");
    sw.listeners.notificationclick(event);
    await event.settled();

    expect(client.focus).toHaveBeenCalled();
    expect(client.navigate).toHaveBeenCalledWith("/load/abc/evidence");
    expect(sw.self.clients.openWindow).not.toHaveBeenCalled();
  });

  it("a push with no deep link goes to More rather than nowhere", async () => {
    const sw = loadServiceWorker(vi.fn());
    const event = pushEvent({ title: "t" });
    sw.listeners.push(event);
    await event.settled();

    expect(sw.self.registration.showNotification.mock.calls[0][1].data).toEqual({
      deep_link: "/more",
    });
  });
});
