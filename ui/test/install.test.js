// AI-CONTEXT: the app asking to be installed (§23 entry 152).
//
// THE APP HAS BEEN INSTALLABLE AND SILENT SINCE ENTRY 143. That entry fixed a manifest
// that shipped with `"icons": []`, and `pwa.test.js` beside this file asserts every rule
// a browser judges installability on. All of them pass. Measured afterwards in real
// Chromium over CDP: `Page.getInstallabilityErrors` returns []. And `beforeinstallprompt`
// — the event a browser fires to hand the app the right to raise the install dialog —
// appeared NOWHERE in this codebase, so the browser fired it, waited, and fell back to a
// passive menu entry no driver goes looking for.
//
// That is entry 122's shape exactly: built, correct, verified, reached by nothing. These
// tests are about the reaching.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount } from "@vue/test-utils";
import StatusStrip from "../src/core/components/StatusStrip.vue";
import { updateReady, __resetPwaForTests } from "../src/core/pwa.js";
import {
  canInstall,
  manualInstall,
  installable,
  offerInstall,
  isStandalone,
  initInstall,
  promptInstall,
  dismissInstall,
  __resetInstallForTests,
  __setDeferredForTests,
} from "../src/core/install.js";
import en from "../src/core/i18n/en.json";

// a `beforeinstallprompt` as the browser delivers it: an event carrying the two members
// that make it usable, and cancelable so `preventDefault` means something
function bipEvent(outcome = "accepted") {
  const evt = new Event("beforeinstallprompt", { cancelable: true });
  evt.prompt = vi.fn(() => Promise.resolve());
  evt.userChoice = Promise.resolve({ outcome });
  return evt;
}

beforeEach(() => {
  __resetInstallForTests();
  __resetPwaForTests();
  localStorage.clear();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("The browser's offer is captured rather than dropped", () => {
  it("offers nothing until the browser says the app is installable", () => {
    // the ONLY proof installability exists on this device is the event. Nothing here
    // ever infers it from a user agent, which is how an app ends up offering an install
    // that cannot happen.
    expect(canInstall.value).toBe(false);
    expect(offerInstall.value).toBe(false);
  });

  it("captures beforeinstallprompt and claims the right to ask", () => {
    initInstall();
    const evt = bipEvent();
    window.dispatchEvent(evt);

    expect(canInstall.value).toBe(true);
    expect(offerInstall.value).toBe(true);
    // preventing the browser's own affordance makes the app the single place the offer
    // comes from, rather than two offers for one thing
    expect(evt.defaultPrevented).toBe(true);
  });

  it("prompts with the event the browser handed over", async () => {
    const evt = bipEvent("accepted");
    __setDeferredForTests(evt);

    await expect(promptInstall()).resolves.toBe("accepted");
    expect(evt.prompt).toHaveBeenCalledTimes(1);
  });

  it("never re-uses a spent prompt", async () => {
    // Chrome invalidates the event once `prompt()` is called. Keeping it for a second
    // tap would leave a control that silently does nothing — the thing entry 89 cleared
    // this strip of.
    __setDeferredForTests(bipEvent());
    await promptInstall();

    expect(canInstall.value).toBe(false);
    await expect(promptInstall()).resolves.toBe("unavailable");
  });

  it("reports a declined prompt without pretending it was accepted", async () => {
    __setDeferredForTests(bipEvent("dismissed"));
    await expect(promptInstall()).resolves.toBe("dismissed");
  });

  it("stops offering once the app is installed", () => {
    initInstall();
    window.dispatchEvent(bipEvent());
    expect(offerInstall.value).toBe(true);

    window.dispatchEvent(new Event("appinstalled"));
    expect(canInstall.value).toBe(false);
    expect(manualInstall.value).toBe(false);
    expect(offerInstall.value).toBe(false);
  });
});

describe("An installed app is never asked to install", () => {
  it("recognises a standalone window", () => {
    vi.stubGlobal("matchMedia", (q) => ({ matches: q.includes("standalone") }));
    expect(isStandalone()).toBe(true);
  });

  it("recognises iOS's own standalone flag, which is not a media query", () => {
    // the platform that needs this module most is the one that reports it differently
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    vi.stubGlobal("navigator", { standalone: true, userAgent: "iPhone" });
    expect(isStandalone()).toBe(true);
  });

  it("wires nothing at all when already installed", () => {
    vi.stubGlobal("matchMedia", (q) => ({ matches: q.includes("standalone") }));
    const spy = vi.spyOn(window, "addEventListener");
    initInstall();

    expect(spy).not.toHaveBeenCalled();
    // and the event, were it somehow to arrive, has nobody listening
    window.dispatchEvent(bipEvent());
    expect(offerInstall.value).toBe(false);
  });
});

describe("iOS, where no prompt can exist", () => {
  it("offers the manual path with no event, because none will ever come", () => {
    // Safari fires no `beforeinstallprompt` and exposes no install API. Waiting for an
    // event here would mean iPhone drivers are never offered anything — and iOS is the
    // platform where index.html has said since entry 111 that push needs an INSTALLED
    // PWA, so this branch is the difference between Web Push being reachable and not.
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)" });

    initInstall();
    expect(manualInstall.value).toBe(true);
    expect(offerInstall.value).toBe(true);
    // and there is nothing to prompt WITH, which the caller must be able to tell
    expect(canInstall.value).toBe(false);
  });

  it("catches an iPad, which reports itself as a Mac", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    vi.stubGlobal("navigator", { userAgent: "Macintosh", platform: "MacIntel", maxTouchPoints: 5 });

    initInstall();
    expect(manualInstall.value).toBe(true);
  });

  it("does not mistake a desktop Mac for an iPad", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    vi.stubGlobal("navigator", { userAgent: "Macintosh", platform: "MacIntel", maxTouchPoints: 0 });

    initInstall();
    expect(manualInstall.value).toBe(false);
  });
});

