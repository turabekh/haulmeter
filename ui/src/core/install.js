// AI-CONTEXT: installing the app, owned in ONE place the way `pwa.js` owns the worker.
//
// Entry 143 made the app installable — a real manifest, both icon sizes, a maskable one,
// a service worker with a fetch handler. Measured in Chromium over CDP afterwards:
// `Page.getInstallabilityErrors` returns []. The app satisfies every rule a browser
// judges, and NOTHING IN IT HAS EVER ASKED. `beforeinstallprompt` appeared nowhere in
// this codebase.
//
// That event is the browser handing the app the right to raise the install dialog, and
// then waiting. With no handler the browser keeps a passive affordance only — a menu
// entry on Android, an omnibox icon on desktop — which is not a thing a driver finds.
// So the app was installable and uninstalled, which is entry 122's shape exactly: built,
// correct, verified, and reached by nothing.
//
// AND iOS CANNOT BE PROMPTED AT ALL. Safari never fires this event and has no install
// UI; Share → Add to Home Screen is the only path that exists and it has to be taught.
// index.html has said since entry 111 that "iOS requires an INSTALLED PWA for push at
// all", so on iPhone this module is the difference between Web Push being reachable and
// being a sentence in a comment.
import { ref, computed } from "vue";

// the browser handed us a prompt: this is the ONLY proof the app is installable here,
// and it is why nothing below ever guesses
export const canInstall = ref(false);
// iOS, where no prompt can exist and the gesture must be shown instead
export const manualInstall = ref(false);

const DISMISS_KEY = "longhaul.install_dismissed";
let deferred = null;
// AI-CONTEXT: kept so the test seam can actually UNDO `initInstall`. A reset that left
// these attached made "wires nothing when already installed" pass against listeners a
// previous test had bound — the check would have gone green over the opposite of what
// it claims, which is the failure mode this repo keeps finding in its own suites.
let bound = [];

function bind(type, fn) {
  window.addEventListener(type, fn);
  bound.push([type, fn]);
}

function dismissed() {
  try {
    return localStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}
const wasDismissed = ref(dismissed());

// AI-CONTEXT: already installed is the one state that must silence everything.
// `display-mode: standalone` covers Android and desktop; `navigator.standalone` is the
// iOS-only flag, and iOS is the platform that needs this module most. Offering to
// install an installed app is the app being wrong about the driver's own phone.
export function isStandalone() {
  if (typeof window === "undefined") return false;
  try {
    if (window.matchMedia?.("(display-mode: standalone)").matches) return true;
    if (window.matchMedia?.("(display-mode: window-controls-overlay)").matches) return true;
  } catch {
    /* matchMedia is absent in some embedded webviews */
  }
  return typeof navigator !== "undefined" && navigator.standalone === true;
}

// AI-CONTEXT: iPadOS reports itself as a Mac and is caught only by the touch-point
// count. A missed iPad is an iPad that can never be told how to install, and the false
// positive it risks — a touchscreen Mac — is a sheet explaining a Share menu, which is
// recoverable. The asymmetry is deliberate.
function isIos() {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent || "";
  if (/iphone|ipad|ipod/i.test(ua)) return true;
  return navigator.platform === "MacIntel" && (navigator.maxTouchPoints || 0) > 1;
}

// the strip asks; the More card does NOT consult this. Dismissing silences the
// interruption, it does not remove the ability — §15.5's "never nags beyond that card"
// with the card kept somewhere the driver can go back to.
export const offerInstall = computed(
  () => (canInstall.value || manualInstall.value) && !wasDismissed.value,
);
// the More card's gate: something this app can actually do about installing. A button
// that cannot install is the dead mic the strip was cleared of in entry 89.
export const installable = computed(() => canInstall.value || manualInstall.value);

export function dismissInstall() {
  wasDismissed.value = true;
  try {
    localStorage.setItem(DISMISS_KEY, "1");
  } catch {
    /* private mode — the choice holds for this session */
  }
}

// AI-CONTEXT: the prompt is single-use. Chrome invalidates the event once `prompt()` is
// called, so it is cleared here rather than kept for a second tap that would silently do
// nothing. A driver who declines the browser's own dialog sees the row go quiet for this
// session; the browser fires the event again on a later visit, which is its decision to
// make and not ours to override.
export async function promptInstall() {
  if (!deferred) return "unavailable";
  const evt = deferred;
  deferred = null;
  canInstall.value = false;
  try {
    evt.prompt();
    const choice = await evt.userChoice;
    return choice?.outcome || "dismissed";
  } catch {
    return "dismissed";
  }
}

// AI-CONTEXT: called from main.js at boot, NOT from a component's onMounted.
// `beforeinstallprompt` fires once, early, and a listener attached after it has fired
// never hears it — the app would be installable and silent, which is the defect this
// module exists to end.
export function initInstall() {
  if (typeof window === "undefined") return;
  if (isStandalone()) return; // already installed: nothing to offer, on any platform

  bind("beforeinstallprompt", (event) => {
    // without this the browser may show its own affordance AND ours; preventing it makes
    // the app the single place the offer comes from
    event.preventDefault();
    deferred = event;
    canInstall.value = true;
  });

  bind("appinstalled", () => {
    deferred = null;
    canInstall.value = false;
    manualInstall.value = false;
  });

  // iOS gets no event, ever. This is a platform fact, not a capability check, which is
  // why it is the one branch here that is inferred rather than observed.
  if (isIos()) manualInstall.value = true;
}

// test seam: the refs above are module state and a suite that mounts the strip twice
// would otherwise inherit the first mount's decision (`pwa.js` has the same seam).
export function __resetInstallForTests() {
  for (const [type, fn] of bound) window.removeEventListener(type, fn);
  bound = [];
  canInstall.value = false;
  manualInstall.value = false;
  wasDismissed.value = false;
  deferred = null;
}

export function __setDeferredForTests(evt) {
  deferred = evt;
  canInstall.value = !!evt;
}
