/* AI-CONTEXT: Web Push enrolment (§13.1, §23 entry 111) — business logic in core/, per
 * §19, so the permission rules are testable without mounting a screen.
 *
 * THE TIMING DECISION, which §22 flagged and which is the whole design here.
 * §21.8 forbids dark patterns, and asking for notification permission on first launch
 * is the canonical one: the driver has seen nothing, has no idea what we would send,
 * and the browser's prompt is ONE-SHOT — a "no" is permanent for that origin and there
 * is no second ask. That single fact is why this is not a UX preference. So:
 *
 *   · Nothing is ever requested automatically. `enable()` runs only from an explicit
 *     tap on a control the driver went looking for.
 *   · The control states what will be sent before the browser prompt appears, because
 *     the prompt itself cannot say it.
 *   · Turning it off is exactly as easy as turning it on (`disable()`), and it really
 *     unsubscribes rather than just muting server-side.
 *
 * SECURE CONTEXT IS A HARD REQUIREMENT, and it is the same trap §23 entry 91 recorded
 * for the microphone: the constructors EXIST over plain http and then refuse to work.
 * `isSecureContext` is the browser's own answer, so a phone on a LAN IP is told the
 * truth — a deployment fact, not something the driver did — instead of failing opaquely.
 */
import { API_BASE, authHeaders } from "./api.js";

export function pushSupported() {
  return (
    typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    window.isSecureContext === true &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    typeof Notification !== "undefined"
  );
}

export function permissionState() {
  if (typeof Notification === "undefined") return "unsupported";
  return Notification.permission; // "default" | "granted" | "denied"
}

/* The browser wants the application server key as a Uint8Array, and the server sends
 * it base64url. Nothing clever — but a wrong conversion surfaces as an opaque
 * DOMException with no message, so it lives in one named place. */
export function urlBase64ToUint8Array(base64) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const normalized = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(normalized);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

export async function fetchPushKey() {
  const resp = await fetch(`${API_BASE}/notifications/push/key`);
  if (!resp.ok) throw new Error(`push key ${resp.status}`);
  return resp.json();
}

// AI-CONTEXT: ONE registration, owned by core/pwa.js (§23 entry 143).
//
// This used to call `navigator.serviceWorker.register` itself, and it was the ONLY
// caller — so the worker existed only for drivers who had turned notifications on. With
// an offline shell that would have made the app's ability to open without signal depend
// on an unrelated opt-in. Registration happens on boot now; enabling push adopts the
// registration that is already there, and falls back to registering if it is somehow
// absent (a browser that refused it at boot, a worker unregistered by hand).
export async function registerWorker() {
  const existing = await navigator.serviceWorker.getRegistration();
  return existing || navigator.serviceWorker.register("/sw.js");
}

function serialize(subscription) {
  const json = subscription.toJSON();
  return {
    endpoint: json.endpoint,
    p256dh: json.keys.p256dh,
    auth: json.keys.auth,
  };
}

/* Returns a REASON rather than a boolean, because §12.4 wants "what happened and what
 * to do" and the four failures need four different sentences: an insecure page is a
 * deployment fact, a denied permission cannot be re-asked from here, an unconfigured
 * server is nobody's fault, and a network error is worth retrying. */
export async function enable() {
  if (!pushSupported()) return { ok: false, reason: "unsupported" };
  let key;
  try {
    key = await fetchPushKey();
  } catch {
    return { ok: false, reason: "error" };
  }
  if (!key.enabled || !key.public_key) return { ok: false, reason: "unconfigured" };

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return { ok: false, reason: "denied" };

  try {
    const registration = await registerWorker();
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true, // the only setting Chrome accepts, and the honest one
      applicationServerKey: urlBase64ToUint8Array(key.public_key),
    });
    const resp = await fetch(`${API_BASE}/notifications/push/subscribe`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(serialize(subscription)),
    });
    if (!resp.ok) return { ok: false, reason: "error" };
    return { ok: true, reason: "enabled" };
  } catch {
    return { ok: false, reason: "error" };
  }
}

export async function disable() {
  if (!pushSupported()) return { ok: false, reason: "unsupported" };
  try {
    const registration = await navigator.serviceWorker.getRegistration();
    const subscription = registration && (await registration.pushManager.getSubscription());
    if (!subscription) return { ok: true, reason: "disabled" };
    const payload = serialize(subscription);
    // unsubscribe LOCALLY first: if the server call fails the browser must still stop
    // receiving, because a driver who turned alerts off has to actually stop hearing them
    await subscription.unsubscribe();
    await fetch(`${API_BASE}/notifications/push/unsubscribe`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(payload),
    }).catch(() => {});
    return { ok: true, reason: "disabled" };
  } catch {
    return { ok: false, reason: "error" };
  }
}

export async function isEnabled() {
  if (!pushSupported() || permissionState() !== "granted") return false;
  try {
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration) return false;
    return Boolean(await registration.pushManager.getSubscription());
  } catch {
    return false;
  }
}