describe("Dismissing silences the strip and keeps the capability", () => {
  it("stops offering on the strip", () => {
    initInstall();
    window.dispatchEvent(bipEvent());
    dismissInstall();
    expect(offerInstall.value).toBe(false);
  });

  it("LEAVES the More tab's card, which is the whole point of allowing a dismiss", () => {
    // §15.5's rule is "never nags beyond that card" — which only works if the card is
    // somewhere the driver can go back to. A dismiss that removed the capability would
    // make the × a permanent decision taken in one tap.
    initInstall();
    window.dispatchEvent(bipEvent());
    dismissInstall();

    expect(offerInstall.value).toBe(false);
    expect(installable.value).toBe(true);
  });

  it("survives a reload", () => {
    dismissInstall();
    expect(localStorage.getItem("longhaul.install_dismissed")).toBe("1");
  });
});

describe("The strip asks, and yields to everything else", () => {
  const strip = (props, opts = {}) =>
    mount(StatusStrip, { props: { online: true, pending: 0, failed: 0, ...props }, ...opts });

  it("asks when the strip has nothing else to say", () => {
    initInstall();
    window.dispatchEvent(bipEvent());
    const w = strip({});

    expect(w.find(".strip__install").exists()).toBe(true);
    expect(w.text()).toContain(en["install.offer"]);
    expect(w.text()).toContain(en["install.action"]);
  });

  it("is a button, never something that happens to the driver", () => {
    initInstall();
    window.dispatchEvent(bipEvent());
    expect(strip({}).find(".strip__install").element.tagName).toBe("BUTTON");
  });

  // AI-CONTEXT: this is the check that keeps LAW 0 satisfiable on this row. Every one
  // of these is a fact about the work in front of the driver right now; the install
  // offer is the only thing this strip carries that can wait, and the only one true for
  // weeks rather than minutes. The alternative to yielding is "Offline — everything
  // saves to your phone" plus a second label plus an action word plus a dismiss on one
  // 360 dp row, which is a clipped string in Russian.
  it.each([
    ["offline", { online: false }],
    ["a queued write", { pending: 1 }],
    ["a refused write", { failed: 1 }],
  ])("says nothing about installing while there is %s", (_label, props) => {
    initInstall();
    window.dispatchEvent(bipEvent());
    const w = strip(props);

    expect(w.find(".strip__install").exists()).toBe(false);
    expect(w.find(".strip").exists()).toBe(true); // the strip itself is still saying its piece
  });

  it("yields to a waiting build too", () => {
    initInstall();
    window.dispatchEvent(bipEvent());
    updateReady.value = true;

    const w = strip({});
    expect(w.find(".strip__update").exists()).toBe(true);
    expect(w.find(".strip__install").exists()).toBe(false);
  });

  it("carries a dismiss, and the tap silences it", async () => {
    initInstall();
    window.dispatchEvent(bipEvent());
    const w = strip({});

    const x = w.find(".strip__dismiss");
    expect(x.exists()).toBe(true);
    expect(x.attributes("aria-label")).toBe(en["install.dismiss"]);

    await x.trigger("click");
    expect(w.find(".strip__install").exists()).toBe(false);
  });

  it("goes silent again when there is nothing to say and nothing to offer", () => {
    // the strip's governing rule since entry 89: it renders NOTHING when the driver is
    // online with nothing queued, which is almost always. An install offer that is not
    // available must not resurrect it.
    expect(strip({}).find(".strip").exists()).toBe(false);
  });

  it("opens the Share sheet on iOS instead of prompting", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    vi.stubGlobal("navigator", { userAgent: "iPhone" });
    initInstall();

    const w = strip({});
    await w.find(".strip__install").trigger("click");
    await w.vm.$nextTick();

    // the three steps ARE the install path here; there is no API to fall back from
    expect(w.text()).toContain(en["install.ios_step2"]);
  });
});
