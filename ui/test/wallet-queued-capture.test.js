// AI-CONTEXT: the BOL photographed in a dead zone had to appear SOMEWHERE, and the
// wallet was the one screen certain not to show it.
//
// §15.1 has said "queued items show a subtle pending glyph" since it was written, and
// entry 144 built that for `ConditionSurface` — where a queued shot is rendered from the
// local file immediately. The wallet was left on the other side of the same argument:
// `onCaptured` calls `refresh()`, which reads the SERVER. Offline there is nothing new
// there to read, so the list came back exactly as it was. The capture sheet said "Saved
// on your phone. Syncs when you have signal", the sheet closed, and the driver was
// returned to a wallet with no trace of the document in it.
//
// That is the shape entry 144 named: the only sync signal in the product is a global
// count on the status strip, so the evidence of a document's existence was a number that
// says "1" for any queued write in the app. A driver at a dock cannot tell from it
// whether the thing they photographed is the thing being counted.
//
// The document EXISTS — it is on the phone, in IndexedDB, with a stable idempotency key.
// Rendering it is a true statement about a local fact (entry 144's own test), and the
// glyph carries the only part still uncertain: whether the server has it yet.
import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import DocsSurface from "../src/surfaces/DocsSurface.vue";
import { setToken, logout, captureDocument, pendingWrites } from "../src/core/api.js";
import { __resetIdbForTests } from "../src/core/idb.js";
import en from "../src/core/i18n/en.json";

const EMPTY_WALLET = {
  documents: [],
  expiring: [],
  archived_count: 0,
  load_paperwork: [],
  unattached: [],
};

// the wallet a driver had BEFORE they photographed anything — which offline is also the
// wallet they have after, because the server is the only thing `refresh()` asks.
function walletServer(wallet = EMPTY_WALLET) {
  return vi.fn((url) => {
    if (String(url).includes("/protection/documents/archived")) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ documents: [] }) });
    }
    if (String(url).includes("/protection/wallet")) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(wallet) });
    }
    // the capture itself: a dead zone, which is the whole premise
    if (String(url).includes("/protection/documents")) return Promise.reject(new Error("network"));
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  });
}

function frame(name = "bol.jpg") {
  const buf = new Uint8Array(2048);
  for (let i = 0; i < buf.length; i += 1) buf[i] = (i * 17 + 3) % 251;
  return new File([buf], name, { type: "image/jpeg" });
}

async function mountWallet() {
  const w = mount(DocsSurface, {
    global: { stubs: { RouterLink: true }, mocks: { $route: { query: {} } } },
  });
  await flushPromises();
  return w;
}

