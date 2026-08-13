// AI-CONTEXT: a driver's photograph must never ride in localStorage, and the reason is
// measurable rather than stylistic.
//
// `saveQueue` writes the WHOLE write-queue as one JSON string, synchronously, and
// localStorage is capped near 5 MB per origin. A base64 camera frame is 5–11 MB, so
// `setItem` threw QuotaExceededError, the `catch {}` swallowed it, and `pendingWrites`
// was incremented anyway — the status strip read "1 pending" for a photograph that had
// been written nowhere, and it was gone on the next reload with nothing recording that
// it had ever existed. That is U-07's shape (evidence lost while the UI reports success)
// reproduced in the half of the queue U-07 did not touch.
//
// So the bytes go to IndexedDB — as an ArrayBuffer plus its type, not as a Blob, because
// Safari has returned Blobs from IDB with their bytes detached — and only a pointer goes
// in the queue. These tests assert the three things that makes true: the bytes are NOT in
// localStorage, a replay puts them back on the wire, and every way it can fail is said
// out loud instead of being counted as pending.
import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  setToken,
  logout,
  flushQueue,
  captureDocument,
  addConditionPhoto,
  pendingWrites,
  failedWrites,
  listFailedWrites,
  clearFailedWrites,
  sweepOrphanedBlobs,
  CAPTURE_NOT_STORED,
} from "../src/core/api.js";
import { __resetIdbForTests, idbGet, idbKeys, idbPut, BLOB_STORE, DB_VERSION } from "../src/core/idb.js";

const QUEUE_KEY = "longhaul.write_queue";

function readQueue() {
  return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
}

// a stand-in for a camera frame. 600 KB of non-repeating bytes: above the re-encode
// floor, and large enough that finding it inside localStorage is unambiguous.
function cameraFrame(bytes = 600 * 1024) {
  const buf = new Uint8Array(bytes);
  for (let i = 0; i < bytes; i += 1) buf[i] = (i * 31 + 7) % 251;
  return new File([buf], "bol.jpg", { type: "image/jpeg" });
}

const deadZone = () => vi.fn(() => Promise.reject(new Error("network")));
const accepts = () =>
  vi.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }));

// AI-CONTEXT: the upload is multipart — the photograph travels as BYTES beside a
// `fields` JSON part, rather than as base64 inside the JSON. These helpers read the two
// halves back, and `sentBytes` is what proves the pixels actually left: asserting only
// on the fields would go green over a request carrying no file at all.
function sentFields(call) {
  const body = call[1].body;
  return JSON.parse(body instanceof FormData ? body.get("fields") : body);
}

function sentBytes(call) {
  const body = call[1].body;
  if (!(body instanceof FormData)) return null;
  return body.get("file");
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory();
  __resetIdbForTests();
  localStorage.clear();
  setToken("tok");
});

