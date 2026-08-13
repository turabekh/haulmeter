/* AI-CONTEXT: the app side's only IndexedDB opener, and it exists because of a version
 * collision that would have broken something invisible.
 *
 * `haulmeter` v1 held one store, `kv`, carrying the session token that `sw.js` reads so a
 * tray tap can be answered without opening the app (§23 entry 111). Queued image bytes
 * cannot go where the rest of the write queue goes: `localStorage` is SYNCHRONOUS and
 * capped near 5 MB per origin, and one camera JPEG exceeds that by itself — so
 * `saveQueue`'s `catch {}` swallowed QuotaExceededError while `pendingWrites` still
 * counted the write, and the driver's evidence was gone on the next reload. Bytes belong
 * in IndexedDB: asynchronous, orders of magnitude larger, and it stores Blobs directly
 * so nothing has to become a base64 string to be persisted.
 *
 * A second store means version 2, and THAT is the trap: `indexedDB.open(name, 1)` against
 * a v2 database fails with VersionError. Every opener has to agree on the version or the
 * one left behind stops working — and the one left behind would have been `sw.js`, where
 * the failure is silent by design, because a tray tap that cannot read a token falls back
 * to opening the app and looks like a deliberate fallback rather than a defect.
 *
 * `sw.js` therefore carries the same bump INLINE rather than importing this file. It
 * cannot import it: `tray-answer.test.js` runs the worker source through `new Function`
 * with its import lines compiled away, so an imported helper would be `undefined` there.
 * The duplication is two names and an integer, and it is deliberate.
 */

export const DB_NAME = "haulmeter";
export const DB_VERSION = 2;
export const KV_STORE = "kv";
export const BLOB_STORE = "blobs";

// created idempotently: a phone upgrading from v1 already has `kv`, and a fresh install
// has neither. `createObjectStore` throwing on an existing name is the cheapest check.
export function upgradeSchema(db) {
  for (const name of [KV_STORE, BLOB_STORE]) {
    try {
      db.createObjectStore(name);
    } catch {
      /* already there */
    }
  }
}

/* AI-CONTEXT: the PROMISE is memoised, not the resolved handle, and both halves of that
 * matter.
 *
 * Caching the handle meant a burst of writes — a six-shot condition capture is exactly
 * that — each started its own `open` before any of them finished, so the database was
 * opened six times to answer six puts. And it left a race with its own reset: clearing
 * the handle did nothing to an open already in flight, which would then assign itself
 * over the top afterwards. That is not only a test artefact; a logout racing a queued
 * write would repopulate the handle for a session that had ended. */
let _dbPromise = null;

export function openDb() {
  if (typeof indexedDB === "undefined") return Promise.resolve(null);
  if (_dbPromise) return _dbPromise;
  _dbPromise = new Promise((resolve) => {
    let req;
    try {
      req = indexedDB.open(DB_NAME, DB_VERSION);
    } catch {
      resolve(null);
      return;
    }
    req.onupgradeneeded = () => upgradeSchema(req.result);
    req.onerror = () => resolve(null);
    // another tab holding v1 open blocks the upgrade. Degrading to null is right:
    // the caller keeps the capture rather than losing it, and the next open succeeds
    // once that tab goes away.
    req.onblocked = () => resolve(null);
    req.onsuccess = () => resolve(req.result);
  });
  // a failed open must not be remembered as "this browser has no IndexedDB" forever —
  // a blocked upgrade clears the moment the other tab closes.
  return _dbPromise.then((db) => {
    if (!db) _dbPromise = null;
    return db;
  });
}

/* AI-CONTEXT: `ok` and `value` are separate, and conflating them was a real defect.
 *
 * A successful `put` and `delete` both leave `req.result` undefined, and so does a `get`
 * for a key that is not there. Collapsing "the operation worked" into "what came back"
 * therefore made a MISSING BLOB indistinguishable from a stored one — every replay would
 * have rebuilt a photograph from a sentinel and dead-lettered the driver's evidence.
 * Caught by the tests in `image-queue.test.js`, not by reading it back. */
function request(store, mode, run) {
  return openDb().then(
    (db) =>
      new Promise((resolve) => {
        if (!db) {
          resolve({ ok: false, value: undefined });
          return;
        }
        try {
          const req = run(db.transaction(store, mode).objectStore(store));
          req.onsuccess = () => resolve({ ok: true, value: req.result });
          req.onerror = () => resolve({ ok: false, value: undefined });
        } catch {
          resolve({ ok: false, value: undefined });
        }
      }),
  );
}

// AI-CONTEXT: every one of these resolves rather than rejects. A caller storing a
// driver's photograph must be able to tell "stored" from "not stored" and act on it —
// an exception thrown into a `catch` that already means "offline" would be read as a
// dead zone and the capture would be silently dropped, which is the defect this file
// was written to remove.
export function idbPut(store, key, value) {
  return request(store, "readwrite", (s) => s.put(value, key)).then((r) => r.ok);
}

// resolves `undefined` for a key that is not there, which is the whole point of the
// split above — a caller must be able to tell "no such photograph" from "here it is".
export function idbGet(store, key) {
  return request(store, "readonly", (s) => s.get(key)).then((r) => (r.ok ? r.value : undefined));
}

export function idbDelete(store, key) {
  return request(store, "readwrite", (s) => s.delete(key)).then((r) => r.ok);
}

export function idbKeys(store) {
  return request(store, "readonly", (s) => s.getAllKeys()).then((r) => r.value || []);
}

// matches the `__…ForTests` convention in state.js, location.js and map-view.js: the
// cached handle outlives a `fake-indexeddb` reset, so a suite that swaps the factory
// would keep talking to the old database.
export function __resetIdbForTests() {
  _dbPromise = null;
}
