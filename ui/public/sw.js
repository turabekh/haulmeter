/* AI-CONTEXT: the service worker that makes a P0 reach a phone in a pocket (§23 111).
 *
 * This file is the ONLY part of the product that runs when the app is closed, which is
 * the whole reason push exists: design-prd §13.1 calls background-permission survival
 * "a platform-critical asset" because the model is about reaching a driver who is NOT
 * looking. An open socket or an SSE stream reaches only an app already on screen.
 *
 * It is deliberately tiny and has no build step. A service worker is cached by the
 * browser and updated on its own schedule, so anything clever in here is a thing that
 * can be stale on a driver's phone for days. No caching, no offline shell, no routing —
 * F12's offline story is the app's, not this file's.
 *
 * NOT A NOTIFICATION SOURCE. Everything shown here was already decided by F8: the tier,
 * the budget, quiet hours and the class rules all ran server-side before the push was
 * sent, and every push has a matching row in the driver's inbox. This file renders and
 * routes; it never decides.
 */

self.addEventListener("install", () => self.skipWaiting());
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
function readToken() {
  return new Promise((resolve) => {
    let req;
    try {
      req = indexedDB.open("haulmeter", 1);
    } catch {
      resolve(null);
      return;
    }
    req.onupgradeneeded = () => {
      try {
        req.result.createObjectStore("kv");
      } catch {
        /* already there */
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
