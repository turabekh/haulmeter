// AI-CONTEXT: the service worker's lifecycle, owned in ONE place (§23 entry 143).
//
// It used to be registered inside `push.js`'s `enable()` — so a driver who never turned
// notifications on had no worker at all, and with the shell cache that would mean the
// offline story existed only for drivers who had opted into something unrelated. It
// registers on boot now; `push.js` keeps using `getRegistration()` and is unchanged.
//
// UPDATES DO NOT APPLY THEMSELVES (owner decision). The worker no longer calls
// `skipWaiting` on install: a driver photographing a BOL at a dock must not have the
// page swapped under them mid-task. A new build installs, WAITS, and the app shows a
// quiet strip — §8's status-strip pattern, the same one offline and sync-pending use,
// which is deliberately not a notification and so spends none of §13.1's budget.
import { ref } from "vue";

// a new version is installed and waiting for the driver to say when
export const updateReady = ref(false);
let waiting = null;

function supported() {
  return typeof navigator !== "undefined" && "serviceWorker" in navigator;
}

function watch(registration) {
  // already waiting when we arrived — a build that landed while the app was closed
  if (registration.waiting) {
    waiting = registration.waiting;
    updateReady.value = true;
  }
  registration.addEventListener("updatefound", () => {
    const installing = registration.installing;
    if (!installing) return;
    installing.addEventListener("statechange", () => {
      // `controller` is null on the very first install: there is no OLD version to
      // replace, so that is not an update and must not raise a strip on first run.
      if (installing.state === "installed" && navigator.serviceWorker.controller) {
        waiting = installing;
        updateReady.value = true;
      }
    });
  });
}

export async function registerServiceWorker() {
  if (!supported()) return null;
  try {
    const registration = await navigator.serviceWorker.register("/sw.js");
    watch(registration);
    return registration;
  } catch {
    // dev serves no worker (devOptions is off, deliberately) and a private-mode browser
    // may refuse one. Neither is an error a driver should ever hear about: the app works
    // exactly as it did before service workers, which is the whole point of the pattern.
    return null;
  }
}

// AI-CONTEXT: the reload is driven by `controllerchange`, not by a timer after
// `postMessage`. The new worker has to actually take control before the page can be
// served by it, and reloading early would reload the OLD build — an update button that
// visibly does nothing, which is worse than no button.
export function applyUpdate() {
  if (!waiting) {
    updateReady.value = false;
    return;
  }
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloaded) return; // Chrome can fire this more than once
    reloaded = true;
    window.location.reload();
  });
  waiting.postMessage({ type: "SKIP_WAITING" });
  updateReady.value = false;
}

// test seam: the refs above are module state, and a suite that mounts the strip twice
// would otherwise inherit the first mount's decision.
export function __resetPwaForTests() {
  updateReady.value = false;
  waiting = null;
}