describe("the wallet shows a capture that has not left the phone (§15.1)", () => {
  beforeEach(async () => {
    localStorage.clear();
    global.indexedDB = new IDBFactory();
    __resetIdbForTests();
    setToken("t-wallet");
  });

  afterEach(() => {
    logout();
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("renders the queued document as a row", async () => {
    global.fetch = walletServer();

    const res = await captureDocument({ docType: "bol", file: frame(), filename: "bol.jpg" });
    expect(res.queued).toBe(true);
    expect(pendingWrites.value).toBe(1);

    const w = await mountWallet();

    expect(w.text()).toContain(en["docs.type.bol"]);
    w.unmount();
  });

  it("marks it pending rather than presenting it as filed", async () => {
    // the honest half. A row with no glyph would claim the broker's copy exists.
    global.fetch = walletServer();
    await captureDocument({ docType: "bol", file: frame(), filename: "bol.jpg" });

    const w = await mountWallet();

    expect(w.find(".queued__glyph").exists()).toBe(true);
    expect(w.find(".queued__glyph").attributes("title")).toBe(en["docs.cap_queued"]);
    w.unmount();
  });

  it("does not offer to open a document the server has never seen", async () => {
    // AI-CONTEXT: the row is NOT a button. `open()` fetches bytes by document id, and a
    // queued capture has no id — only an idempotency key. Tapping it could only fail,
    // and failing on the screen that says the document is safe is worse than not
    // offering the tap.
    global.fetch = walletServer();
    await captureDocument({ docType: "bol", file: frame(), filename: "bol.jpg" });

    const w = await mountWallet();

    const row = w.find(".queued__row");
    expect(row.exists()).toBe(true);
    expect(row.element.tagName).not.toBe("BUTTON");
    expect(row.find("button").exists()).toBe(false);
    w.unmount();
  });

  it("still shows it when the wallet itself could not be fetched", async () => {
    /* AI-CONTEXT: THE STATE THIS IS ACTUALLY FOR, and the first build of it got this
     * wrong — the row sat inside the LOADED branch, so it rendered in every case except
     * the one it exists to serve.
     *
     * A driver in a dead zone does not get a wallet: `fetchWallet` fails, §15.4's line
     * takes the screen, and the four-state chain has no room for anything else. The
     * queued capture is the ONE thing on that screen that is not in doubt — it is on the
     * phone — so it belongs outside the chain entirely, exactly as the capture chip below
     * it already is ("a driver can photograph a document whether or not the wallet
     * fetched"). Found by the layout harness, which could not render the state either. */
    global.fetch = vi.fn(() => Promise.reject(new Error("network")));

    await captureDocument({ docType: "bol", file: frame(), filename: "bol.jpg" });
    const w = await mountWallet();

    expect(w.find(".docs__failed").exists(), "the wallet failed, as it must offline").toBe(true);
    expect(w.find(".queued__row").exists(), "and the capture is still on the screen").toBe(true);
    expect(w.text()).toContain(en["docs.type.bol"]);
    w.unmount();
  });

  it("shows nothing extra once the document is on the server", async () => {
    // §15.1: "sync completion is silent". The queued row is not a notification with a
    // life of its own — it is the absence of the real row, and it ends when that arrives.
    global.fetch = walletServer({
      ...EMPTY_WALLET,
      documents: [
        { id: "d-1", doc_type: "bol", expires_on: null, status: "ok", content_type: "image/jpeg" },
      ],
    });

    const w = await mountWallet();

    expect(w.find(".queued__glyph").exists()).toBe(false);
    expect(w.find(".queued__row").exists()).toBe(false);
    w.unmount();
  });

  it("counts only DOCUMENT captures, not every queued write in the app", async () => {
    /* AI-CONTEXT: this is why the row is keyed on the queue ENTRY'S PATH rather than on
     * `pendingWrites`. That count is global — a queued condition photo, incident or lot
     * report all increment it — and a wallet that grew a phantom document row every time
     * a driver reported a closed truck stop would be worse than the silence it replaces.
     *
     * THE FIRST VERSION OF THIS TEST PROVED NOTHING. Its three fixtures were writes with
     * no `doc_type` in them, so deleting the path filter entirely left it green — the
     * OTHER filter was carrying it. Both entries below now defeat exactly one filter:
     * the archive is a real queued write whose path shares this one's PREFIX (so it
     * catches a `startsWith`), and the portal upload carries a real `doc_type` on a
     * different path. */
    global.fetch = walletServer();
    const { queueForTests } = await import("../src/core/api.js");
    queueForTests([
      { path: "/protection/documents/d-1/archive", body: { doc_type: "cdl" }, opId: "op-arch" },
      { path: "/fleet/documents", body: { doc_type: "insurance" }, opId: "op-fleet" },
    ]);

    const w = await mountWallet();

    expect(w.findAll(".queued__row").length).toBe(0);
    w.unmount();
  });

  it("skips a queue entry it cannot label rather than throwing", async () => {
    // AI-CONTEXT: a queue written by an older build carries no `body.doc_type`, and this
    // queue OUTLIVES a deploy — it is localStorage on a driver's phone, replayed by
    // whatever version happens to load next. A row with no label helps nobody, and
    // throwing here empties the entire screen, so it is skipped and the wallet renders.
    global.fetch = walletServer();
    const { queueForTests } = await import("../src/core/api.js");
    queueForTests([{ path: "/protection/documents", opId: "op-old" }]);

    const w = await mountWallet();

    expect(w.findAll(".queued__row").length).toBe(0);
    expect(w.text()).toContain(en["docs.empty"]);
    w.unmount();
  });
});
