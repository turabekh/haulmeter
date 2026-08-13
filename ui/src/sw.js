/* AI-CONTEXT: the service worker that makes a P0 reach a phone in a pocket (§23 111).
 *
 * This file is the ONLY part of the product that runs when the app is closed, which is
 * the whole reason push exists: design-prd §13.1 calls background-permission survival
 * "a platform-critical asset" because the model is about reaching a driver who is NOT
 * looking. An open socket or an SSE stream reaches only an app already on screen.
 *
 * It is deliberately tiny. The header used to end "no caching, no offline shell, no
 * routing", and the reasoning behind that — a service worker updates on its own
 * schedule, so anything clever in here can be stale on a driver's phone for days — is
 * still right and is exactly why the shell cache below is GENERATED rather than written
 * (§23 entry 143). `self.__WB_MANIFEST` is a revisioned list stamped in at build time:
 * a content-hashed asset cannot go stale, because a changed file is a different URL.
 * Nothing here is hand-maintained and nothing here decides what to cache.
 *
 * THE API IS NOT CACHED, and that boundary is the load-bearing part. F12 owns response
 * caching and the offline write queue; a second cache in here would be a second answer
 * to "what did the server say", which is how two caches start disagreeing about a
 * driver's money. This file caches the SHELL — the JS, CSS and HTML needed to render at
 * all — and nothing else.
 *
 * NOT A NOTIFICATION SOURCE. Everything shown here was already decided by F8: the tier,
 * the budget, quiet hours and the class rules all ran server-side before the push was
 * sent, and every push has a matching row in the driver's inbox. This file renders and
 * routes; it never decides.
 */

import { precacheAndRoute, createHandlerBoundToURL } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";

// the build stamps the revisioned shell in here. Empty in dev, where this worker is
// deliberately not generated at all.
precacheAndRoute(self.__WB_MANIFEST || []);

// AI-CONTEXT: every in-app route resolves to the SPA shell, which is what makes a cold
// open work with no signal. `/api` is excluded because it is the API — a navigation
// there is a download or a share link, not a screen this app renders.
registerRoute(
  new NavigationRoute(createHandlerBoundToURL("/index.html"), {
    denylist: [/^\/api\//],
  }),
);

// AI-CONTEXT: NO `skipWaiting` on install any more (§23 entry 143, owner decision).
//
// It used to take over the moment it installed. For a push-only worker that was
// harmless; with a shell cache it means a driver photographing a BOL at a dock can have
// the page swapped under them mid-task. The new worker now WAITS, the app shows a quiet
// strip, and the driver decides when — so this listener exists to be asked.
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    // a push with no readable body still means "something happened" — F8 sends a
    // payload on every dispatch, so this is a corrupted delivery rather than a
    // legitimate empty one, and silence would be the worse failure
    payload = {};
  }
  const title = payload.title || "Haulmeter";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: payload.body || "",
      // §13.5: the exact screen, carried from the server so push and inbox can never
      // disagree about where a thing is
      data: { deep_link: payload.deep_link || "/more" },
      tag: payload.tag || undefined,
      // §23 entry 112: tray buttons, so answering is one tap from a locked phone
      // rather than a task. Rendered from the payload and never inferred here — a
      // vocabulary hardcoded in a service worker can be stale on a phone for days.
      actions: Array.isArray(payload.actions) ? payload.actions.slice(0, 3) : undefined,
    }),
  );
});

/* AI-CONTEXT: the session token, read from IndexedDB because a service worker cannot
 * reach localStorage (it is a synchronous API and workers have none). The app mirrors
 * it there on sign-in. This is NOT a new exposure: the same token already sits in
 * localStorage on the same origin, so the threat model is unchanged — what changes is
 * that a tap answered from the lock screen can be sent without opening the app, which
 * is the whole difference between a confirmation and a chore. */
/* AI-CONTEXT: the version and the store list are duplicated from `core/idb.js` ON
 * PURPOSE, and the duplication is load-bearing rather than sloppy.
 *
 * This file cannot import it: `tray-answer.test.js` runs this source through
 * `new Function` with every `import` line compiled away, so an imported constant would
 * be `undefined` exactly where the token is read. What it MUST do is agree — the app
 * opens `haulmeter` at v2 for the queued-image blob store, and `open(name, 1)` against a
 * v2 database fails with VersionError. Left at 1, `readToken` would resolve null for
 * every driver and every tray tap would fall back to opening the app, which looks like
 * the deliberate fallback it is not. If `core/idb.js` bumps again, bump here too. */
function readToken() {
  return new Promise((resolve) => {
    let req;
    try {
      req = indexedDB.open("haulmeter", 2);
    } catch {
      resolve(null);
      return;
    }
    req.onupgradeneeded = () => {
      for (const name of ["kv", "blobs"]) {
        try {
          req.result.createObjectStore(name);
        } catch {
          /* already there */
        }
      }
    };
    req.onerror = () => resolve(null);
    req.onsuccess = () => {
      try {
        const store = req.result.transaction("kv", "readonly").objectStore("kv");
        const get = store.get("token");
        get.onsuccess = () => resolve(get.result || null);
        get.onerror = () => resolve(null);
      } catch {
        resolve(null);
      }
    };
  });
}

const LOT_STATUS = { "lot:empty": "empty", "lot:some": "some", "lot:full": "full" };

/* Answering from the tray posts the report directly. If it cannot — no token, no
 * network — the driver is NOT left thinking they answered: the app is opened at the
 * facility, where the same question is a chip they can still tap. Silence would be the
 * §11.7 lie of a report that was accepted and discarded. */
async function reportLotStatus(action, deepLink) {
  const status = LOT_STATUS[action];
  const facilityId = (deepLink || "").split("/facility/")[1];
  const token = await readToken();
  if (!status || !facilityId || !token) return false;
  try {
    const resp = await fetch("/api/map/report", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        facility_id: facilityId,
        signal_type: "parking_fullness",
        value: { status },
      }),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.deep_link) || "/more";

  if (event.action && event.action.startsWith("lot:")) {
    event.waitUntil(
      reportLotStatus(event.action, target).then((ok) => {
        if (ok) return undefined; // answered from the lock screen; nothing to open
        return self.clients.openWindow(target);
      }),
    );
    return;
  }
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      // reuse an open tab rather than stacking another: a driver who taps three alerts
      // should end on three screens in one app, not three copies of the app
      for (const client of windows) {
        if ("focus" in client && "navigate" in client) {
          return client.focus().then(() => client.navigate(target));
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