afterEach(() => {
  logout();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("a photograph queued in a dead zone", () => {
  it("puts the BYTES in IndexedDB and only a pointer in localStorage", async () => {
    vi.stubGlobal("fetch", deadZone());

    const res = await captureDocument({ docType: "bol", file: cameraFrame() });

    expect(res).toEqual({ queued: true });
    const [item] = readQueue();
    expect(item.blob?.key, "the queue row must name where the bytes went").toBeTruthy();
    expect(item.body.content_b64, "and must not carry them itself").toBeNull();

    // the assertion that is the whole point: the frame is not in localStorage at all.
    // Serialised there it would be ~800 KB of base64 against a ~5 MB cap shared with
    // the session, the response cache and the active stop.
    expect(localStorage.getItem(QUEUE_KEY).length).toBeLessThan(2000);

    // stored as an ArrayBuffer + type rather than as a Blob: Safari has returned Blobs
    // from IDB with their bytes detached, and that failure is silent.
    const stored = await idbGet(BLOB_STORE, item.blob.key);
    expect(stored, "the bytes are retrievable").toBeTruthy();
    expect(stored.buf.byteLength, "and they are the whole photograph").toBeGreaterThan(500 * 1024);
    expect(stored.type).toBe("image/jpeg");
  });

  it("replays the bytes back onto the wire and then releases them", async () => {
    vi.stubGlobal("fetch", deadZone());
    await captureDocument({ docType: "bol", file: cameraFrame() });
    const [{ blob }] = readQueue();

    const fetchMock = accepts();
    vi.stubGlobal("fetch", fetchMock);
    await flushQueue();

    expect(pendingWrites.value).toBe(0);
    const bytes = sentBytes(fetchMock.mock.calls[0]);
    expect(bytes, "the replay must carry the photograph, as bytes").toBeTruthy();
    expect(bytes.size, "and all of it").toBeGreaterThan(500 * 1024);
    // base64 is gone from the wire: the field is present and empty, not carrying a
    // second copy of the same photograph at +33%
    expect(sentFields(fetchMock.mock.calls[0]).content_b64).toBeNull();

    // the server has them now; keeping a second copy on the phone is how a device
    // fills up with photographs of things already filed
    expect(await idbGet(BLOB_STORE, blob.key)).toBeFalsy();
  });

  it("sends the photograph straight through when there IS signal, storing nothing", async () => {
    const fetchMock = accepts();
    vi.stubGlobal("fetch", fetchMock);

    await addConditionPhoto("cap-1", "trailer", cameraFrame());

    expect(readQueue()).toHaveLength(0);
    expect(await idbKeys(BLOB_STORE)).toHaveLength(0);
    expect(sentBytes(fetchMock.mock.calls[0]).size).toBeGreaterThan(500 * 1024);
  });
});

describe("when the bytes cannot be stored, the driver is told", () => {
  it("dead-letters rather than reporting a capture that went nowhere as queued", async () => {
    vi.stubGlobal("fetch", deadZone());
    // a device that will not accept the write at all — full, private mode, blocked
    // upgrade. The old code path counted this as pending and lost the photograph.
    const broken = new IDBFactory();
    broken.open = () => {
      throw new Error("no storage");
    };
    globalThis.indexedDB = broken;
    __resetIdbForTests();

    await expect(captureDocument({ docType: "bol", file: cameraFrame() })).rejects.toThrow(
      CAPTURE_NOT_STORED,
    );

    expect(pendingWrites.value, "it must NOT be counted as waiting to sync").toBe(0);
    expect(failedWrites.value, "it must be somewhere the driver can be told about").toBe(1);
    expect(listFailedWrites()[0].reason).toBe(CAPTURE_NOT_STORED);
  });

  it("dead-letters a replay whose bytes have gone, instead of filing an empty record", async () => {
    vi.stubGlobal("fetch", deadZone());
    await captureDocument({ docType: "bol", file: cameraFrame() });
    const [{ blob }] = readQueue();

    // the browser evicted the blob store, or a logout swept it: the row survives and
    // the photograph does not. Sending it anyway would file a BOL containing no BOL.
    const fresh = new IDBFactory();
    globalThis.indexedDB = fresh;
    __resetIdbForTests();
    expect(await idbGet(BLOB_STORE, blob.key)).toBeFalsy();

    const fetchMock = accepts();
    vi.stubGlobal("fetch", fetchMock);
    await flushQueue();

    expect(fetchMock, "nothing may be sent for a capture with no bytes").not.toHaveBeenCalled();
    expect(pendingWrites.value).toBe(0);
    expect(failedWrites.value).toBe(1);
  });
});

describe("the bytes are collected, but never out from under a live row", () => {
  it("keeps a dead letter's photograph so it stays replayable, and drops it on clear", async () => {
    vi.stubGlobal("fetch", deadZone());
    await captureDocument({ docType: "bol", file: cameraFrame() });
    const [{ blob }] = readQueue();

    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, status: 422, json: () => ({}) })),
    );
    await flushQueue();

    expect(failedWrites.value).toBe(1);
    // the dead letter is kept WHOLE for a future retry surface, and a retry with no
    // photograph is not a retry
    expect(await idbGet(BLOB_STORE, blob.key), "the bytes survive the failure").toBeTruthy();

    await clearFailedWrites();
    expect(await idbGet(BLOB_STORE, blob.key), "and go when the driver discards it").toBeFalsy();
  });

  it("sweeps orphans and leaves everything a queue row or a dead letter still names", async () => {
    vi.stubGlobal("fetch", deadZone());
    await captureDocument({ docType: "bol", file: cameraFrame() });
    const [{ blob }] = readQueue();

    await idbPut(BLOB_STORE, "orphan-1", new Blob(["x"]));
    await idbPut(BLOB_STORE, "orphan-2", new Blob(["y"]));

    const removed = await sweepOrphanedBlobs();

    expect(removed).toBe(2);
    expect(await idbGet(BLOB_STORE, blob.key), "the queued capture is untouched").toBeTruthy();
  });
});

describe("the IndexedDB version the service worker opens", () => {
  // AI-CONTEXT: this is the trap the blob store created, and it fails SILENTLY.
  // `indexedDB.open(name, 1)` against a v2 database rejects with VersionError, so a
  // sw.js left at v1 resolves no token, every tray tap falls back to opening the app,
  // and that fallback is deliberate elsewhere — it looks like the feature working.
  it("matches core/idb.js, or every tray tap silently stops answering", () => {
    const swSource = readFileSync(resolve(process.cwd(), "src/sw.js"), "utf8");
    const match = swSource.match(/indexedDB\.open\(\s*"haulmeter"\s*,\s*(\d+)\s*\)/);

    expect(match, "sw.js must still open the database by name and version").toBeTruthy();
    expect(Number(match[1])).toBe(DB_VERSION);
  });

  it("creates the blob store too, so an upgrade driven by the worker is complete", () => {
    const swSource = readFileSync(resolve(process.cwd(), "src/sw.js"), "utf8");
    // whichever opener wins the upgrade race has to build BOTH stores: if the worker
    // upgrades first and makes only `kv`, the app's blob writes fail forever after.
    expect(swSource).toMatch(/createObjectStore/);
    expect(swSource).toContain("blobs");
    expect(swSource).toContain("kv");
  });
});
