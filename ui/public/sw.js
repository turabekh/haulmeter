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
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.deep_link) || "/more";
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
